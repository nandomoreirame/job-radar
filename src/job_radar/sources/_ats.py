"""Loop compartilhado fetch→health→parse→gate→record para boards ATS.

Greenhouse/Lever/Ashby repetiam o mesmo esqueleto; o join de localização
por espaço (bug que derrubava Curitiba) apareceu nos três. Um helper só
segura a política de health e o country gate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from job_radar.geo import is_brazil_relevant
from job_radar.health import SourceHealth
from job_radar.http import get_json
from job_radar.models import Job

# (job, location_haystack, country) — country vazio quando o board não expõe
GateRow = tuple[Job, str, str]
ParseBoard = Callable[[Any, str, str], Iterable[GateRow | None]]


def fetch_ats_boards(
    *,
    api_template: str,
    slugs: dict[str, str],
    health: SourceHealth | None,
    parse_board: ParseBoard,
) -> list[Job]:
    """Varre cada slug: GET JSON, parseia, aplica country gate, grava health."""
    found: list[Job] = []
    for slug, company in slugs.items():
        url = api_template.format(slug=slug)
        try:
            payload = get_json(url, headers={"Accept": "application/json"})
            if health:
                health.record_ok()
        except Exception as exc:
            if health:
                health.record_error(f"{slug}: {type(exc).__name__}")
            continue
        for row in parse_board(payload, slug, company):
            if row is None:
                continue
            job, location, country = row
            if not is_brazil_relevant(
                location=location,
                country=country,
                work_mode=job.work_mode_hint,
            ):
                if health:
                    health.record_foreign()
                continue
            found.append(job)
            if health:
                health.record_job(job)
    return found
