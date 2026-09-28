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
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.filters import passes_hard_filters  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.profile import load_profile  # noqa: E402
from job_radar.sources import (  # noqa: E402
    fetch_github_repos,
    fetch_gupy,
    fetch_programathor,
    fetch_solides,
)
from job_radar.runstats import write_stats  # noqa: E402
from job_radar.store import Store  # noqa: E402
from job_radar.targets import TARGETS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Coleta e filtra vagas")
    ap.add_argument("--profile", default=os.getenv("PROFILE_PATH", str(ROOT / "profile" / "profile.md")))
    ap.add_argument("--targets", default="all", help="all ou lista: ai,fullstack,techlead,dados")
    ap.add_argument("--min-skills", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "data" / "candidates.json"))
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--stats", default=str(ROOT / "data" / "last_run.json"))
    ap.add_argument("--sources", default="gupy,github,programathor",
                    help="lista separada por vírgula: gupy, github, programathor, solides")
    ap.add_argument("--solides-pages", type=int, default=50,
                    help="páginas da Sólides a varrer (14 vagas por página)")
    args = ap.parse_args()

    _, skills = load_profile(Path(args.profile))
    if not skills:
        print("ERRO: nenhuma qualificação extraída do perfil. Confira a seção 'Stack técnica'.", file=sys.stderr)
        return 1

    wanted = TARGETS.keys() if args.targets == "all" else [t.strip() for t in args.targets.split(",")]
    store = Store(Path(args.db))

    sources = {s.strip() for s in args.sources.split(",")}
    raw: dict[str, object] = {}

    if "gupy" in sources:
        for target in wanted:
            for term in TARGETS.get(target, []):
                for job in fetch_gupy(term):
                    raw.setdefault(job.fingerprint, job)  # dedup dentro da própria rodada

    if "github" in sources:
        # os repos não têm busca por termo: trazem tudo e os filtros decidem
        for job in fetch_github_repos():
            raw.setdefault(job.fingerprint, job)

    if "programathor" in sources:
        for job in fetch_programathor():
            raw.setdefault(job.fingerprint, job)

    if "solides" in sources:
        # A listagem da Sólides não traz descrição, e buscá-la custa uma requisição
        # por anúncio. `keep` roda os cortes que não dependem de descrição
        # (senioridade, modalidade, praça, função, stack) e só então vale detalhar.
        def vale_detalhar(job: Job) -> bool:
            aprovado, _ = passes_hard_filters(job, skills, min_skill_hits=0)
            return aprovado

        for job in fetch_solides(max_pages=args.solides_pages, keep=vale_detalhar):
            raw.setdefault(job.fingerprint, job)

    stats = {"coletadas": len(raw), "reprovadas": 0, "ja_enviadas": 0, "candidatas": 0}
    motivos: dict[str, int] = {}
    candidates = []

    for job in raw.values():
        ok, reason = passes_hard_filters(job, skills, args.min_skills)
        if not ok:
            stats["reprovadas"] += 1
            motivos[reason.split("(")[0].strip()] = motivos.get(reason.split("(")[0].strip(), 0) + 1
            continue
        if not store.is_new(job.fingerprint):
            stats["ja_enviadas"] += 1
            continue
        stats["candidatas"] += 1
        candidates.append(asdict(job) | {"fingerprint": job.fingerprint})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(candidates, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # o collect abre a rodada, então zera o que sobrou da varredura anterior
    write_stats(Path(args.stats), reset=True, motivos=motivos, **stats)

    print(f"Qualificações do perfil: {len(skills)}")
    print(f"Vagas coletadas:      {stats['coletadas']}")
    print(f"Reprovadas no filtro: {stats['reprovadas']}")
    for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
        print(f"   - {motivo}: {n}")
    print(f"Já enviadas antes:    {stats['ja_enviadas']}")
    print(f"CANDIDATAS:           {stats['candidatas']}  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
