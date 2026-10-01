#!/usr/bin/env python3
"""Coleta vagas, aplica os filtros duros e salva as candidatas para avaliação.

Este script NÃO julga compatibilidade semântica e NÃO envia nada: ele só reduz o
universo ao que é elegível, para que a avaliação cara (e o envio) rode sobre um
conjunto pequeno. A contagem impressa no fim é o que você vê antes de aprovar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.boards import resolve_boards  # noqa: E402
from job_radar.dedup import (  # noqa: E402
    drop_near_duplicates,
    matches_history_simhash,
    select_variant,
)
from job_radar.discards import format_row, write_discards  # noqa: E402
from job_radar.filters import passes_hard_filters  # noqa: E402
from job_radar.fsutil import atomic_write_text  # noqa: E402
from job_radar.health import (  # noqa: E402
    SourceHealth,
    format_health_warnings,
    update_failure_streaks,
)
from job_radar.identity import url_key  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.profile import load_profile  # noqa: E402
from job_radar.runstats import write_stats  # noqa: E402
from job_radar.sources import (  # noqa: E402
    fetch_ashby,
    fetch_github_repos,
    fetch_greenhouse,
    fetch_gupy,
    fetch_lever,
    fetch_programathor,
    fetch_solides,
)
from job_radar.store import SEEN_WINDOW_DAYS, Store  # noqa: E402
from job_radar.targets import TARGETS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = ROOT / "data" / "source_health.json"

_SOURCE_HELP = (
    "lista separada por vírgula: gupy, github, programathor, solides, "
    "greenhouse, lever, ashby (ats = as três)"
)


def _expand_sources(raw: str) -> set[str]:
    names = {s.strip().casefold() for s in raw.split(",") if s.strip()}
    if "ats" in names:
        names.discard("ats")
        names.update({"greenhouse", "lever", "ashby"})
    return names


def _read_streaks(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in data.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _write_streaks(path: Path, streaks: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(streaks, ensure_ascii=False, indent=2))


def _add(variants: dict[str, list[Job]], job: Job) -> None:
    variants[job.fingerprint].append(job)


def main() -> int:
    ap = argparse.ArgumentParser(description="Coleta e filtra vagas")
    ap.add_argument("--profile", default=os.getenv("PROFILE_PATH", str(ROOT / "profile" / "profile.md")))
    ap.add_argument("--targets", default="all", help="all ou lista: ai,fullstack,techlead,dados")
    ap.add_argument("--min-skills", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "data" / "candidates.json"))
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--stats", default=str(ROOT / "data" / "last_run.json"))
    ap.add_argument("--health", default=str(HEALTH_PATH),
                    help="arquivo de sequência de falhas por fonte")
    ap.add_argument("--sources", default="gupy,github,programathor", help=_SOURCE_HELP)
    ap.add_argument("--solides-pages", type=int, default=50,
                    help="páginas da Sólides a varrer (14 vagas por página)")
    ap.add_argument(
        "--discards",
        default=str(ROOT / "data" / "discarded.tsv"),
        help="TSV das vagas descartadas nesta rodada (sobrescreve)",
    )
    args = ap.parse_args()

    _, skills = load_profile(Path(args.profile))
    if not skills:
        print("ERRO: nenhuma qualificação extraída do perfil. Confira a seção 'Stack técnica'.", file=sys.stderr)
        return 1

    wanted = TARGETS.keys() if args.targets == "all" else [t.strip() for t in args.targets.split(",")]
    store = Store(Path(args.db))

    sources = _expand_sources(args.sources)
    boards = resolve_boards()
    variants: dict[str, list[Job]] = defaultdict(list)
    health_by_source: dict[str, SourceHealth] = {}

    def health_for(name: str) -> SourceHealth:
        return health_by_source.setdefault(name, SourceHealth(name=name))

    if "gupy" in sources:
        h = health_for("gupy")
        for target in wanted:
            for term in TARGETS.get(target, []):
                for job in fetch_gupy(term, health=h):
                    _add(variants, job)

    if "github" in sources:
        h = health_for("github")
        for job in fetch_github_repos(health=h):
            _add(variants, job)

    if "programathor" in sources:
        h = health_for("programathor")
        for job in fetch_programathor(health=h):
            _add(variants, job)

    if "solides" in sources:
        h = health_for("solides")

        def vale_detalhar(job: Job) -> bool:
            aprovado, _ = passes_hard_filters(job, skills, min_skill_hits=0)
            return aprovado

        for job in fetch_solides(max_pages=args.solides_pages, keep=vale_detalhar, health=h):
            _add(variants, job)

    if "greenhouse" in sources:
        h = health_for("greenhouse")
        for job in fetch_greenhouse(boards.get("greenhouse"), health=h):
            _add(variants, job)

    if "lever" in sources:
        h = health_for("lever")
        for job in fetch_lever(boards.get("lever"), health=h):
            _add(variants, job)

    if "ashby" in sources:
        h = health_for("ashby")
        for job in fetch_ashby(boards.get("ashby"), health=h):
            _add(variants, job)

    # uma variante por fingerprint (a que passa no filtro, se houver);
    # ok/reason vêm do select para não recontar o hard filter na escolhida
    raw = [
        select_variant(group, skills, args.min_skills)
        for group in variants.values()
    ]

    fontes = {name: h.to_dict() for name, h in health_by_source.items()}
    prev_streaks = _read_streaks(Path(args.health))
    streaks = update_failure_streaks(prev_streaks, fontes)
    _write_streaks(Path(args.health), streaks)

    stats = {
        "coletadas": len(raw),
        "reprovadas": 0,
        "ja_enviadas": 0,
        "quase_duplicadas": 0,
        "candidatas": 0,
        "fontes": fontes,
        "streaks": streaks,
    }
    motivos: dict[str, int] = {}
    discard_rows: list[str] = []
    passed: list[Job] = []
    seen_fps, seen_urls = store.seen_keys(window_days=SEEN_WINDOW_DAYS)
    history_simhashes = store.recent_simhashes(window_days=SEEN_WINDOW_DAYS)

    for job, ok, reason in raw:
        if not ok:
            stats["reprovadas"] += 1
            chave = reason.split("(")[0].strip()
            motivos[chave] = motivos.get(chave, 0) + 1
            discard_rows.append(format_row(job, reason))
            continue
        key = url_key(job.url)
        already = job.fingerprint in seen_fps or (key in seen_urls if key else False)
        if already or matches_history_simhash(job, history_simhashes):
            stats["ja_enviadas"] += 1
            discard_rows.append(format_row(job, "já enviada"))
            continue
        passed.append(job)

    candidates_jobs, near_dropped = drop_near_duplicates(passed)
    stats["quase_duplicadas"] = near_dropped
    # as quase-duplicatas caíram depois do filtro: registram no TSV
    kept_ids = {id(j) for j in candidates_jobs}
    for job in passed:
        if id(job) not in kept_ids:
            discard_rows.append(format_row(job, "quase duplicada"))

    candidates = []
    for job in candidates_jobs:
        stats["candidatas"] += 1
        candidates.append(asdict(job) | {"fingerprint": job.fingerprint})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out, json.dumps(candidates, ensure_ascii=False, indent=2, default=str)
    )
    write_discards(Path(args.discards), discard_rows, append=False)

    write_stats(Path(args.stats), reset=True, motivos=motivos, **stats)

    print(f"Qualificações do perfil: {len(skills)}")
    print(f"Vagas coletadas:      {stats['coletadas']}")
    print(f"Reprovadas no filtro: {stats['reprovadas']}")
    for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
        print(f"   - {motivo}: {n}")
    print(f"Já enviadas antes:    {stats['ja_enviadas']}")
    print(f"Quase duplicadas:     {stats['quase_duplicadas']}")
    print(f"CANDIDATAS:           {stats['candidatas']}  -> {out}")

    for line in format_health_warnings(fontes, streaks):
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
