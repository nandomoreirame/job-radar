#!/usr/bin/env python3
"""Injeta vagas coletadas fora dos crawlers (por exemplo, dos alertas de e-mail).

Existe para que vaga vinda de e-mail atravesse exatamente os mesmos filtros e a
mesma deduplicação das vagas de API. Sem isto, a skill teria que reimplementar as
regras de senioridade, modalidade e salário em prosa, e elas divergiriam com o
tempo.

Entrada: JSON (arquivo ou stdin) com uma lista de objetos contendo ao menos
title, company e url. Campos aceitos: description, location, work_mode_hint,
contact_email, contact_phone, source, published_at, other_locations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.discards import format_row, write_discards  # noqa: E402
from job_radar.filters import passes_hard_filters  # noqa: E402
from job_radar.fsutil import atomic_write_text  # noqa: E402
from job_radar.identity import url_key  # noqa: E402
from job_radar.models import Job, parse_published_at  # noqa: E402
from job_radar.profile import load_profile  # noqa: E402
from job_radar.store import SEEN_WINDOW_DAYS, Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CAMPOS = {
    "title", "company", "url", "description", "location", "work_mode_hint",
    "contact_email", "contact_phone", "source", "external_id", "published_at",
    "other_locations",
}


def to_job(raw: dict, default_source: str) -> Job:
    data = {k: v for k, v in raw.items() if k in CAMPOS}
    data.setdefault("source", default_source)
    data.setdefault("external_id", "")
    data["published_at"] = parse_published_at(data.get("published_at"))
    return Job(**data)


def main() -> int:
    ap = argparse.ArgumentParser(description="Injeta vagas externas no pipeline")
    ap.add_argument("--input", default="-", help="arquivo JSON ou - para stdin")
    ap.add_argument("--source", default="email", help="rótulo da origem")
    ap.add_argument("--profile", default=os.getenv("PROFILE_PATH", str(ROOT / "profile" / "profile.md")))
    ap.add_argument("--min-skills", type=int, default=2, help="e-mail traz descrição curta: exija menos")
    ap.add_argument("--out", default=str(ROOT / "data" / "candidates.json"))
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--merge", action="store_true", help="soma ao arquivo de saída em vez de substituir")
    ap.add_argument(
        "--discards",
        default=str(ROOT / "data" / "discarded.tsv"),
        help="TSV de descartes (sempre anexa; header só se o arquivo for novo)",
    )
    args = ap.parse_args()

    payload = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    entradas = json.loads(payload)
    if isinstance(entradas, dict):
        entradas = [entradas]

    _, skills = load_profile(Path(args.profile))
    store = Store(Path(args.db))
    seen_fps, seen_urls = store.seen_keys(window_days=SEEN_WINDOW_DAYS)

    existentes: list[dict] = []
    out = Path(args.out)
    if args.merge and out.exists():
        existentes = json.loads(out.read_text(encoding="utf-8"))
    vistos = {e.get("fingerprint") for e in existentes}

    aceitas, reprovadas, repetidas = [], 0, 0
    motivos: dict[str, int] = {}
    discard_rows: list[str] = []
    for raw in entradas:
        job = to_job(raw, args.source)
        ok, motivo = passes_hard_filters(job, skills, args.min_skills)
        if not ok:
            reprovadas += 1
            chave = motivo.split("(")[0].strip()
            motivos[chave] = motivos.get(chave, 0) + 1
            discard_rows.append(format_row(job, motivo))
            continue
        key = url_key(job.url)
        already = (
            job.fingerprint in seen_fps
            or job.fingerprint in vistos
            or (key in seen_urls if key else False)
        )
        if already:
            repetidas += 1
            discard_rows.append(format_row(job, "já enviada"))
            continue
        vistos.add(job.fingerprint)
        aceitas.append(asdict(job) | {"fingerprint": job.fingerprint})

    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out,
        json.dumps(existentes + aceitas, ensure_ascii=False, indent=2, default=str),
    )
    # Sempre anexa: sobrescrever apagaria o TSV que o collect gravou na mesma rodada.
    write_discards(Path(args.discards), discard_rows, append=True)

    print(f"Recebidas:   {len(entradas)}")
    print(f"Reprovadas:  {reprovadas}")
    for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
        print(f"   - {motivo}: {n}")
    print(f"Repetidas:   {repetidas}")
    print(f"ACEITAS:     {len(aceitas)}  -> {out} (total no arquivo: {len(existentes) + len(aceitas)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
