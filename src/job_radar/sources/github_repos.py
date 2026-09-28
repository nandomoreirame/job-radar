"""Vagas publicadas como issues em repositórios brasileiros do GitHub.

É o caminho para sair do ATS: nesses repos a vaga é escrita por quem contrata,
e o padrão da comunidade pede contato no corpo, então é onde aparece e-mail
direto. A API é pública e o formato do título é convencionado:
`[Modalidade/Cidade] Cargo na Empresa`.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from job_radar.contact import extract_email, extract_phone
from job_radar.models import Job

REPOS = [
    "frontendbr/vagas",
    "backend-br/vagas",
    "datascience-br/vagas",
    "react-brasil/vagas",
    "phpdevbr/vagas",
    "androiddevbr/vagas",
    "CangaceirosDevels/vagas_de_emprego",
    "vuejs-br/vagas",
]
API = "https://api.github.com/repos/{repo}/issues?state=open&per_page=100&sort=created&direction=desc"

# Os repos de vagas raramente fecham issue antiga: encontramos anúncio de 570 dias
# ainda marcado como "open", com o e-mail do recrutador já desativado (bounce 550).
# Sem corte de idade, o radar gasta candidatura em vaga que não existe mais.
DEFAULT_MAX_AGE_DAYS = 45

_TITLE_RE = re.compile(r"^\s*\[(?P<bracket>[^\]]+)\]\s*(?P<rest>.+?)\s*$")
_COMPANY_NA_RE = re.compile(r"\s+n[ao]\s+(?P<company>[^()\[\]]+?)\s*$", re.I)
_TRAILING_BRACKET_RE = re.compile(r"\s*\[[^\]]*\]\s*$")
_COMPANY_PAREN_RE = re.compile(r"\((?P<company>[^)]+)\)\s*$")
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")

_MODE_MAP = {"remoto": "remote", "remote": "remote", "híbrido": "hybrid", "hibrido": "hybrid",
             "hybrid": "hybrid", "presencial": "onsite", "on-site": "onsite", "alocado": "onsite"}


def _looks_like_company(text: str) -> bool:
    """Distingue "(Jcal)" de "(LLMs, Next.js, Python)".

    Parêntese no fim do título tanto nomeia a empresa quanto lista a stack. Nome
    de empresa raramente tem vírgula, barra ou muitas palavras; lista de
    tecnologia quase sempre tem.
    """
    value = text.strip()
    if not value or "," in value or "/" in value:
        return False
    return len(value.split()) <= 3


def parse_title(title: str) -> tuple[str, str, str, str]:
    """Extrai (cargo, empresa, modalidade, cidade) do título convencionado."""
    clean = _EMOJI_RE.sub("", title).strip()
    mode = city = ""
    match = _TITLE_RE.match(clean)
    rest = clean
    if match:
        bracket = match.group("bracket").strip()
        rest = match.group("rest").strip()
        # "Híbrido/Curitiba", "Híbrido-SP" ou só "Remoto"
        parts = re.split(r"[/\-–]", bracket, maxsplit=1)
        mode = _MODE_MAP.get(parts[0].strip().casefold(), "")
        city = parts[1].strip() if len(parts) > 1 else ""

    rest = _TRAILING_BRACKET_RE.sub("", rest)  # "[PJ, LATAM]" no fim não é empresa
    company = ""
    company_match = _COMPANY_NA_RE.search(rest)
    if company_match:
        company = company_match.group("company").strip(" -–—")
        rest = rest[: company_match.start()].strip(" -–—")
    else:
        paren = _COMPANY_PAREN_RE.search(rest)
        if paren and _looks_like_company(paren.group("company")):
            company = paren.group("company").strip(" -–—")
            rest = rest[: paren.start()].strip(" -–—")
    return rest.strip(), company, mode, city


def parse_issue(issue: dict, repo: str) -> Job:
    body = issue.get("body") or ""
    labels = [label.get("name", "") for label in issue.get("labels", [])]
    role, company, mode, city = parse_title(issue.get("title", ""))

    if not mode:  # o título nem sempre traz; as labels costumam trazer
        for label in labels:
            mode = _MODE_MAP.get(label.strip().casefold(), "")
            if mode:
                break

    published = None
    if issue.get("created_at"):
        try:
            published = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
        except ValueError:
            published = None

    return Job(
        source=f"github:{repo.split('/')[0]}",
        external_id=str(issue.get("number", "")),
        title=role or issue.get("title", ""),
        company=company,  # vazio quando o título não declara: melhor que fingir o nome do repo
        url=issue.get("html_url", ""),
        description=body,
        location=city,
        work_mode_hint=mode or None,
        tags=labels,
        contact_email=extract_email(body),
        contact_phone=extract_phone(body),
        published_at=published,
    )


def is_fresh(job: Job, max_age_days: int) -> bool:
    """Vaga sem data é tratada como fresca; com data, precisa estar na janela."""
    if job.published_at is None:
        return True
    age = datetime.now(timezone.utc) - job.published_at
    return age <= timedelta(days=max_age_days)


def fetch_github_repos(repos: list[str] | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> list[Job]:
    """Varre os repositórios de vagas. Um token no ambiente eleva o limite de
    60 para 5000 requisições por hora, mas não é obrigatório."""
    headers = {"User-Agent": "job-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    jobs: list[Job] = []
    for repo in repos or REPOS:
        try:
            req = urllib.request.Request(API.format(repo=repo), headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310
                issues = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue  # repo removido ou rede instável não derruba a varredura
        parsed = (parse_issue(i, repo) for i in issues if "pull_request" not in i)
        jobs.extend(job for job in parsed if is_fresh(job, max_age_days))
    return jobs
