"""Fixtures compartilhados: protege data/ de escrita acidental nos testes."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _snapshot_data() -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) por arquivo sob data/; ignora ausente."""
    if not DATA.is_dir():
        return {}
    out: dict[str, tuple[int, int]] = {}
    for path in DATA.iterdir():
        if path.is_file():
            st = path.stat()
            out[path.name] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(autouse=True, scope="session")
def _guard_data_dir_untouched():
    """Falha se qualquer teste alterar tamanho/mtime de data/*.

    Scripts sob teste devem receber --out/--db/--discards em tmp_path;
    gravar no data/ real polui o histórico e o TSV de descartes.
    """
    before = _snapshot_data()
    yield
    after = _snapshot_data()
    assert after == before, (
        "testes alteraram arquivos em data/: "
        f"antes={sorted(before.items())} depois={sorted(after.items())}"
    )
