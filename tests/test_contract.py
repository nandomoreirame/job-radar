"""Contrato mínimo de todo conector: título, URL http(s) e empresa quando a fonte traz."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_radar.models import Job
from job_radar.sources.ashby import parse_job as parse_ashby
from job_radar.sources.github_repos import parse_issue
from job_radar.sources.greenhouse import parse_job as parse_greenhouse
from job_radar.sources.gupy import listing_from_page, parse_job as parse_gupy
from job_radar.sources.lever import parse_job as parse_lever
from job_radar.sources.programathor import parse_listing as parse_programathor
from job_radar.sources.solides import parse_listing as parse_solides

FIX = Path(__file__).parent / "fixtures"


def _jobs_gupy() -> list[Job]:
    html = (FIX / "gupy_search.html").read_text(encoding="utf-8")
    return [parse_gupy(item) for item in listing_from_page(html)]


def _jobs_github() -> list[Job]:
    issue = {
        "number": 42,
        "title": "[Remoto] Engenheiro de Dados na Acme",
        "body": "Vaga sênior. Envie CV para talentos@acme.com.br",
        "html_url": "https://github.com/x/y/issues/42",
        "labels": [{"name": "Sênior"}],
        "created_at": "2026-09-01T10:00:00Z",
    }
    return [parse_issue(issue, "datascience-br/vagas")]


def _jobs_programathor() -> list[Job]:
    card = """
    <div class="cell-list ">
      <a href="/jobs/33685-desenvolvedor-back-end-senior-ai-engineer">
        <div class="cell-list-content">
          <h3 class="text-24 line-height-30">Desenvolvedor Back-End Senior</h3>
          <div class='cell-list-content-icon'>
            <span><i class='fa fa-briefcase'></i>Acme LTDA</span>
            <span><i class='fas fa-map-marker-alt'></i>Remoto</span>
          </div>
        </div>
      </a>
    </div>
    """
    return parse_programathor(card)


def _jobs_solides() -> list[Job]:
    pagina = json.loads((FIX / "solides_listing.json").read_text(encoding="utf-8"))
    return [parse_solides(item) for item in pagina["data"]]


def _jobs_greenhouse() -> list[Job]:
    board = json.loads((FIX / "greenhouse_board.json").read_text(encoding="utf-8"))
    return [parse_greenhouse(raw, "quintoandar") for raw in board["jobs"][:5]]


def _jobs_lever() -> list[Job]:
    postings = json.loads((FIX / "lever_postings.json").read_text(encoding="utf-8"))
    return [parse_lever(raw, "Neon", "neon") for raw in postings[:5]]


def _jobs_ashby() -> list[Job]:
    board = json.loads((FIX / "ashby_board.json").read_text(encoding="utf-8"))
    jobs = []
    for raw in board["jobs"][:5]:
        job = parse_ashby(raw, "Nubank")
        if job is not None:
            jobs.append(job)
    return jobs


# (nome, jobs, empresa_obrigatoria)
_CASES = [
    ("gupy", _jobs_gupy, True),
    ("github", _jobs_github, True),
    ("programathor", _jobs_programathor, True),
    ("solides", _jobs_solides, True),
    ("greenhouse", _jobs_greenhouse, True),
    ("lever", _jobs_lever, True),
    ("ashby", _jobs_ashby, True),
]


@pytest.mark.parametrize("nome,loader,exige_empresa", _CASES)
def test_contrato_minimo_do_parser(nome, loader, exige_empresa):
    jobs = loader()
    assert jobs, f"{nome}: fixture não produziu vagas"
    for job in jobs:
        assert isinstance(job, Job)
        assert job.title.strip(), f"{nome}: título vazio"
        assert job.url.startswith("http"), f"{nome}: URL inválida ({job.url!r})"
        if exige_empresa:
            # github sem empresa no título é caso à parte; o sample acima traz "na Acme"
            assert job.company.strip(), f"{nome}: empresa vazia em {job.title!r}"
