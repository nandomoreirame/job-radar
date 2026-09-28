from datetime import datetime, timedelta

from job_radar.models import Job
from job_radar.store import Store


def make_job(title="Dev Sênior", company="Acme"):
    return Job(source="gupy", external_id="1", title=title, company=company, url="https://x")


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
    outra_fonte = Job(source="linkedin", external_id="99", title="Dev Sênior", company="Acme", url="https://y")
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
    job = Job(source="gupy", external_id="1", title="Engenheiro de Dados Sênior", company="Acme Ltda", url="u")
    assert job.fingerprint == Job(
        source="outra", external_id="2", title="Engenheiro de Dados Sênior", company="Acme Ltda", url="v"
    ).fingerprint
    # pontuação e caixa não alteram a identidade
    assert job.fingerprint == Job(
        source="gupy", external_id="3", title="ENGENHEIRO DE DADOS SÊNIOR!", company="acme ltda", url="w"
    ).fingerprint
