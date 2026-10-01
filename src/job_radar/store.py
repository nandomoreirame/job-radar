"""Histórico do que já foi publicado, para não repetir vaga no canal."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from job_radar.identity import (
    company_key,
    parse_simhash_hex,
    simhash,
    simhash_hex,
    url_key,
)

if TYPE_CHECKING:
    from job_radar.models import Job

# Uma janela só: is_new e near-dup history antes divergiam (45 vs 90).
SEEN_WINDOW_DAYS = 45

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    fingerprint TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    url         TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    url_key     TEXT,
    simhash     TEXT
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_url_key ON seen(url_key)"
            )
            conn.commit()

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        """Bancos antigos ganham url_key/simhash sem perder linhas."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(seen)")}
        if "url_key" not in cols:
            conn.execute("ALTER TABLE seen ADD COLUMN url_key TEXT")
        if "simhash" not in cols:
            conn.execute("ALTER TABLE seen ADD COLUMN simhash TEXT")

    def seen_keys(
        self, window_days: int = SEEN_WINDOW_DAYS
    ) -> tuple[set[str], set[str]]:
        """Fingerprints e url_keys enviados dentro da janela (uma query por rodada).

        collect/ingest checam membership em memória; evita N conexões × 2 queries.
        """
        cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute(
                "SELECT fingerprint, url_key FROM seen WHERE sent_at > ?",
                (cutoff,),
            ).fetchall()
        fingerprints = {fp for fp, _ in rows if fp}
        url_keys = {uk for _, uk in rows if uk}
        return fingerprints, url_keys

    def is_new(
        self,
        job_or_fingerprint: str | Job,
        window_days: int = SEEN_WINDOW_DAYS,
        url: str = "",
    ) -> bool:
        """Vaga é nova se fingerprint E url_key (quando houver) estão fora da janela.

        Aceita string (fingerprint) por compatibilidade, ou um Job. Preferir
        `seen_keys` + membership em loops quentes (collect/ingest). A janela
        existe porque anúncio é republicado: sem ela, uma vaga some para sempre;
        com ela curta demais, o canal repete a mesma vaga toda semana.
        """
        if isinstance(job_or_fingerprint, str):
            fingerprint = job_or_fingerprint
            key = url_key(url) if url else ""
        else:
            job = job_or_fingerprint
            fingerprint = job.fingerprint
            key = url_key(job.url)

        cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM seen WHERE fingerprint = ? AND sent_at > ?",
                (fingerprint, cutoff),
            ).fetchone()
            if row is not None:
                return False
            if key:
                row = conn.execute(
                    "SELECT 1 FROM seen WHERE url_key = ? AND url_key != '' "
                    "AND sent_at > ?",
                    (key, cutoff),
                ).fetchone()
                if row is not None:
                    return False
        return True

    def mark_sent(self, job: Job) -> None:
        key = url_key(job.url)
        sh = simhash_hex(simhash(job.description))
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO seen "
                "(fingerprint, source, title, company, url, sent_at, url_key, simhash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.fingerprint,
                    job.source,
                    job.title,
                    job.company,
                    job.url,
                    datetime.now().isoformat(),
                    key or None,
                    sh or None,
                ),
            )
            conn.commit()

    def recent_simhashes(
        self, window_days: int = SEEN_WINDOW_DAYS
    ) -> list[tuple[int, str]]:
        """SimHashes não-nulos da janela, uma query por rodada (não por vaga).

        Devolve (simhash_int, company_key) para checagem de quase-duplicata
        contra o histórico sem query-in-loop.
        """
        cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute(
                "SELECT simhash, company FROM seen "
                "WHERE simhash IS NOT NULL AND simhash != '' AND sent_at > ?",
                (cutoff,),
            ).fetchall()
        out: list[tuple[int, str]] = []
        for raw, company in rows:
            value = parse_simhash_hex(raw)
            if value is None:
                continue
            out.append((value, company_key(company or "")))
        return out

    def count(self) -> int:
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
