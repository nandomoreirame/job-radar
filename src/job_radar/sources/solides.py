"""Sólides Vagas: agregador com ~73 mil anúncios, 3,6 mil deles em tecnologia.

Não existe API pública. Os dados chegam no payload RSC que o Next.js embute no
HTML, o que na prática é JSON e se consome sem raspar marcação.

A coleta tem dois estágios porque a listagem NÃO traz a descrição da vaga (ela é
carregada sob demanda ao abrir o anúncio). Sem descrição o casamento de
qualificações fica cego, então cada sobrevivente dos cortes baratos tem seu
JSON-LD `JobPosting` lido na página individual. Esse JSON-LD existe para o Google
for Jobs, o que o torna a superfície mais estável do site.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from collections.abc import Callable
from datetime import date, datetime

from job_radar.filters import AFFIRMATIVE_TAG
from job_radar.health import SourceHealth
from job_radar.http import get
from job_radar.models import Job, clean_html

BASE = "https://vagas.solides.com.br"
PAGE_SIZE = 14  # fixo pelo portal
DELAY_BETWEEN_PAGES = 1.2
DELAY_BETWEEN_DETAILS = 0.8

# O fim da paginação serve anúncios de 2023. Candidatar-se a eles queima o
# contato e, na prática, a vaga não existe mais.
DEFAULT_MAX_AGE_DAYS = 45

# Traduz a modalidade declarada pela fonte para o vocabulário do filtro.
_WORK_MODE = {"remoto": "remote", "hibrido": "hybrid", "presencial": "onsite"}

_PUSH = 'self.__next_f.push([1,'
_LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _fetch(url: str, health: SourceHealth | None = None) -> str:
    """Baixa uma página via o helper HTTP compartilhado.

    A Sólides responde rajada com 403; retenta 403/429 com o pacing antigo
    (5s, 10s) para não marcar a fonte como morta num burst passageiro.
    """
    try:
        body = get(
            url,
            timeout=30,
            headers={"Accept": "text/html"},
            retries=2,
            retry_statuses={403, 429},
            backoff=lambda attempt, _ra: 5.0 * (attempt + 1),
        ).decode("utf-8", "replace")
        if health:
            health.record_ok()
        return body
    except Exception as exc:
        if health:
            health.record_error(f"{type(exc).__name__}: {exc}")
        return ""


def rsc_blob(html: str) -> str:
    """Concatena os pushes do RSC num único texto.

    Decodifica cada push como string JSON de verdade: um regex ingênuo até o
    próximo `"])` quebra nos pushes que contêm aspas escapadas.
    """
    decoder = json.JSONDecoder()
    partes: list[str] = []
    i = html.find(_PUSH)
    while i >= 0:
        try:
            trecho, _ = decoder.raw_decode(html, i + len(_PUSH))
        except ValueError:
            trecho = None
        if isinstance(trecho, str):
            partes.append(trecho)
        i = html.find(_PUSH, i + 1)
    return "".join(partes)


def _slice_json(text: str, start: int) -> str:
    """Recorta o objeto JSON iniciado em `start`, ignorando chaves dentro de string."""
    opener = text[start]
    closer = {"{": "}", "[": "]"}[opener]
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def parse_listing(raw: dict) -> Job:
    """Mapeia um item da listagem para o modelo canônico.

    A URL é montada a partir do id, nunca do `redirectLink`: a fonte devolve
    "https://hwit./vacancies/926052" (sem domínio) e o subdomínio da empresa
    responde 200 com página vazia, o que passaria por link válido.
    """
    city = (raw.get("city") or {}).get("name", "")
    state = (raw.get("state") or {}).get("code", "")
    tags = [c.get("name", "") for c in (raw.get("recruitmentContractType") or [])]
    tags += [s.get("name", "") for s in (raw.get("seniority") or [])]
    if raw.get("affirmative") or raw.get("pcdOnly"):
        tags.append(AFFIRMATIVE_TAG)

    try:
        publicada = datetime.fromisoformat(raw["createdAt"])
    except (KeyError, TypeError, ValueError):
        publicada = None

    return Job(
        source="solides",
        external_id=str(raw.get("id", "")),
        title=raw.get("title", ""),
        company=raw.get("companyName", ""),
        url=f"{BASE}/vaga/{raw.get('id', '')}",
        location=", ".join(p for p in (city, state) if p),
        work_mode_hint=_WORK_MODE.get(raw.get("jobType", "")),
        tags=[t for t in tags if t],
        published_at=publicada,
    )


def is_fresh(job: Job, max_age_days: int = DEFAULT_MAX_AGE_DAYS, hoje: date | None = None) -> bool:
    """False apenas quando a fonte AFIRMA que o anúncio é velho.

    Sem data, mantém: ausência de informação não é prova de vaga vencida, e
    descartar por isso perderia anúncio bom.
    """
    if job.published_at is None:
        return True
    return (hoje or date.today()).toordinal() - job.published_at.date().toordinal() <= max_age_days


def listing_from_page(blob: str) -> tuple[dict, list[Job]]:
    """Extrai (metadados de paginação, vagas) do payload de uma página."""
    marker = blob.find('"initialData":')
    if marker < 0:
        return {}, []
    try:
        data = json.loads(_slice_json(blob, blob.index("{", marker)))
    except (ValueError, KeyError):
        return {}, []
    meta = {k: data.get(k) for k in ("totalPages", "currentPage", "count")}
    return meta, [parse_listing(item) for item in data.get("data", [])]


def parse_jobposting(html: str) -> str:
    """Devolve a descrição do JSON-LD `JobPosting`, ou vazio se não houver."""
    match = _LD_RE.search(html)
    if not match:
        return ""
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return ""
    if data.get("@type") != "JobPosting":
        return ""
    return data.get("description", "") or ""


def fetch_detail(job: Job, health: SourceHealth | None = None) -> Job:
    """Preenche a descrição a partir da página do anúncio.

    Atribuir depois da construção não passa pelo `__post_init__`, então a
    limpeza de HTML é explícita aqui: o JSON-LD devolve a descrição marcada.
    """
    job.description = clean_html(parse_jobposting(_fetch(job.url, health=health)))
    return job


def fetch_solides(
    max_pages: int = 50,
    area: str = "tecnologia",
    seniority: str = "senior",
    keep: Callable[[Job], bool] | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    health: SourceHealth | None = None,
) -> list[Job]:
    """Varre a listagem e detalha apenas as vagas que `keep` aprovar.

    `keep` existe para o custo não explodir: são ~700 anúncios sênior em
    tecnologia, e buscar a descrição de todos seria uma requisição por anúncio.
    Quem decide o que merece detalhe é o chamador, não este módulo.

    Health.jobs conta a listagem fresca ANTES do keep: listagem saudável com
    tudo filtrado continua "ok", não "vazia".
    """
    query = urllib.parse.urlencode({"seniorities": seniority})
    found: list[Job] = []

    for page in range(1, max_pages + 1):
        url = f"{BASE}/vagas/area/{area}/todas?{query}&page={page}"
        meta, jobs = listing_from_page(rsc_blob(_fetch(url, health=health)))
        if not jobs:
            break
        fresh = [j for j in jobs if is_fresh(j, max_age_days)]
        found.extend(fresh)
        if health:
            for job in fresh:
                health.record_job(job)
        # a listagem vem da mais nova para a mais velha: quando a página inteira
        # já está fora da janela, as seguintes também estão.
        if not any(is_fresh(j, max_age_days) for j in jobs):
            break
        if page >= (meta.get("totalPages") or 1):
            break
        time.sleep(DELAY_BETWEEN_PAGES)

    detailed: list[Job] = []
    for job in found:
        if keep is not None and not keep(job):
            continue
        detailed.append(fetch_detail(job, health=health))
        time.sleep(DELAY_BETWEEN_DETAILS)
    return detailed
