"""Greenhouse Job Board API: um board público por slug de empresa."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any, Iterable

from job_radar.boards import resolve_boards
from job_radar.geo import normalize_location
from job_radar.health import SourceHealth
from job_radar.models import Job
from job_radar.sources._ats import GateRow, fetch_ats_boards

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

_MODE_IN_LOCATION = re.compile(
    r"^\s*(remote|hybrid|remoto|h[ií]brido|onsite|on-site|presencial)\s*$",
    re.I,
)
# Sufixo de modalidade colado na praça: "São Paulo | Hybrid", "(Remote)", "- On-site"
_TRAILING_MODE = re.compile(
    r"(?P<loc>.*?)\s*(?:[|/\-–—]\s*|\()\s*"
    r"(?P<mode>remote|hybrid|remoto|h[ií]brido|onsite|on-site|presencial)\s*\)?\s*$",
    re.I,
)
_MODE_MAP = {
    "remote": "remote",
    "remoto": "remote",
    "hybrid": "hybrid",
    "hibrido": "hybrid",
    "híbrido": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
    "presencial": "onsite",
}


def _strip_company_prefix(title: str, company: str) -> str:
    """Remove `Empresa | Cargo` / `Empresa| Cargo` do título."""
    if not title or not company:
        return title
    # tolerante a espaços ao redor da barra vertical
    pattern = re.compile(
        rf"^\s*{re.escape(company)}\s*\|\s*",
        re.I,
    )
    return pattern.sub("", title).strip() or title


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mode_key(raw: str) -> str:
    return raw.casefold().replace("í", "i")


def _location_and_mode(raw: dict) -> tuple[str, str | None]:
    loc_name = ((raw.get("location") or {}).get("name") or "").strip()
    mode = None

    if _MODE_IN_LOCATION.match(loc_name):
        mode = _MODE_MAP.get(_mode_key(loc_name))
        # cidade real vive em offices[].location
        offices = raw.get("offices") or []
        for office in offices:
            candidate = (office.get("location") or office.get("name") or "").strip()
            if candidate and not _MODE_IN_LOCATION.match(candidate):
                loc_name = candidate
                break
    else:
        # "São Paulo | Hybrid", "Curitiba (Remote)", "Brasil - On-site"
        trailing = _TRAILING_MODE.match(loc_name)
        if trailing:
            mode = _MODE_MAP.get(_mode_key(trailing.group("mode")))
            loc_name = trailing.group("loc").strip(" ,-|/")

    return normalize_location(loc_name), mode


def parse_job(raw: dict, slug: str, display_name: str = "") -> Job:
    """Mapeia um job do board Greenhouse para o modelo canônico.

    `company_name` do payload manda; sem ele, cai no nome do mapeamento ATS_BOARDS.
    O prefixo `Empresa | Cargo` é removido contra os dois nomes.
    """
    company = (raw.get("company_name") or "").strip() or (display_name or "").strip()
    title = raw.get("title") or ""
    for name in ((raw.get("company_name") or "").strip(), (display_name or "").strip()):
        if name:
            title = _strip_company_prefix(title, name)
    location, mode = _location_and_mode(raw)
    # content vem entity-escaped duas vezes ("&lt;p&gt;..."); um unescape
    # antes do Job deixa o HTML real para clean_html remover as tags.
    content = html.unescape(raw.get("content") or "")
    published = _parse_dt(raw.get("first_published")) or _parse_dt(raw.get("updated_at"))
    return Job(
        source="greenhouse",
        external_id=str(raw.get("id", "")),
        title=title,
        company=company,
        url=raw.get("absolute_url") or "",
        description=content,
        location=location,
        work_mode_hint=mode,
        published_at=published,
        tags=[slug] if slug else [],
    )


def _gate_location(item: dict, job: Job) -> str:
    """Junta praça bruta + offices com vírgula (espaço colava tokens e o gate falhava)."""
    raw_loc = ((item.get("location") or {}).get("name") or "").strip()
    offices = [
        (o.get("location") or "").strip()
        for o in (item.get("offices") or [])
        if (o.get("location") or "").strip()
    ]
    parts = [p for p in [raw_loc, *offices, job.location] if p]
    # dedup preservando ordem
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        key = part.casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(part)
    return ", ".join(ordered)


def _parse_board(payload: Any, slug: str, company: str) -> Iterable[GateRow | None]:
    if not isinstance(payload, dict):
        return
    for item in payload.get("jobs") or []:
        job = parse_job(item, slug, display_name=company)
        yield job, _gate_location(item, job), ""


def fetch_greenhouse(
    slugs: dict[str, str] | None = None,
    health: SourceHealth | None = None,
) -> list[Job]:
    """Varre boards Greenhouse. `slugs` mapeia slug -> nome de exibição."""
    if slugs is None:
        slugs = resolve_boards().get("greenhouse", {})
    return fetch_ats_boards(
        api_template=API,
        slugs=slugs,
        health=health,
        parse_board=_parse_board,
    )
