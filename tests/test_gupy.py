"""Conector Gupy: página de busca do portal (payload Next.js)."""

from pathlib import Path

from job_radar.health import SourceHealth
from job_radar.sources.gupy import fetch_gupy, listing_from_page, parse_job

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "gupy_search.html").read_text(encoding="utf-8")


def test_listing_from_page_extrai_jobs_do_next_data():
    items = listing_from_page(HTML)
    assert len(items) == 12
    first = items[0]
    assert first["id"] == 12561405
    assert first["name"] == "Data Manager (Data Engineer)"
    assert first["careerPageName"] == "Cadastra"
    assert first["city"] == "São Paulo"
    assert first["workplaceType"] == "hybrid"


def test_listing_from_page_sem_script_devolve_vazio():
    assert listing_from_page("<html><body>sem dados</body></html>") == []
    assert listing_from_page("") == []


def test_listing_from_page_json_quebrado_devolve_vazio():
    html = '<script id="__NEXT_DATA__" type="application/json">{não-json}</script>'
    assert listing_from_page(html) == []


def test_parse_job_mapeia_campos_do_portal():
    items = listing_from_page(HTML)
    job = parse_job(items[0])
    assert job.source == "gupy"
    assert job.external_id == "12561405"
    assert job.title == "Data Manager (Data Engineer)"
    assert job.company == "Cadastra"
    assert job.location == "São Paulo, São Paulo"  # city + state do portal

    assert job.work_mode_hint == "hybrid"
    assert job.url


def test_fetch_gupy_usa_portal_e_grava_health(monkeypatch):
    seen: list[str] = []

    def fake_get(url, **kwargs):
        seen.append(url)
        return HTML.encode("utf-8")

    monkeypatch.setattr("job_radar.sources.gupy.get", fake_get)
    health = SourceHealth(name="gupy")
    jobs = fetch_gupy("data engineer", health=health)
    assert len(jobs) == 12
    assert jobs[0].external_id == "12561405"
    # o portal só entende o termo no PATH ("/job-search/term=..."). Com "?term=" ele
    # devolve a página de busca vazia, sem erro: foi assim que a fonte zerou ao vivo
    assert seen[0] == "https://portal.gupy.io/job-search/term=data%20engineer"
    assert health.ok == 1
    assert health.jobs == 12


def test_fetch_gupy_payload_ausente_grava_erro(monkeypatch):
    monkeypatch.setattr(
        "job_radar.sources.gupy.get",
        lambda url, **kw: b"<html>sem next data</html>",
    )
    health = SourceHealth(name="gupy")
    jobs = fetch_gupy("python", health=health)
    assert jobs == []
    assert health.ok == 1  # HTTP ok
    assert health.requests == 1  # payload ausente não é uma segunda requisição
    assert any("payload ausente" in e for e in health.errors)
    # respondeu e não trouxe nada legível: é contrato quebrado, não "sem vagas"
    assert health.status == "degradada"
