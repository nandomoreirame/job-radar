#!/usr/bin/env python3
"""Consulta o histórico de vagas já enviadas ao Discord.

O banco em data/seen.db é a memória que impede repetir vaga entre rodadas. Este
script existe para torná-la legível: sem ele, a única forma de saber o que já foi
enviado é abrir o SQLite na mão.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


SELECT_COLUMNS = "SELECT sent_at, source, company, title, url FROM seen"


def rows(db: Path, days: int | None = None) -> list[tuple]:
    """Histórico ordenado do mais recente para o mais antigo."""
    if days:
        query = f"{SELECT_COLUMNS} WHERE sent_at > datetime('now', ?) ORDER BY sent_at DESC"
        params: tuple = (f"-{days} days",)
    else:
        query = f"{SELECT_COLUMNS} ORDER BY sent_at DESC"
        params = ()
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(query, params).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description="Histórico de vagas enviadas")
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--days", type=int, default=0, help="só os últimos N dias (0 = tudo)")
    ap.add_argument("--export", default="", help="escreve um markdown no caminho indicado")
    args = ap.parse_args()

    data = rows(Path(args.db), args.days or None)
    if not data:
        print("Nenhuma vaga enviada ainda.")
        return 0

    por_fonte = Counter(r[1] for r in data)
    por_dia = Counter(r[0][:10] for r in data)

    print(f"{len(data)} vaga(s) já enviadas ao Discord")
    print("\nPor fonte:")
    for fonte, n in por_fonte.most_common():
        print(f"  {fonte:24} {n:3}")
    print("\nPor dia:")
    for dia, n in sorted(por_dia.items(), reverse=True)[:10]:
        print(f"  {dia}  {n:3}")

    if args.export:
        lines = [
            "# Histórico de vagas enviadas",
            "",
            f"Atualizado em {datetime.now():%d/%m/%Y %H:%M}. {len(data)} vagas no total.",
            "",
            "Estas vagas não voltam ao Discord por 45 dias a partir da data de envio.",
            "",
            "| Data | Fonte | Empresa | Vaga |",
            "|---|---|---|---|",
        ]
        for sent_at, source, company, title, url in data:
            empresa = company or "(não informada)"
            titulo = f"[{title}]({url})" if url else title
            lines.append(f"| {sent_at[:10]} | {source} | {empresa} | {titulo} |")
        Path(args.export).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nExportado para {args.export}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
