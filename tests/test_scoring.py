from job_radar.models import Job
from job_radar.scoring import score_job


def make(title, desc="", hint="remote"):
    return Job(source="gupy", external_id="1", title=title, company="Acme", url="u",
               description=desc, work_mode_hint=hint)


def test_vaga_de_ia_remota_com_muitas_skills_pontua_alto():
    job = make("Engenheiro de IA Sênior", "Python, AWS, Docker, TypeScript")
    hits = {"python", "aws", "docker", "typescript", "fastapi", "polars"}
    assert score_job(job, hits, hits) >= 80


def test_titulo_generico_com_poucas_skills_pontua_baixo():
    job = make("Analista de Sistemas", "Excel e rotinas administrativas", hint=None)
    assert score_job(job, set(), set()) < 30


def test_remoto_pontua_mais_que_hibrido():
    hits = {"python", "aws"}
    remoto = score_job(make("Engenheiro de Dados Sênior", hint="remote"), hits, hits)
    hibrido = score_job(make("Engenheiro de Dados Sênior", hint="hybrid"), hits, hits)
    assert remoto > hibrido


def test_stack_alheia_dominante_derruba_a_nota():
    # uma vaga que é essencialmente SAP não encaixa, mesmo citando Python de passagem
    desc = "Consultor SAP ABAP, módulo SAP MM, integração SAP. Python desejável."
    hits = {"python"}
    assert score_job(make("Desenvolvedor Sênior", desc), hits, hits) < 60


def test_nota_fica_no_intervalo():
    job = make("Staff AI Engineer", "Python AWS")
    hits = {f"skill{i}" for i in range(20)}
    assert 0 <= score_job(job, hits, hits) <= 100


def test_penalidade_por_idade_da_vaga():
    from datetime import datetime, timedelta

    hits = {"python", "aws", "docker", "typescript"}
    base = make("Engenheiro de Dados Sênior", "Python, AWS, Docker, TypeScript")
    fresca = score_job(base, hits, hits)

    velha = make("Engenheiro de Dados Sênior", "Python, AWS, Docker, TypeScript")
    velha.published_at = datetime.now() - timedelta(days=25)
    assert score_job(velha, hits, hits) == fresca - 5

    antiga = make("Engenheiro de Dados Sênior", "Python, AWS, Docker, TypeScript")
    antiga.published_at = datetime.now() - timedelta(days=40)
    assert score_job(antiga, hits, hits) == fresca - 10


def test_sem_published_at_nao_penaliza_idade():
    hits = {"python", "aws"}
    job = make("Engenheiro de Dados Sênior", "Python AWS")
    assert job.published_at is None
    # só garante que não explode; a nota base já é coberta nos outros testes
    assert score_job(job, hits, hits) >= 0
