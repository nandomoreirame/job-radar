"""Conector Greenhouse contra fixture real (QuintoAndar)."""

import json
from pathlib import Path

from job_radar.sources.greenhouse import fetch_greenhouse, parse_job

FIX = Path(__file__).parent / "fixtures"
BOARD = json.loads((FIX / "greenhouse_board.json").read_text(encoding="utf-8"))
JOBS = BOARD["jobs"]


def _by_id(job_id: int) -> dict:
    return next(j for j in JOBS if j["id"] == job_id)


def test_remove_prefixo_da_empresa_no_titulo():
    job = parse_job(_by_id(4023115009), "quintoandar")
    assert job.title == "Staff Data Engineer"
    assert job.company == "Grupo QuintoAndar"


def test_prefixo_sem_espaco_ao_redor_da_barra():
    job = parse_job(_by_id(4362525009), "quintoandar")
    assert job.title == "Especialista em Dados e Estratégia"


def test_content_duplamente_escapado_vira_texto():
    job = parse_job(_by_id(4362525009), "quintoandar")
    assert "<" not in job.description
    assert "Grupo QuintoAndar" in job.description or "ecossistema" in job.description.casefold()


def test_normaliza_local_sao_paulo():
    job = parse_job(_by_id(4023115009), "quintoandar")
    assert job.location == "São Paulo, SP"


def test_local_brasil_sozinho():
    job = parse_job(_by_id(4321369009), "quintoandar")
    assert job.location == "Brasil"


def test_url_e_data_de_publicacao():
    job = parse_job(_by_id(4023115009), "quintoandar")
    assert job.url.startswith("https://job-boards.greenhouse.io/quintoandar/")
    assert job.published_at is not None
    assert job.source == "greenhouse"


def test_hybrid_no_location_name_usa_office(monkeypatch):
    # boards colocam "Hybrid"/"Remote" em location.name e a cidade só em offices
    bruto = dict(
        _by_id(4023115009),
        location={"name": "Remote"},
        offices=[{"location": "São Paulo, São Paulo, Brazil"}],
    )
    job = parse_job(bruto, "quintoandar")
    assert job.location == "São Paulo, SP"
    assert job.work_mode_hint == "remote"


def test_fetch_aplica_country_gate_e_conta_foreign(monkeypatch):
    from job_radar.health import SourceHealth

    calls: list[str] = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        return BOARD

    monkeypatch.setattr("job_radar.sources._ats.get_json", fake_get_json)
    health = SourceHealth(name="greenhouse")
    jobs = fetch_greenhouse({"quintoandar": "Grupo QuintoAndar"}, health=health)

    assert calls and "quintoandar" in calls[0]
    ids = {j.external_id for j in jobs}
    # México e Argentina saem; SP e Brasil ficam
    assert "4361108009" not in ids  # Mexico City
    assert "4330619009" not in ids  # Argentina
    assert "4023115009" in ids
    assert "4321369009" in ids
    assert health.foreign >= 2
    assert health.ok == 1
    assert health.jobs == len(jobs)


def test_mantem_curitiba_com_offices_vazios(monkeypatch):
    """Join por espaço gerava token que o gate antigo não lia; Curitiba pura passa."""
    from job_radar.health import SourceHealth

    board = {
        "jobs": [
            {
                "id": 1,
                "title": "Engenheiro de Dados",
                "company_name": "",
                "absolute_url": "https://job-boards.greenhouse.io/ebanx/jobs/1",
                "location": {"name": "Curitiba"},
                "offices": [],
                "content": "vaga em Curitiba",
                "first_published": "2026-09-01T00:00:00Z",
            }
        ]
    }

    monkeypatch.setattr("job_radar.sources._ats.get_json", lambda url, **kw: board)
    health = SourceHealth(name="greenhouse")
    jobs = fetch_greenhouse({"ebanx": "EBANX"}, health=health)
    assert len(jobs) == 1
    assert jobs[0].location == "Curitiba"
    assert jobs[0].company == "EBANX"  # fallback do mapeamento


def test_extrai_work_mode_trailing_da_location():
    bruto = dict(
        _by_id(4023115009),
        location={"name": "São Paulo, SP | Hybrid"},
        offices=[],
        company_name="",
    )
    job = parse_job(bruto, "quintoandar", display_name="Grupo QuintoAndar")
    assert job.work_mode_hint == "hybrid"
    assert job.location == "São Paulo, SP"
    assert job.company == "Grupo QuintoAndar"

    remoto = dict(bruto, location={"name": "Curitiba (Remote)"})
    job2 = parse_job(remoto, "ebanx", display_name="EBANX")
    assert job2.work_mode_hint == "remote"
    assert "Remote" not in (job2.location or "")
