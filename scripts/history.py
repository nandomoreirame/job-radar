#!/usr/bin/env python3
"""Consulta o histórico de vagas já enviadas ao Discord.

O banco em data/seen.db é a memória que impede repetir vaga entre rodadas. Este
script existe para torná-la legível: sem ele, a única forma de saber o que já foi
enviado é abrir o SQLite na mão.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.models import Job  # noqa: E402

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


def audit(db: Path) -> dict:
    """Relatório somente-leitura da saúde do histórico.

    Detecta (a) url_keys enviadas sob mais de um fingerprint, (b) fingerprints
    que não batem com a regra atual (migração pendente) e (c) totais.
    """
    with closing(sqlite3.connect(db)) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(seen)")}
        has_url_key = "url_key" in cols
        select = "fingerprint, title, company, url"
        if has_url_key:
            select += ", url_key"
        linhas = conn.execute(f"SELECT {select} FROM seen").fetchall()

    by_url: dict[str, set[str]] = defaultdict(set)
    desatualizados = 0
    for row in linhas:
        if has_url_key:
            fp, title, company, url, ukey = row
        else:
            fp, title, company, url = row
            ukey = ""
        atual = Job(
            source="audit", external_id="", title=title or "", company=company or "", url=url or ""
        ).fingerprint
        if atual != fp:
            desatualizados += 1
        if ukey:
            by_url[ukey].add(fp)

    colisoes = sum(1 for fps in by_url.values() if len(fps) > 1)
    return {
        "total": len(linhas),
        "url_keys_colisao": colisoes,
        "fingerprints_desatualizados": desatualizados,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Histórico de vagas enviadas")
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--days", type=int, default=0, help="só os últimos N dias (0 = tudo)")
    ap.add_argument("--export", default="", help="escreve um markdown no caminho indicado")
    ap.add_argument(
        "--audit",
        action="store_true",
        help="relatório de colisões de url_key e fingerprints desatualizados (não altera nada)",
    )
    args = ap.parse_args()

    if args.audit:
        report = audit(Path(args.db))
        print(f"Total de registros:              {report['total']}")
        print(f"url_keys com >1 fingerprint:     {report['url_keys_colisao']}")
        print(f"fingerprints desatualizados:     {report['fingerprints_desatualizados']}")
        if report["fingerprints_desatualizados"]:
            print("  (rode scripts/migrate_fingerprints.py para recalcular)")
        return 0

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
