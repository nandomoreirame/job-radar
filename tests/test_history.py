import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from history import rows  # noqa: E402

from job_radar.models import Job  # noqa: E402
from job_radar.store import Store  # noqa: E402


def seed(tmp_path, dias_atras: int):
    db = tmp_path / "t.db"
    store = Store(db)
    store.mark_sent(Job(source="gupy", external_id="1", title="Dev Sênior", company="Acme", url="u"))
    if dias_atras:
        with closing(sqlite3.connect(db)) as c:
            c.execute("UPDATE seen SET sent_at = datetime('now', ?)", (f"-{dias_atras} days",))
            c.commit()
    return db


def test_lista_tudo_sem_filtro(tmp_path):
    db = seed(tmp_path, 0)
    assert len(rows(db)) == 1


def test_filtra_por_janela_de_dias(tmp_path):
    # vaga enviada há 10 dias não aparece numa janela de 3 dias
    db = seed(tmp_path, 10)
    assert rows(db, days=3) == []
    assert len(rows(db, days=30)) == 1
