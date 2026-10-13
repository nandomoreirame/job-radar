"""Conector InHire contra respostas reais gravadas (Olist)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from job_radar.health import SourceHealth
from job_radar.sources.inhire import (
    apply_detail,
    country_from_location,
    fetch_inhire,
    parse_listing,
)

FIX = Path(__file__).parent / "fixtures"
PAGE = json.loads((FIX / "inhire_page.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIX / "inhire_job.json").read_text(encoding="utf-8"))
FIRST = PAGE["jobsPage"][0]


def test_listagem_mapeia_campos_basicos():
    job = parse_listing(FIRST, slug="olist", company="Olist")
    assert job.source == "inhire"
    assert job.external_id == FIRST["jobId"]
    assert job.title == "Analista de Dados e Negócios Sênior | Financial Services"
    assert job.company == "Olist"
    assert job.url == f"https://olist.inhire.app/vagas/{FIRST['jobId']}"
    assert job.work_mode_hint == "hybrid"
    assert job.location == "São Paulo, SP"
    assert job.description == ""  # a listagem não traz descrição


def test_modalidades_da_inhire():
    modes = {
        item["workplaceType"]: parse_listing(item, slug="olist", company="Olist").work_mode_hint
        for item in PAGE["jobsPage"]
    }
    assert modes == {"Hybrid": "hybrid", "On-site": "onsite", "Remote": "remote"}


def test_pais_vem_do_ultimo_segmento_da_localizacao():
    # A InHire manda "Cidade, UF, BR"; sem o país explícito o gate recusava
    # "Osasco, SP" e "Bento Gonçalves, RS", que não estão na lista de cidades.
    assert country_from_location("Osasco, SP, BR") == "BR"
    assert country_from_location("BR") == "BR"
    assert country_from_location("Lisboa, PT") == "PT"
    assert country_from_location("") == ""
    assert country_from_location("São Paulo") == ""


def test_detalhe_preenche_descricao_e_data():
    job = apply_detail(parse_listing(FIRST, slug="olist", company="Olist"), DETAIL)
    assert "Olist" in job.description
    assert "<p" not in job.description
    assert job.published_at == datetime(2026, 9, 24, 14, 45, 38, 105000, tzinfo=UTC)


def _fake_get_json(calls):
    def fake(url, **kwargs):
        calls.append((url, kwargs.get("headers") or {}))
        if url.endswith("/pages"):
            return PAGE
        return DETAIL

    return fake


def test_fetch_detalha_so_o_que_keep_aprova(monkeypatch):
    calls: list = []
    monkeypatch.setattr("job_radar.sources.inhire.get_json", _fake_get_json(calls))
    monkeypatch.setattr("job_radar.sources.inhire.time.sleep", lambda _s: None)
    health = SourceHealth(name="inhire")

    jobs = fetch_inhire(
        {"olist": "Olist"},
        health=health,
        keep=lambda job: job.external_id == FIRST["jobId"],
    )

    assert [j.external_id for j in jobs] == [FIRST["jobId"]]
    assert jobs[0].description
    assert all(h.get("X-Tenant") == "olist" for _, h in calls)
    # uma listagem + um detalhe: o keep evita requisição por anúncio
    assert len(calls) == 2
    assert calls[1][0].endswith(f"/pages/{FIRST['jobId']}")
    assert health.ok == 2
    # health conta a listagem antes do keep (mesma política da Sólides)
    assert health.jobs == len(PAGE["jobsPage"])


def test_fetch_sem_keep_detalha_tudo(monkeypatch):
    calls: list = []
    monkeypatch.setattr("job_radar.sources.inhire.get_json", _fake_get_json(calls))
    monkeypatch.setattr("job_radar.sources.inhire.time.sleep", lambda _s: None)

    jobs = fetch_inhire({"olist": "Olist"})

    assert len(jobs) == len(PAGE["jobsPage"])
    assert len(calls) == 1 + len(PAGE["jobsPage"])


def test_vaga_estrangeira_nao_passa_o_gate(monkeypatch):
    page = {
        "tenantName": "Olist",
        "jobsPage": [
            {"jobId": "pt-1", "displayName": "Engenheiro", "workplaceType": "Hybrid",
             "location": "Lisboa, PT"},
        ],
    }
    monkeypatch.setattr("job_radar.sources.inhire.get_json", lambda url, **kw: page)
    health = SourceHealth(name="inhire")

    assert fetch_inhire({"olist": "Olist"}, health=health) == []
    assert health.foreign == 1


def test_falha_na_listagem_registra_erro_e_segue(monkeypatch):
    def fake(url, **kwargs):
        if kwargs["headers"]["X-Tenant"] == "quebrado":
            raise OSError("404")
        return {"tenantName": "Cora", "jobsPage": []}

    monkeypatch.setattr("job_radar.sources.inhire.get_json", fake)
    health = SourceHealth(name="inhire")

    assert fetch_inhire({"quebrado": "Quebrado", "cora": "Cora"}, health=health) == []
    assert health.ok == 1
    assert health.errors and "quebrado" in health.errors[0]


def test_falha_no_detalhe_descarta_a_vaga(monkeypatch):
    def fake(url, **kwargs):
        if url.endswith("/pages"):
            return {"tenantName": "Olist", "jobsPage": [FIRST]}
        raise OSError("timeout")

    monkeypatch.setattr("job_radar.sources.inhire.get_json", fake)
    monkeypatch.setattr("job_radar.sources.inhire.time.sleep", lambda _s: None)
    health = SourceHealth(name="inhire")

    # sem descrição a vaga reprovaria no filtro de qualificações de qualquer jeito
    assert fetch_inhire({"olist": "Olist"}, health=health) == []
    assert health.errors


def test_payload_sem_jobs_page_e_contrato_quebrado(monkeypatch):
    monkeypatch.setattr("job_radar.sources.inhire.get_json", lambda url, **kw: {"message": "x"})
    health = SourceHealth(name="inhire")

    assert fetch_inhire({"olist": "Olist"}, health=health) == []
    assert health.parse_failures == 1


def test_nome_configurado_igual_ao_slug_usa_o_nome_do_tenant(monkeypatch):
    # ATS_BOARDS sem nome ("inhire:olist") cai no slug; o payload tem o nome certo
    monkeypatch.setattr("job_radar.sources.inhire.get_json", _fake_get_json([]))
    monkeypatch.setattr("job_radar.sources.inhire.time.sleep", lambda _s: None)

    jobs = fetch_inhire({"olist": "olist"})

    assert jobs and all(j.company == "Olist" for j in jobs)
