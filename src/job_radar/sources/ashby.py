"""Ashby Job Board API: um board público por slug de empresa."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from job_radar.boards import resolve_boards
from job_radar.geo import normalize_location
from job_radar.health import SourceHealth
from job_radar.models import Job
from job_radar.sources._ats import GateRow, fetch_ats_boards

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"

_MODE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
}


def _country_from(raw: dict) -> str:
    addr = ((raw.get("address") or {}).get("postalAddress") or {})
    return (addr.get("addressCountry") or "").strip()


def _location_raw(raw: dict) -> str:
    """Monta um texto de localização a partir dos campos estruturados."""
    addr = ((raw.get("address") or {}).get("postalAddress") or {})
    parts = [
        raw.get("location") or "",
        addr.get("addressLocality") or "",
        addr.get("addressRegion") or "",
        addr.get("addressCountry") or "",
    ]
    for secondary in raw.get("secondaryLocations") or []:
        parts.append(secondary.get("location") or "")
        saddr = ((secondary.get("address") or {}).get("postalAddress") or {})
        parts.extend(
            [
                saddr.get("addressLocality") or "",
                saddr.get("addressRegion") or "",
                saddr.get("addressCountry") or "",
            ]
        )
    # dedup preservando ordem
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        key = part.strip().casefold()
        if part.strip() and key not in seen:
            seen.add(key)
            ordered.append(part.strip())
    return ", ".join(ordered)


def parse_job(raw: dict, company: str) -> Job | None:
    """Mapeia um job Ashby. Devolve None quando `isListed` é falso."""
    if raw.get("isListed") is False:
        return None

    # isRemote é NÃO confiável (true em Hybrid); workplaceType manda.
    mode = _MODE_MAP.get((raw.get("workplaceType") or "").casefold().replace("-", ""))
    if mode is None:
        mode = _MODE_MAP.get((raw.get("workplaceType") or "").casefold())

    # normaliza a praça principal (cidade do board), não a lista inteira
    primary = (raw.get("location") or "").strip()
    addr = ((raw.get("address") or {}).get("postalAddress") or {})
    primary_full = ", ".join(
        p
        for p in (
            primary or addr.get("addressLocality") or "",
            addr.get("addressRegion") or "",
            addr.get("addressCountry") or "",
        )
        if p
    )
    location = normalize_location(primary_full or primary)

    description = raw.get("descriptionPlain") or ""
    comp = (raw.get("compensation") or {}).get("scrapeableCompensationSalarySummary")
    if comp:
        description = f"{description}\n\nCompensation: {comp}".strip()

    published = None
    if raw.get("publishedAt"):
        try:
            published = datetime.fromisoformat(raw["publishedAt"].replace("Z", "+00:00"))
        except ValueError:
            published = None

    tags = []
    if raw.get("employmentType"):
        tags.append(raw["employmentType"])
    if raw.get("department"):
        tags.append(raw["department"])

    return Job(
        source="ashby",
        external_id=str(raw.get("id", "")),
        title=(raw.get("title") or "").strip(),
        company=company,
        url=raw.get("jobUrl") or "",
        description=description,
        location=location,
        work_mode_hint=mode,
        tags=tags,
        published_at=published,
    )


def _parse_board(payload: Any, slug: str, company: str) -> Iterable[GateRow | None]:
    if not isinstance(payload, dict):
        return
    for item in payload.get("jobs") or []:
        job = parse_job(item, company=company)
        if job is None:
            yield None
            continue
        yield job, _location_raw(item), _country_from(item)


def fetch_ashby(
    slugs: dict[str, str] | None = None,
    health: SourceHealth | None = None,
) -> list[Job]:
    """Varre boards Ashby. `slugs` mapeia slug -> nome de exibição da empresa."""
    if slugs is None:
        slugs = resolve_boards().get("ashby", {})
    return fetch_ats_boards(
        api_template=API,
        slugs=slugs,
        health=health,
        parse_board=_parse_board,
    )
