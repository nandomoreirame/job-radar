"""Conector Lever contra fixture real (Neon)."""

import json
from pathlib import Path

from job_radar.sources.lever import fetch_lever, parse_job

FIX = Path(__file__).parent / "fixtures"
POSTINGS = json.loads((FIX / "lever_postings.json").read_text(encoding="utf-8"))


def test_mapeia_campos_basicos():
    job = parse_job(POSTINGS[0], company="Neon")
    assert job.source == "lever"
    assert job.title == "Analista de Growth (Business Analytics) - Pleno"
    assert job.company == "Neon"
    assert job.url.startswith("https://jobs.lever.co/neon/")
    assert job.work_mode_hint == "remote"
    assert job.location  # Remoto ou vazio normalizado
    assert job.published_at is not None


def test_commitment_vira_tag():
    job = parse_job(POSTINGS[0], company="Neon")
    assert "CLT" in job.tags


def test_descricao_junta_plain_e_listas():
    job = parse_job(POSTINGS[0], company="Neon")
    assert len(job.description) > 500
    assert "Responsabilidades" in job.description or "SQL" in job.description


def test_fetch_filtra_por_brasil_e_grava_health(monkeypatch):
    from job_radar.health import SourceHealth

    def fake_get_json(url, **kwargs):
        return POSTINGS

    monkeypatch.setattr("job_radar.sources._ats.get_json", fake_get_json)
    health = SourceHealth(name="lever")
    jobs = fetch_lever({"neon": "Neon"}, health=health)
    assert len(jobs) == len(POSTINGS)  # todas country=BR
    assert health.ok == 1
    assert health.jobs == len(jobs)
    assert all(j.company == "Neon" for j in jobs)


def test_hibrido_em_sao_paulo_com_all_locations_duplicado(monkeypatch):
    """Join por espaço ('São Paulo São Paulo') quebrava o gate; vírgula mantém."""
    from job_radar.health import SourceHealth

    posting = {
        "id": "sp-hybrid",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/neon/sp-hybrid",
        "workplaceType": "hybrid",
        "country": "",
        "categories": {
            "location": "São Paulo",
            "allLocations": ["São Paulo"],
            "commitment": "CLT",
        },
        "descriptionPlain": "vaga em São Paulo",
        "lists": [],
        "createdAt": 1700000000000,
    }

    monkeypatch.setattr("job_radar.sources._ats.get_json", lambda url, **kw: [posting])
    health = SourceHealth(name="lever")
    jobs = fetch_lever({"neon": "Neon"}, health=health)
    assert len(jobs) == 1
    assert jobs[0].location == "São Paulo"
    assert jobs[0].work_mode_hint == "hybrid"
