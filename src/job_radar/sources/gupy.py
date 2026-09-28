"""Gupy: maior ATS do Brasil, com API pública de busca.

Não exige credencial e devolve descrição completa, modalidade e link de
candidatura, o que a torna a fonte mais barata e mais confiável do conjunto.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime

from job_radar.models import Job

API = "https://employability-portal.gupy.io/api/v1/jobs"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
PAGE_SIZE = 100


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa, http s)
        return json.loads(resp.read().decode("utf-8"))


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


def fetch_gupy(term: str, limit: int = PAGE_SIZE) -> list[Job]:
    """Busca vagas por termo. Uma chamada por termo, sem paginação profunda:
    o radar roda várias vezes ao dia, então a primeira página já traz o que é novo."""
    query = urllib.parse.urlencode({"jobName": term, "limit": limit, "offset": 0})
    try:
        payload = _get(f"{API}?{query}")
    except Exception:  # rede instável não pode derrubar a varredura inteira
        return []
    return [parse_job(item) for item in payload.get("data", [])]
