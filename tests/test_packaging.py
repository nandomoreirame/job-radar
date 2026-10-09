"""Metadados do projeto: o que um terceiro vê ao clonar ou instalar o pacote."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_entry_points_apontam_para_funcoes_existentes() -> None:
    # Um entry point quebrado vira um comando instalado que morre com ImportError.
    for target in PYPROJECT["project"].get("scripts", {}).values():
        module_name, _, attr = target.partition(":")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attr))


def test_licenca_mit_declarada_e_presente() -> None:
    assert PYPROJECT["project"]["license"] == "MIT"
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")


def test_run_sh_usa_o_mesmo_perfil_que_os_scripts() -> None:
    # O run.sh fixava profile/perfil.md enquanto os scripts e o .env.example usam
    # profile/profile.md: quem seguisse o README tinha o timer quebrado.
    # Sem --profile no run.sh, vale o default dos scripts ou PROFILE_PATH.
    assert "--profile" not in (ROOT / "run.sh").read_text(encoding="utf-8")
