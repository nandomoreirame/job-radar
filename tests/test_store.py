import sqlite3
from contextlib import closing

from job_radar.identity import simhash, simhash_hex, url_key
from job_radar.models import Job
from job_radar.store import Store


def make_job(title="Dev Sênior", company="Acme", url="https://x.com/jobs/1"):
    return Job(source="gupy", external_id="1", title=title, company=company, url=url)


def test_vaga_inedita_e_nova(tmp_path):
    store = Store(tmp_path / "t.db")
    assert store.is_new(make_job().fingerprint) is True


def test_vaga_ja_enviada_nao_repete(tmp_path):
    store = Store(tmp_path / "t.db")
    job = make_job()
    store.mark_sent(job)
    assert store.is_new(job.fingerprint) is False


def test_mesma_vaga_em_fontes_diferentes_conta_como_uma(tmp_path):
    # agregadores republicam o mesmo anúncio: empresa+título é o que identifica
    store = Store(tmp_path / "t.db")
    store.mark_sent(make_job())
    outra_fonte = Job(
        source="linkedin", external_id="99", title="Dev Sênior", company="Acme", url="https://y.com/2"
    )
    assert store.is_new(outra_fonte.fingerprint) is False


def test_volta_a_ser_nova_depois_da_janela(tmp_path):
    store = Store(tmp_path / "t.db")
    job = make_job()
    store.mark_sent(job)
    # janela de 0 dia: qualquer envio já está fora dela
    assert store.is_new(job.fingerprint, window_days=0) is True


def test_fingerprint_e_estavel_para_a_mesma_vaga():
    """Trava o algoritmo de identidade.

    Se este teste quebrar, a regra de fingerprint mudou e o histórico existente
    deixou de casar: rode scripts/migrate_fingerprints.py antes de publicar,
    senão toda vaga já enviada volta ao canal como novidade.
    """
    job = Job(
        source="gupy", external_id="1", title="Engenheiro de Dados Sênior",
        company="Acme Ltda", url="u",
    )
    assert job.fingerprint == Job(
        source="outra", external_id="2", title="Engenheiro de Dados Sênior",
        company="Acme Ltda", url="v",
    ).fingerprint
    # pontuação, caixa e sufixo jurídico não alteram a identidade
    assert job.fingerprint == Job(
        source="gupy", external_id="3", title="ENGENHEIRO DE DADOS SÊNIOR!",
        company="acme ltda", url="w",
    ).fingerprint


def test_mesma_url_com_tracking_conta_como_ja_enviada(tmp_path):
    store = Store(tmp_path / "t.db")
    job = make_job(url="https://boards.example.com/jobs/42")
    store.mark_sent(job)
    clone = make_job(
        title="Outro Título Totalmente Diferente",
        company="Outra Empresa",
        url="https://boards.example.com/jobs/42?utm_source=li",
    )
    assert store.is_new(clone.fingerprint, url=clone.url) is False


def test_is_new_aceita_job_direto(tmp_path):
    store = Store(tmp_path / "t.db")
    job = make_job()
    store.mark_sent(job)
    assert store.is_new(job) is False


def test_mark_sent_grava_url_key_e_simhash(tmp_path):
    store = Store(tmp_path / "t.db")
    desc = ("Python AWS Docker Kubernetes TypeScript React FastAPI dados. " * 10)
    job = make_job()
    job.description = desc
    store.mark_sent(job)
    with closing(sqlite3.connect(tmp_path / "t.db")) as conn:
        row = conn.execute("SELECT url_key, simhash FROM seen").fetchone()
    assert row[0] == url_key(job.url)
    assert row[1] == simhash_hex(simhash(desc))


def test_banco_antigo_sem_colunas_novas_recebe_migracao(tmp_path):
    db = tmp_path / "old.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "CREATE TABLE seen (fingerprint TEXT PRIMARY KEY, source TEXT, "
            "title TEXT, company TEXT, url TEXT, sent_at TEXT)"
        )
        conn.execute(
            "INSERT INTO seen VALUES ('abc','gupy','Dev','Acme','https://x','2026-01-01')"
        )
        conn.commit()
    store = Store(db)
    assert store.count() == 1
    with closing(sqlite3.connect(db)) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(seen)")}
    assert "url_key" in cols and "simhash" in cols


def test_recent_simhashes_carrega_lote_da_janela(tmp_path):
    store = Store(tmp_path / "t.db")
    desc = ("Python AWS Docker Kubernetes TypeScript React FastAPI dados. " * 10)
    job = make_job(company="Consultoria X")
    job.description = desc
    store.mark_sent(job)
    from job_radar.store import SEEN_WINDOW_DAYS

    rows = store.recent_simhashes(window_days=SEEN_WINDOW_DAYS)
    assert len(rows) == 1
    assert rows[0][0] == simhash(desc)
    assert rows[0][1] == "consultoria x"


def test_seen_keys_devolve_fingerprints_e_url_keys_da_janela(tmp_path):
    store = Store(tmp_path / "t.db")
    job = make_job(url="https://boards.example.com/jobs/42")
    store.mark_sent(job)
    fps, urls = store.seen_keys()
    assert job.fingerprint in fps
    assert url_key(job.url) in urls


def test_collect_style_seen_keys_faz_queries_constantes(tmp_path, monkeypatch):
    # is_new abria conexão e até 2 queries por vaga; seen_keys resolve em lote.
    import sqlite3

    store = Store(tmp_path / "t.db")
    for i in range(5):
        store.mark_sent(make_job(title=f"Dev {i}", url=f"https://x.com/jobs/{i}"))

    connects = {"n": 0}
    real_connect = sqlite3.connect

    def counting_connect(*a, **k):
        connects["n"] += 1
        return real_connect(*a, **k)

    monkeypatch.setattr("job_radar.store.sqlite3.connect", counting_connect)
    fps, urls = store.seen_keys()
    assert connects["n"] == 1
    jobs = [make_job(title=f"Dev {i}", url=f"https://x.com/jobs/{i}") for i in range(5)]
    # checagem em memória: sem nova query por vaga
    before = connects["n"]
    for job in jobs:
        key = url_key(job.url)
        assert job.fingerprint in fps or (key and key in urls)
    assert connects["n"] == before


def test_seen_window_days_compartilhado():
    from job_radar.store import SEEN_WINDOW_DAYS

    assert SEEN_WINDOW_DAYS == 45
