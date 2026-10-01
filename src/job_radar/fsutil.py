"""Escrita atômica de arquivos de texto.

Um kill do cron no meio de um `write_text` deixa JSON truncado para a próxima
etapa. Escrever num temp na mesma pasta e `os.replace` garante que o leitor
só vê o arquivo completo ou o anterior.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _umask() -> int:
    """Lê o umask sem deixá-lo alterado (umask() seta e devolve o anterior)."""
    current = os.umask(0)
    os.umask(current)
    return current


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    """Grava `text` em `path` de forma atômica (temp + fsync + replace).

    Preserva o mode do arquivo existente; arquivo novo recebe 0o666 & ~umask.
    Sem isso, mkstemp (0600) + replace deixava JSON/TSV de 0644 como 0600.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        mode = dest.stat().st_mode & 0o777
    else:
        mode = 0o666 & ~_umask()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=dest.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
        os.chmod(dest, mode)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
