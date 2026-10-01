"""Conector Ashby contra fixture real (Nubank)."""

import json
from pathlib import Path

from job_radar.sources.ashby import fetch_ashby, parse_job

FIX = Path(__file__).parent / "fixtures"
BOARD = json.loads((FIX / "ashby_board.json").read_text(encoding="utf-8"))
JOBS = BOARD["jobs"]


def _by_title(fragment: str) -> dict:
    return next(j for j in JOBS if fragment in j["title"])


def test_mapeia_vaga_brasileira():
    raw = _by_title("Lead Security Engineer")
    job = parse_job(raw, company="Nubank")
    assert job.source == "ashby"
    assert job.company == "Nubank"
    assert job.location == "São Paulo, SP"
    assert job.work_mode_hint == "hybrid"
    assert job.url.startswith("https://jobs.ashbyhq.com/nubank/")
    assert job.published_at is not None


def test_nao_usa_is_remote_como_fonte_da_modalidade():
    # isRemote=true em vaga Hybrid: o campo é mentiroso
    raw = _by_title("Lead Security Engineer")
    assert raw["isRemote"] is True and raw["workplaceType"] == "Hybrid"
    job = parse_job(raw, company="Nubank")
    assert job.work_mode_hint == "hybrid"


def test_anexa_compensation_na_descricao():
    raw = _by_title("Business Control Officer")
    job = parse_job(raw, company="Nubank")
    assert "$129.6K" in job.description or "129.6" in job.description


def test_pula_is_listed_false():
    bruto = dict(_by_title("Lead Security Engineer"), isListed=False)
    assert parse_job(bruto, company="Nubank") is None


def test_fetch_descarta_eua_e_mantem_brasil(monkeypatch):
    from job_radar.health import SourceHealth

    monkeypatch.setattr(
        "job_radar.sources._ats.get_json",
        lambda url, **kwargs: BOARD,
    )
    health = SourceHealth(name="ashby")
    jobs = fetch_ashby({"nubank": "Nubank"}, health=health)
    titles = {j.title for j in jobs}
    assert any("Security Engineer" in t for t in titles)
    assert not any("Miami" in (j.location or "") for j in jobs)
    assert not any("Virginia" in (j.location or "") for j in jobs)
    assert not any("CloudNetwork" in t for t in titles)
    assert not any("Business Control" in t for t in titles)
    assert health.foreign >= 2
    assert health.ok == 1
