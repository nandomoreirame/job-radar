"""Conectores de fonte. Cada um devolve uma lista de Job normalizada."""

from job_radar.sources.ashby import fetch_ashby
from job_radar.sources.github_repos import fetch_github_repos
from job_radar.sources.greenhouse import fetch_greenhouse
from job_radar.sources.gupy import fetch_gupy
from job_radar.sources.inhire import fetch_inhire
from job_radar.sources.lever import fetch_lever
from job_radar.sources.programathor import fetch_programathor
from job_radar.sources.solides import fetch_solides

__all__ = [
    "fetch_ashby",
    "fetch_github_repos",
    "fetch_greenhouse",
    "fetch_gupy",
    "fetch_inhire",
    "fetch_lever",
    "fetch_programathor",
    "fetch_solides",
]
