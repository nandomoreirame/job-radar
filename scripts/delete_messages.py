#!/usr/bin/env python3
"""Apaga mensagens que este webhook publicou, usando os IDs registrados.

Só funciona para mensagens enviadas depois que o registro de ID passou a
existir: o Discord não deixa um webhook listar o canal nem apagar o que não
consta no próprio histórico local.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = os.getenv("USER_AGENT", "job-radar/0.1 (+https://github.com/topics/job-search)")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def select_targets(
    entries: list[dict],
    last: int = 0,
    ids: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Divide o log em (apagar, manter).

    `ids` existe porque apagar por critério (vaga afirmativa, stack fora do
    perfil) escolhe mensagens no MEIO do log, não um sufixo dele.
    """
    if ids is not None:
        alvos = [e for e in entries if e.get("id") in ids]
        restantes = [e for e in entries if e.get("id") not in ids]
        return alvos, restantes
    if last:
        return entries[-last:], entries[:-last]
    return list(entries), []


def main() -> int:
    load_env(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Apaga mensagens publicadas pelo webhook")
    ap.add_argument("--log", default=str(ROOT / "data" / "sent_messages.json"))
    ap.add_argument("--last", type=int, default=0, help="apaga apenas as N últimas")
    ap.add_argument("--ids", default="", help="apaga apenas estes IDs (separados por vírgula)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    log_path = Path(args.log)
    if not webhook or not log_path.exists():
        print("Nada a apagar: webhook ausente ou nenhum envio registrado.", file=sys.stderr)
        return 1

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    ids = {i.strip() for i in args.ids.split(",") if i.strip()} if args.ids else None
    targets, remaining = select_targets(entries, args.last, ids)

    for entry in targets:
        url = f"{webhook}/messages/{entry['id']}"
        if args.dry_run:
            print(f"apagaria: {entry['title'][:60]}")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=20):
                print(f"apagada: {entry['title'][:60]}")
        except urllib.error.HTTPError as exc:
            print(f"falhou ({exc.code}): {entry['title'][:60]}", file=sys.stderr)

    if not args.dry_run:
        log_path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(targets)} mensagem(ns) processadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
