"""Conectores de fonte. Cada um devolve uma lista de Job normalizada."""

from job_radar.sources.github_repos import fetch_github_repos
from job_radar.sources.gupy import fetch_gupy
from job_radar.sources.programathor import fetch_programathor
from job_radar.sources.solides import fetch_solides

__all__ = ["fetch_github_repos", "fetch_gupy", "fetch_programathor", "fetch_solides"]
