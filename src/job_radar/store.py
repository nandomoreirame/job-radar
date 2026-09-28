"""Histórico do que já foi publicado, para não repetir vaga no canal."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    fingerprint TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    url         TEXT NOT NULL,
    sent_at     TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(SCHEMA)

    def is_new(self, fingerprint: str, window_days: int = 45) -> bool:
        """Vaga é nova se nunca foi enviada ou se o envio saiu da janela.

        A janela existe porque anúncio é republicado: sem ela, uma vaga some para
        sempre; com ela curta demais, o canal repete a mesma vaga toda semana.
        """
        cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT sent_at FROM seen WHERE fingerprint = ? AND sent_at > ?", (fingerprint, cutoff)
            ).fetchone()
        return row is None

    def mark_sent(self, job) -> None:  # noqa: ANN001 (Job, evitando import circular)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO seen VALUES (?, ?, ?, ?, ?, ?)",
                (job.fingerprint, job.source, job.title, job.company, job.url, datetime.now().isoformat()),
            )
            conn.commit()

    def count(self) -> int:
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
