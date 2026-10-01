#!/usr/bin/env python3
"""Recalcula os fingerprints do histórico com o algoritmo atual.

Necessário sempre que a regra de identidade da vaga mudar: o histórico guarda o
hash, e um hash calculado por uma regra antiga nunca casa com a nova, o que faz
vagas já enviadas voltarem ao canal como se fossem novas. Como o banco guarda
título e empresa, dá para recalcular sem perder nada. Também preenche url_key
nas linhas antigas.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.identity import simhash, simhash_hex, url_key  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Recalcula fingerprints do histórico")
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # garante colunas novas antes de ler/gravar
    Store(Path(args.db))

    with closing(sqlite3.connect(args.db)) as conn:
        linhas = conn.execute(
            "SELECT fingerprint, source, title, company, url, sent_at, "
            "COALESCE(url_key, ''), COALESCE(simhash, '') FROM seen"
        ).fetchall()
        mudou = 0
        for antigo, source, title, company, url, sent_at, old_ukey, old_sh in linhas:
            job = Job(source=source, external_id="", title=title, company=company, url=url)
            novo = job.fingerprint
            new_ukey = url_key(url) or None
            # histórico não guarda descrição; preserva simhash já gravado
            new_sh = (old_sh or None) if not job.description else (
                simhash_hex(simhash(job.description)) or None
            )
            if (
                novo == antigo
                and (new_ukey or "") == (old_ukey or "")
                and (new_sh or "") == (old_sh or "")
            ):
                continue
            mudou += 1
            if args.dry_run:
                print(f"  {antigo} -> {novo}  url_key={new_ukey}  {title[:50]}")
                continue
            conn.execute("DELETE FROM seen WHERE fingerprint = ?", (antigo,))
            conn.execute(
                "INSERT OR REPLACE INTO seen "
                "(fingerprint, source, title, company, url, sent_at, url_key, simhash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (novo, source, title, company, url, sent_at, new_ukey, new_sh),
            )
        if not args.dry_run:
            conn.commit()

    print(f"{'(dry-run) ' if args.dry_run else ''}{mudou} de {len(linhas)} registros recalculados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
