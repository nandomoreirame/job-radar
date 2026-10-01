"""Configuração vem do ambiente: o repositório não carrega dados de ninguém."""

from job_radar.settings import blocked_companies, commute_cities, max_job_age_days, min_salary


def test_sem_configuracao_nao_ha_piso_salarial(monkeypatch):
    # default neutro: um clone do projeto não herda a pretensão de outra pessoa
    monkeypatch.delenv("MIN_SALARY_PJ", raising=False)
    monkeypatch.delenv("MIN_SALARY_CLT", raising=False)
    assert min_salary("PJ") == 0
    assert min_salary("CLT") == 0


def test_le_o_piso_por_tipo_de_contrato(monkeypatch):
    monkeypatch.setenv("MIN_SALARY_PJ", "14000")
    monkeypatch.setenv("MIN_SALARY_CLT", "12000")
    assert min_salary("PJ") == 14000
    assert min_salary("CLT") == 12000
    assert min_salary(None) == 12000  # contrato não declarado usa o piso de CLT


def test_valor_invalido_nao_derruba_a_varredura(monkeypatch):
    monkeypatch.setenv("MIN_SALARY_PJ", "catorze mil")
    assert min_salary("PJ") == 0


def test_sem_cidades_configuradas_o_conjunto_e_vazio(monkeypatch):
    monkeypatch.delenv("COMMUTE_CITIES", raising=False)
    assert commute_cities() == frozenset()


def test_cidades_sao_normalizadas(monkeypatch):
    # o anúncio escreve "São Paulo"; a comparação precisa bater sem acento
    monkeypatch.setenv("COMMUTE_CITIES", "São Paulo, Barueri , OSASCO")
    assert commute_cities() == frozenset({"sao paulo", "barueri", "osasco"})


def test_entradas_vazias_sao_descartadas(monkeypatch):
    monkeypatch.setenv("COMMUTE_CITIES", "Cotia,,  ,Jandira")
    assert commute_cities() == frozenset({"cotia", "jandira"})


def test_max_job_age_default_desliga_o_filtro(monkeypatch):
    monkeypatch.delenv("MAX_JOB_AGE_DAYS", raising=False)
    assert max_job_age_days() == 0


def test_max_job_age_le_inteiro(monkeypatch):
    monkeypatch.setenv("MAX_JOB_AGE_DAYS", "45")
    assert max_job_age_days() == 45


def test_blocked_companies_usa_company_key(monkeypatch):
    monkeypatch.setenv("BLOCKED_COMPANIES", "Acme Ltda, Outra S.A.")
    assert blocked_companies() == frozenset({"acme", "outra"})
