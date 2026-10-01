"""Lever postings API: um board público por slug de empresa."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from job_radar.boards import resolve_boards
from job_radar.geo import normalize_location
from job_radar.health import SourceHealth
from job_radar.models import Job
from job_radar.sources._ats import GateRow, fetch_ats_boards

API = "https://api.lever.co/v0/postings/{slug}?mode=json"

_MODE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
    "unspecified": None,
}


def _description(raw: dict) -> str:
    parts: list[str] = []
    if raw.get("descriptionPlain"):
        parts.append(raw["descriptionPlain"])
    for block in raw.get("lists") or []:
        title = (block.get("text") or "").strip()
        body = (block.get("content") or "").strip()
        if title:
            parts.append(title)
        if body:
            parts.append(body)
    if raw.get("additionalPlain"):
        parts.append(raw["additionalPlain"])
    return "\n\n".join(parts)


def parse_job(raw: dict, company: str, slug: str = "") -> Job:
    """Mapeia um posting Lever. O nome da empresa vem do mapeamento configurado."""
    cats = raw.get("categories") or {}
    loc = cats.get("location") or ""
    all_locs = cats.get("allLocations") or []
    if not loc and all_locs:
        loc = all_locs[0]
    mode = _MODE_MAP.get((raw.get("workplaceType") or "").casefold())
    tags = []
    if cats.get("commitment"):
        tags.append(cats["commitment"])
    if cats.get("department"):
        tags.append(cats["department"])

    published = None
    created = raw.get("createdAt")
    if isinstance(created, (int, float)):
        # epoch em milissegundos
        published = datetime.fromtimestamp(created / 1000.0, tz=timezone.utc)

    return Job(
        source="lever",
        external_id=str(raw.get("id", "")),
        title=raw.get("text") or "",
        company=company,
        url=raw.get("hostedUrl") or "",
        description=_description(raw),
        location=(
            normalize_location(loc)
            if loc and loc.casefold() not in {"remoto", "remote"}
            else loc
        ),
        work_mode_hint=mode,
        tags=tags,
        published_at=published,
    )


def _gate_location(item: dict, job: Job) -> str:
    """Junta location + allLocations com vírgula (espaço colava e o gate falhava)."""
    cats = item.get("categories") or {}
    parts = [cats.get("location") or ""]
    parts.extend(cats.get("allLocations") or [])
    parts.append(job.location)
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        text = (part or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            ordered.append(text)
    return ", ".join(ordered)


def _parse_board(payload: Any, slug: str, company: str) -> Iterable[GateRow | None]:
    items = payload if isinstance(payload, list) else []
    for item in items:
        job = parse_job(item, company=company, slug=slug)
        yield job, _gate_location(item, job), item.get("country") or ""


def fetch_lever(
    slugs: dict[str, str] | None = None,
    health: SourceHealth | None = None,
) -> list[Job]:
    """Varre boards Lever. `slugs` mapeia slug -> nome de exibição da empresa."""
    if slugs is None:
        slugs = resolve_boards().get("lever", {})
    return fetch_ats_boards(
        api_template=API,
        slugs=slugs,
        health=health,
        parse_board=_parse_board,
    )
