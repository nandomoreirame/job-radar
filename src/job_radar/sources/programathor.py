"""Programathor: board brasileiro de vagas de tecnologia, fora do circuito de ATS.

Não tem API pública, mas o HTML da listagem é estável e traz empresa, modalidade,
senioridade e regime de contratação já estruturados em cada card, o que reduz
muito a dependência de heurística sobre texto livre.
"""

from __future__ import annotations

import html as html_mod
import re
import urllib.error
import urllib.request

from job_radar.models import Job

BASE = "https://programathor.com.br"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

# Fatia por vaga: do link do card até o próximo link de card (ou o fim da página).
# Delimitar por estrutura de <div> quebra quando o board muda o layout interno.
_CARD_RE = re.compile(r'<a href="(?P<url>/jobs/[^"]+)">(?P<body>.*?)(?=<a href="/jobs/|\Z)', re.S)
_H3_RE = re.compile(r"<h3[^>]*>(?P<title>.*?)</h3>", re.S)
_ICON_RE = re.compile(r"<i class='[^']*fa[^']*'></i>([^<]+)", re.S)
_TAG_RE = re.compile(r"<span class='tag-list[^']*'>([^<]+)</span>")
_STRIP_RE = re.compile(r"<[^>]+>")

_MODE_MAP = {"remoto": "remote", "híbrido": "hybrid", "hibrido": "hybrid", "presencial": "onsite"}


# O board cola o selo "NOVA" no fim do título das vagas recentes.
_BADGE_RE = re.compile(r"(NOVA|NEW)\s*$")
# O board mantém na listagem vagas já encerradas, marcadas no próprio título.
_EXPIRED_RE = re.compile(r"^\s*vencida\b", re.I)


def _clean(text: str) -> str:
    return _BADGE_RE.sub("", html_mod.unescape(_STRIP_RE.sub("", text)).strip()).strip()


def parse_listing(page_html: str) -> list[Job]:
    """Extrai as vagas de uma página de listagem."""
    jobs: list[Job] = []
    for match in _CARD_RE.finditer(page_html):
        url = match.group("url")
        body = match.group("body")
        title_match = _H3_RE.search(body)
        if not title_match:
            continue  # link de card sem título: não é uma vaga listada
        title = _clean(title_match.group("title"))
        if _EXPIRED_RE.match(title):
            continue
        meta = body[title_match.end() :]

        icons = [_clean(i) for i in _ICON_RE.findall(meta)]
        company = icons[0] if icons else ""
        mode = ""
        location = ""
        for value in icons[1:]:
            key = value.casefold()
            for label, normalized in _MODE_MAP.items():
                if label in key:
                    mode = normalized
                    if normalized != "remote":
                        location = value
                    break

        tags = [_clean(t) for t in _TAG_RE.findall(meta)]
        # senioridade e regime chegam como ícones e viram tags para o filtro enxergar
        tags += [v for v in icons[1:] if v.casefold() in {"sênior", "senior", "pleno", "júnior", "pj", "clt"}]

        jobs.append(
            Job(
                source="programathor",
                external_id=url.split("/")[-1].split("-")[0],
                title=title,
                company=company,
                url=f"{BASE}{url}",
                description=" ".join(icons + tags),
                location=location,
                work_mode_hint=mode or None,
                tags=tags,
            )
        )
    return jobs


def fetch_programathor(paths: list[str] | None = None) -> list[Job]:
    """Varre as listagens por área. Cada caminho é uma página do board."""
    paths = paths or ["/jobs", "/jobs-python", "/jobs-javascript", "/jobs-data-science", "/jobs-devops"]
    jobs: list[Job] = []
    seen: set[str] = set()
    for path in paths:
        try:
            req = urllib.request.Request(f"{BASE}{path}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310
                page = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
        for job in parse_listing(page):
            if job.url not in seen:
                seen.add(job.url)
                jobs.append(job)
    return jobs
