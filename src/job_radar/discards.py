"""Log TSV das vagas descartadas na rodada.

Serve para auditar se um regex de filtro está matando vaga boa: a contagem
agregada em `motivos` não mostra título/empresa/URL de cada caso.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_radar.fsutil import atomic_write_text
from job_radar.models import Job

HEADER = "timestamp\tsource\treason\tcompany\ttitle\turl"


def _cell(value: object) -> str:
    return str(value or "").replace("\t", " ").replace("\n", " ").replace("\r", " ")


def format_row(job: Job, reason: str, when: datetime | None = None) -> str:
    ts = (when or datetime.now()).isoformat(timespec="seconds")
    return "\t".join(
        [
            _cell(ts),
            _cell(job.source),
            _cell(reason),
            _cell(job.company),
            _cell(job.title),
            _cell(job.url),
        ]
    )


def write_discards(path: Path, rows: list[str], *, append: bool = False) -> None:
    """Escreve o TSV. `append` soma a um arquivo existente (header só se novo)."""
    path = Path(path)
    lines: list[str]
    if append and path.exists():
        existing = path.read_text(encoding="utf-8")
        # garante header uma vez só
        body = existing if existing.startswith(HEADER) else HEADER + "\n" + existing
        if not body.endswith("\n") and body:
            body += "\n"
        lines = [body.rstrip("\n"), *rows]
        atomic_write_text(path, "\n".join(lines) + "\n")
        return
    atomic_write_text(path, HEADER + "\n" + ("\n".join(rows) + "\n" if rows else ""))
