"""Deduplicação intra-rodada: variantes da mesma vaga e quase-duplicatas."""

from __future__ import annotations

from job_radar.filters import passes_hard_filters
from job_radar.identity import (
    NEAR_DUP_HAMMING,
    company_key,
    hamming,
    simhash,
)
from job_radar.models import Job


def select_variant(
    group: list[Job],
    skills: set[str],
    min_skill_hits: int,
) -> tuple[Job, bool, str]:
    """Mantém a primeira variante que passa nos filtros duros (senão a primeira).

    Devolve (job, ok, reason) para o collect reusar o resultado e não contar
    reprovação/descarte duas vezes na mesma variante escolhida.

    A Gupy publica a mesma vaga por cidade: se a primeira for híbrida fora de
    COMMUTE_CITIES, a rodada perdia a vaga inteira. As demais cidades vão para
    `other_locations`.
    """
    if not group:
        raise ValueError("grupo de variantes vazio")
    chosen = group[0]
    ok, reason = False, ""
    for i, job in enumerate(group):
        job_ok, job_reason = passes_hard_filters(job, skills, min_skill_hits)
        if i == 0:
            # fallback: se ninguém passar, a reason da primeira explica o descarte
            ok, reason = job_ok, job_reason
        if job_ok:
            chosen = job
            ok, reason = job_ok, job_reason
            break
    others: list[str] = []
    seen: set[str] = set()
    for job in group:
        if job is chosen:
            continue
        loc = (job.location or "").strip()
        if not loc or loc == chosen.location or loc in seen:
            continue
        seen.add(loc)
        others.append(loc)
    chosen.other_locations = others
    return chosen, ok, reason


def drop_near_duplicates(jobs: list[Job]) -> tuple[list[Job], int]:
    """Entre candidatas da rodada, descarta quase-duplicatas (fica a descrição maior)."""
    kept: list[Job] = []
    # Cache por índice em `kept`: recomputar simhash a cada rival era O(n²).
    kept_hashes: list[int | None] = []
    dropped = 0
    for job in jobs:
        sh = simhash(job.description)
        if sh is None:
            kept.append(job)
            kept_hashes.append(None)
            continue
        ck = company_key(job.company)
        rival_idx = None
        for i, other_sh in enumerate(kept_hashes):
            if other_sh is None:
                continue
            if company_key(kept[i].company) == ck:
                continue
            if hamming(sh, other_sh) <= NEAR_DUP_HAMMING:
                rival_idx = i
                break
        if rival_idx is None:
            kept.append(job)
            kept_hashes.append(sh)
            continue
        rival = kept[rival_idx]
        if len(job.description) > len(rival.description):
            kept[rival_idx] = job
            kept_hashes[rival_idx] = sh
        dropped += 1
    return kept, dropped


def matches_history_simhash(
    job: Job,
    history: list[tuple[int, str]],
    *,
    cached_simhash: int | None = None,
) -> bool:
    """True se o SimHash da vaga está a ≤5 bits de algum envio recente de OUTRA empresa."""
    sh = cached_simhash if cached_simhash is not None else simhash(job.description)
    if sh is None:
        return False
    ck = company_key(job.company)
    for hist_sh, hist_ck in history:
        if hist_ck == ck:
            continue
        if hamming(sh, hist_sh) <= NEAR_DUP_HAMMING:
            return True
    return False
