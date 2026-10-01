import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from history import audit, rows  # noqa: E402

from job_radar.identity import url_key  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.store import Store  # noqa: E402


def seed(tmp_path, dias_atras: int):
    db = tmp_path / "t.db"
    store = Store(db)
    store.mark_sent(
        Job(source="gupy", external_id="1", title="Dev Sênior", company="Acme", url="https://x/1")
    )
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


def test_audit_detecta_url_key_com_multiplos_fingerprints(tmp_path):
    db = tmp_path / "a.db"
    store = Store(db)
    store.mark_sent(
        Job(source="gupy", external_id="1", title="Dev A", company="Acme",
            url="https://example.com/job/1")
    )
    # segunda linha com a mesma url_key mas fingerprint diferente (simula legado)
    key = url_key("https://example.com/job/1?utm_source=x")
    with closing(sqlite3.connect(db)) as c:
        c.execute(
            "INSERT OR REPLACE INTO seen "
            "(fingerprint, source, title, company, url, sent_at, url_key, simhash) "
            "VALUES (?, 'gupy', 'Dev B', 'Outra', 'https://example.com/job/1?utm_source=x', "
            "datetime('now'), ?, NULL)",
            ("ffffffffffff0001", key),
        )
        c.commit()
    report = audit(db)
    assert report["url_keys_colisao"] >= 1
    assert report["total"] == 2


def test_audit_detecta_fingerprint_desatualizado(tmp_path):
    db = tmp_path / "b.db"
    store = Store(db)
    job = Job(source="gupy", external_id="1", title="Dev Sênior", company="Acme",
              url="https://example.com/j")
    store.mark_sent(job)
    with closing(sqlite3.connect(db)) as c:
        c.execute("UPDATE seen SET fingerprint = 'deadbeefdeadbeef'")
        c.commit()
    report = audit(db)
    assert report["fingerprints_desatualizados"] == 1
