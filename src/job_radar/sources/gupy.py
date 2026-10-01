"""Gupy: maior ATS do Brasil, via página de busca do portal.

A API antiga (`employability-portal.gupy.io/api/v1/jobs`) morreu (404). A busca
agora é server-rendered em `portal.gupy.io/job-search`; o HTML embute
`<script id="__NEXT_DATA__">` com `props.pageProps.initialJobList.data`.
O shape de cada item é o mesmo que `parse_job` já lia.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime

from job_radar.health import SourceHealth
from job_radar.http import get
from job_radar.models import Job

SEARCH = "https://portal.gupy.io/job-search"
_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def listing_from_page(html: str) -> list[dict]:
    """Extrai a lista de vagas do `__NEXT_DATA__`. Ausente/quebrado → []."""
    match = _NEXT_DATA.search(html or "")
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (ValueError, TypeError):
        return []
    try:
        listing = data["props"]["pageProps"]["initialJobList"]
    except (KeyError, TypeError):
        return []
    if isinstance(listing, dict):
        items = listing.get("data") or []
    elif isinstance(listing, list):
        items = listing
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


def parse_job(raw: dict) -> Job:
    """Mapeia o payload da Gupy para o modelo canônico."""
    city, state = (raw.get("city") or "").strip(), (raw.get("state") or "").strip()
    location = ", ".join(p for p in (city, state) if p) or (raw.get("country") or "")
    published = None
    if raw.get("publishedDate"):
        try:
            published = datetime.fromisoformat(raw["publishedDate"].replace("Z", "+00:00"))
        except ValueError:
            published = None
    return Job(
        source="gupy",
        external_id=str(raw.get("id", "")),
        title=raw.get("name", ""),
        company=(raw.get("careerPageName") or "").strip(),
        url=raw.get("jobUrl") or raw.get("careerPageUrl") or "",
        description=raw.get("description", ""),
        location=location,
        work_mode_hint=raw.get("workplaceType"),
        tags=[s for s in (raw.get("skills") or []) if isinstance(s, str)],
        published_at=published,
    )


def fetch_gupy(
    term: str,
    limit: int = 12,
    health: SourceHealth | None = None,
) -> list[Job]:
    """Busca vagas por termo na página do portal (uma página = até 12 itens)."""
    # o termo vai no PATH: com "?term=" o portal responde 200 com a busca vazia
    url = f"{SEARCH}/term={urllib.parse.quote(term, safe='')}"
    try:
        html = get(url, headers={"Accept": "text/html"}).decode("utf-8", "replace")
        if health:
            health.record_ok()
    except Exception as exc:  # rede instável não pode derrubar a varredura inteira
        if health:
            health.record_error(f"{type(exc).__name__}: {exc}")
        return []

    items = listing_from_page(html)
    if not items:
        # HTTP ok, mas o payload Next sumiu ou mudou de shape
        if health:
            health.record_parse_error("payload ausente")
        return []

    # o portal pagina de 12 em 12; uma página por termo basta para o radar diário
    jobs = [parse_job(item) for item in items[:limit]]
    if health:
        for job in jobs:
            health.record_job(job)
    return jobs
