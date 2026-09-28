#!/usr/bin/env python3
"""Publica no Discord as vagas aprovadas e registra o envio.

Por padrão envia UMA mensagem por vaga, com pausa entre elas: o canal é para
leitura e candidatura uma a uma, e uma rajada de mensagens idênticas é tratada
como spam pelo Discord e ignorada por quem lê. Cada vaga é marcada como enviada
logo após o próprio POST, então uma interrupção no meio não perde nem repete o
que já saiu.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_radar.models import Job  # noqa: E402
from job_radar.report import chunk_embeds, job_to_embed  # noqa: E402
from job_radar.report import build_empty_embed  # noqa: E402
from job_radar.runstats import read_stats  # noqa: E402
from job_radar.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EMBEDS_PER_MESSAGE = 10  # limite do Discord


def load_env(path: Path) -> None:
    """Lê o .env sem dependência externa: o webhook é segredo e não entra no código."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# O Cloudflare do Discord responde 403 ao User-Agent padrão do urllib
# ("Python-urllib/3.x"). Um UA identificável é obrigatório, não cosmético.
USER_AGENT = os.getenv("USER_AGENT", "job-radar/0.1 (+https://github.com/topics/job-search)")


def post(webhook: str, payload: dict) -> str:
    """Posta e devolve o ID da mensagem criada.

    O `wait=true` é o que faz o Discord responder com o objeto da mensagem. Sem
    ele a resposta é vazia e a mensagem fica órfã: um webhook só consegue apagar
    o que postou se tiver guardado o ID, e não tem como listar o canal depois.
    """
    data = json.dumps(payload).encode("utf-8")
    url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8") or "{}")
    return str(body.get("id", ""))


def record_message_id(path: Path, message_id: str, title: str) -> None:
    """Guarda o ID para permitir apagar depois."""
    if not message_id:
        return
    log = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    log.append({"id": message_id, "title": title, "at": __import__("datetime").datetime.now().isoformat()})
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def should_notify_empty(items: list, notify_empty: bool) -> bool:
    """Se a rodada não tem nada a publicar, o canal deve saber disso.

    Sem este aviso, silêncio no canal é ambíguo: pode ser "não achou vaga" ou
    "a automação parou". Já custou dois dias de radar mudo passando por normal.
    """
    return bool(notify_empty) and not items


def main() -> int:
    load_env(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Envia vagas aprovadas ao Discord")
    ap.add_argument("--input", default=str(ROOT / "data" / "apply_manual.json"))
    ap.add_argument("--db", default=str(ROOT / "data" / "seen.db"))
    ap.add_argument("--webhook", default="")
    ap.add_argument("--dry-run", action="store_true", help="imprime o que enviaria, sem postar")
    ap.add_argument("--batch", action="store_true", help="agrupa várias vagas por mensagem")
    ap.add_argument("--delay", type=float, default=30.0, help="segundos entre mensagens (padrão 30)")
    ap.add_argument("--limit", type=int, default=0, help="envia no máximo N vagas nesta execução")
    ap.add_argument("--notify-empty", action="store_true",
                    help="publica um aviso quando a varredura não encontra nada")
    ap.add_argument("--stats", default=str(ROOT / "data" / "last_run.json"),
                    help="estatísticas da rodada, usadas no aviso de varredura vazia")
    args = ap.parse_args()

    webhook = args.webhook or os.getenv("DISCORD_WEBHOOK_URL", "")
    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not items:
        print("Nada aprovado para enviar.")
        if should_notify_empty(items, args.notify_empty) and webhook and not args.dry_run:
            post(webhook, {"embeds": [build_empty_embed(read_stats(Path(args.stats)))]})
            print("Aviso de varredura vazia publicado no canal.")
        return 0
    if not webhook and not args.dry_run:
        print("ERRO: defina DISCORD_WEBHOOK_URL ou use --dry-run", file=sys.stderr)
        return 1

    if args.limit:
        items = items[: args.limit]

    store = Store(Path(args.db))
    pairs: list[tuple[Job, dict]] = []
    for item in items:
        data = dict(item)
        score, reason = data.pop("score", 0), data.pop("reason", "")
        data.pop("fingerprint", None)
        data.pop("published_at", None)
        job = Job(**data)
        pairs.append((job, job_to_embed(job, score, reason, 320 if args.batch else 700)))

    prefix = "(dry-run) " if args.dry_run else ""

    if args.batch:
        for i, chunk in enumerate(chunk_embeds([e for _, e in pairs])):
            header = f"**{len(pairs)} vaga(s) compatíveis** nesta varredura" if i == 0 else None
            payload = {"embeds": chunk} | ({"content": header} if header else {})
            if args.dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
            else:
                message_id = post(webhook, payload)
                record_message_id(ROOT / "data" / "sent_messages.json", message_id, f"lote {i + 1}")
        if not args.dry_run:
            for job, _ in pairs:
                store.mark_sent(job)
        print(f"{prefix}{len(pairs)} vaga(s) em {len(chunk_embeds([e for _, e in pairs]))} mensagem(ns).")
        return 0

    total = len(pairs)
    for index, (job, embed) in enumerate(pairs, start=1):
        payload = {"embeds": [embed]}
        if args.dry_run:
            print(f"[{index}/{total}] {job.title[:60]} — {job.company[:30]}")
        else:
            message_id = post(webhook, payload)
            record_message_id(ROOT / "data" / "sent_messages.json", message_id, job.title)
            store.mark_sent(job)  # marca já: interrupção não repete o que saiu
            print(f"[{index}/{total}] enviada: {job.title[:60]} — {job.company[:30]}", flush=True)
            if index < total and args.delay > 0:
                time.sleep(args.delay)
    print(f"{prefix}{total} vaga(s) enviadas, uma por mensagem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
