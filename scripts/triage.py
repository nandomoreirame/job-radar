#!/usr/bin/env python3
"""Ordena as candidatas por compatibilidade e separa por forma de candidatura.

Saída em dois arquivos porque o tratamento é diferente: vaga com e-mail permite
preparar uma candidatura direta; vaga de ATS só permite abrir o link e aplicar
à mão. Misturar as duas no mesmo canal esconde essa diferença.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.contact import extract_email, extract_phone  # noqa: E402
from job_radar.filters import count_skill_hits  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.profile import load_profile  # noqa: E402
from job_radar.runstats import write_stats  # noqa: E402
from job_radar.scoring import score_job  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Pontua e separa as candidatas")
    ap.add_argument("--input", default=str(ROOT / "data" / "candidates.json"))
    ap.add_argument("--profile", default=os.getenv("PROFILE_PATH", str(ROOT / "profile" / "profile.md")))
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--top", type=int, default=0, help="0 = sem limite")
    ap.add_argument("--out-manual", default=str(ROOT / "data" / "apply_manual.json"))
    ap.add_argument("--out-email", default=str(ROOT / "data" / "apply_email.json"))
    ap.add_argument("--out-all", default="", help="grava também o conjunto completo em um arquivo")
    ap.add_argument("--stats", default=str(ROOT / "data" / "last_run.json"))
    args = ap.parse_args()

    _, skills = load_profile(Path(args.profile))
    items = json.loads(Path(args.input).read_text(encoding="utf-8"))

    scored = []
    for item in items:
        data = {k: v for k, v in item.items() if k not in {"fingerprint", "published_at"}}
        job = Job(**data)
        hits = count_skill_hits(job, skills)
        score = score_job(job, skills, hits)
        email, phone = extract_email(job.description), extract_phone(job.description)
        reason = f"casa em {len(hits)} qualificações ({', '.join(sorted(hits)[:5])})"
        scored.append(item | {"score": score, "reason": reason, "contact_email": email, "contact_phone": phone})

    scored.sort(key=lambda j: -j["score"])
    # `scored` guarda TODAS as pontuadas e `approved` só as que passam do corte.
    # Reaproveitar um nome só apagaria a melhor nota do conjunto completo, que é
    # justamente o número que explica uma rodada sem resultado.
    approved = [j for j in scored if j["score"] >= args.min_score]
    if args.top:
        approved = approved[: args.top]

    by_email = [j for j in approved if j["contact_email"]]
    manual = [j for j in approved if not j["contact_email"]]

    Path(args.out_email).write_text(json.dumps(by_email, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    Path(args.out_manual).write_text(json.dumps(manual, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if args.out_all:
        Path(args.out_all).write_text(json.dumps(approved, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # a melhor nota é o que distingue "não apareceu vaga" de "o corte está alto"
    melhor = max((j["score"] for j in scored), default=None)
    write_stats(Path(args.stats), avaliadas=len(items), aprovadas=len(approved),
                min_score=args.min_score, melhor_nota=melhor)

    print(f"Avaliadas:                 {len(items)}")
    print(f"Acima do corte ({args.min_score:>3}):      {len(approved)}")
    print(f"  candidatura por e-mail:  {len(by_email)} -> {args.out_email}")
    print(f"  candidatura manual:      {len(manual)} -> {args.out_manual}")
    if approved:
        print(f"\nTop {min(15, len(approved))} por compatibilidade:")
        for j in approved[:15]:
            print(f"  {j['score']:3}  {j['title'][:48]:48}  {j['company'][:24]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
