"""Conector da Sólides: listagem no payload RSC + descrição no JSON-LD."""

import json
from pathlib import Path

from job_radar.sources.solides import (
    listing_from_page,
    parse_jobposting,
    parse_listing,
)

FIX = Path(__file__).parent / "fixtures"
PAGINA = json.loads((FIX / "solides_listing.json").read_text(encoding="utf-8"))
PRIMEIRA = PAGINA["data"][0]


def test_mapeia_campos_da_listagem():
    job = parse_listing(PRIMEIRA)
    assert job.source == "solides"
    assert job.external_id == "926052"
    assert job.title == "DESENVOLVEDOR DE HARDWARE SR"
    assert job.company == "HIT TECNOLOGIA LTDA"
    assert job.location == "Campinas, SP"


def test_monta_url_do_portal_e_ignora_o_redirect_quebrado():
    # a fonte devolve redirectLink="https://hwit./vacancies/926052", sem domínio,
    # e o subdomínio da empresa responde 200 com página vazia. Só o portal serve.
    job = parse_listing(PRIMEIRA)
    assert job.url == "https://vagas.solides.com.br/vaga/926052"
    assert "vacancies" not in job.url


def test_traduz_modalidade_declarada_pela_fonte():
    modos = {parse_listing(v).external_id: parse_listing(v).work_mode_hint for v in PAGINA["data"]}
    assert modos["926052"] == "hybrid"   # jobType "hibrido"
    assert modos["926088"] == "onsite"   # jobType "presencial"


def test_leva_o_contrato_para_as_tags():
    assert "CLT" in parse_listing(PRIMEIRA).tags
    assert "PJ" in parse_listing(PAGINA["data"][2]).tags


def test_marca_vaga_afirmativa_declarada_pela_fonte():
    # a Sólides expõe isso estruturalmente; é mais confiável que ler o texto
    bruto = dict(PRIMEIRA, affirmative=[{"id": 1, "name": "Mulheres"}])
    assert "vaga afirmativa" in parse_listing(bruto).tags
    bruto_pcd = dict(PRIMEIRA, pcdOnly=True)
    assert "vaga afirmativa" in parse_listing(bruto_pcd).tags
    assert "vaga afirmativa" not in parse_listing(PRIMEIRA).tags


def test_extrai_descricao_do_json_ld():
    html = (FIX / "solides_jobposting.html").read_text(encoding="utf-8")
    desc = parse_jobposting(html)
    assert len(desc) > 500
    assert "Desenvolvedor de Hardware" in desc


def test_pagina_sem_json_ld_devolve_vazio_sem_quebrar():
    assert parse_jobposting("<html><body>indisponível</body></html>") == ""


def test_listing_from_page_devolve_meta_e_vagas():
    meta, jobs = listing_from_page(json.dumps({"initialData": PAGINA}))
    assert meta["totalPages"] == PAGINA["totalPages"]
    assert len(jobs) == 3
    assert jobs[0].external_id == "926052"


def test_blob_sem_dados_nao_quebra():
    meta, jobs = listing_from_page("payload qualquer sem initialData")
    assert meta == {} and jobs == []


# --- frescor: a listagem vai até 2023 no fim da paginação ---

from datetime import date, datetime  # noqa: E402

from job_radar.sources.solides import DEFAULT_MAX_AGE_DAYS, is_fresh  # noqa: E402


def test_preenche_a_data_de_publicacao():
    job = parse_listing(PRIMEIRA)
    assert job.published_at is not None
    assert job.published_at.date() == datetime.fromisoformat(PRIMEIRA["createdAt"]).date()


def test_descarta_vaga_mais_velha_que_a_janela():
    antiga = parse_listing(dict(PRIMEIRA, createdAt="2023-04-03"))
    assert not is_fresh(antiga, hoje=date(2026, 9, 23))


def test_mantem_vaga_dentro_da_janela():
    nova = parse_listing(dict(PRIMEIRA, createdAt="2026-09-01"))
    assert is_fresh(nova, hoje=date(2026, 9, 23))


def test_vaga_no_limite_exato_da_janela_e_mantida():
    limite = date(2026, 9, 23).toordinal() - DEFAULT_MAX_AGE_DAYS
    job = parse_listing(dict(PRIMEIRA, createdAt=date.fromordinal(limite).isoformat()))
    assert is_fresh(job, hoje=date(2026, 9, 23))


def test_sem_data_a_vaga_e_mantida():
    # ausência de data não é prova de vaga velha: descartar perderia anúncio bom
    sem_data = parse_listing({k: v for k, v in PRIMEIRA.items() if k != "createdAt"})
    assert sem_data.published_at is None
    assert is_fresh(sem_data, hoje=date(2026, 9, 23))
