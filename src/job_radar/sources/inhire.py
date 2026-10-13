"""InHire: ATS brasileiro com API pública por empresa (tenant via header X-Tenant).

A listagem traz título, modalidade e local, mas não a descrição, e é dela que
sai o casamento de qualificações. Detalhar todo anúncio custaria uma requisição
por vaga, então segue o desenho da Sólides: o chamador passa `keep` e só o que
sobrevive aos filtros baratos ganha a segunda chamada.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from job_radar.boards import resolve_boards
from job_radar.geo import is_brazil_relevant, normalize_location
from job_radar.health import SourceHealth
from job_radar.http import get_json
from job_radar.models import Job

API = "https://api.inhire.app/job-posts/public/pages"
JOB_URL = "https://{slug}.inhire.app/vagas/{job_id}"
DELAY_BETWEEN_DETAILS = 1.0

_MODE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on-site": "onsite",
    "onsite": "onsite",
}


def _headers(slug: str) -> dict[str, str]:
    return {"X-Tenant": slug, "Accept": "application/json"}


def country_from_location(location: str) -> str:
    """Código de país do último segmento ("Osasco, SP, BR" -> "BR").

    Só aceita 2 letras maiúsculas como último segmento de uma lista com
    vírgula, ou o campo inteiro: "São Paulo" sozinho não é país.
    """
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    if not parts:
        return ""
    last = parts[-1]
    is_code = len(last) == 2 and last.isalpha() and last.isupper()
    # "SP" sozinho é UF, não país; só vale como país atrás de outro segmento
    # ou quando é o próprio "BR" que a InHire usa para vaga remota
    if is_code and (len(parts) > 1 or last == "BR"):
        return last
    return ""


def _strip_country(location: str, country: str) -> str:
    if not country:
        return location
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if parts and parts[-1] == country:
        parts = parts[:-1]
    return ", ".join(parts)


def parse_listing(raw: dict[str, Any], *, slug: str, company: str) -> Job:
    """Mapeia um item de `jobsPage`. Descrição e data chegam em `apply_detail`."""
    location = raw.get("location") or ""
    country = country_from_location(location)
    city = _strip_country(location, country)
    if not city and country == "BR":
        shown = "Brasil"
    else:
        shown = normalize_location(city) if city else ""
    job_id = str(raw.get("jobId") or "")
    return Job(
        source="inhire",
        external_id=job_id,
        title=raw.get("displayName") or "",
        company=company,
        url=JOB_URL.format(slug=slug, job_id=job_id),
        location=shown,
        work_mode_hint=_MODE_MAP.get((raw.get("workplaceType") or "").casefold()),
    )


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)  # 3.11+ aceita o sufixo "Z"
    except ValueError:
        return None


def apply_detail(job: Job, detail: dict[str, Any]) -> Job:
    """Preenche descrição e data a partir de `pages/{jobId}`.

    Atribuir depois da construção não passa pelo `__post_init__`, então a
    limpeza de HTML é refeita construindo o Job de novo.
    """
    published = _parse_date(detail.get("publishedAt")) or _parse_date(detail.get("createdAt"))
    return Job(
        source=job.source,
        external_id=job.external_id,
        title=job.title,
        company=job.company,
        url=job.url,
        description=detail.get("description") or "",
        location=job.location,
        work_mode_hint=job.work_mode_hint,
        tags=[str(t) for t in detail.get("contractType") or [] if t],
        published_at=published,
    )


def fetch_inhire(
    slugs: dict[str, str] | None = None,
    health: SourceHealth | None = None,
    keep: Callable[[Job], bool] | None = None,
) -> list[Job]:
    """Varre os tenants InHire. `slugs` mapeia tenant -> nome de exibição.

    Health.jobs conta a listagem brasileira ANTES do keep: tenant saudável com
    tudo filtrado continua "ok", não "vazia".
    """
    if slugs is None:
        slugs = resolve_boards().get("inhire", {})
    found: list[Job] = []
    for slug, configured in slugs.items():
        try:
            page = get_json(API, headers=_headers(slug))
            if health:
                health.record_ok()
        except Exception as exc:  # noqa: BLE001 — um tenant fora do ar não derruba os outros
            if health:
                health.record_error(f"{slug}: {type(exc).__name__}")
            continue
        if not isinstance(page, dict):
            page = {}
        items = page.get("jobsPage")
        if not isinstance(items, list):
            if health:
                health.record_parse_error(f"{slug}: resposta sem jobsPage")
            continue
        # sem nome no ATS_BOARDS o nome cai no slug; o payload tem o nome real
        company = configured
        if configured == slug and page.get("tenantName"):
            company = str(page["tenantName"])

        for item in items:
            job = parse_listing(item, slug=slug, company=company)
            country = country_from_location(item.get("location") or "")
            if not is_brazil_relevant(
                location=job.location, country=country, work_mode=job.work_mode_hint
            ):
                if health:
                    health.record_foreign()
                continue
            if health:
                health.record_job(job)
            if keep is not None and not keep(job):
                continue
            try:
                detail = get_json(f"{API}/{job.external_id}", headers=_headers(slug))
                if health:
                    health.record_ok()
            except Exception as exc:  # noqa: BLE001 — vaga sem detalhe é descartada, a varredura segue
                if health:
                    health.record_error(f"{slug}/{job.external_id}: {type(exc).__name__}")
                continue
            found.append(apply_detail(job, detail if isinstance(detail, dict) else {}))
            time.sleep(DELAY_BETWEEN_DETAILS)
    return found
