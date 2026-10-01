"""Escrita atômica: o arquivo final só aparece completo."""

import os
import stat
from pathlib import Path

from job_radar.fsutil import atomic_write_text


def test_grava_conteudo_completo(tmp_path):
    dest = tmp_path / "out.json"
    atomic_write_text(dest, '{"ok": true}')
    assert dest.read_text(encoding="utf-8") == '{"ok": true}'


def test_substitui_arquivo_existente(tmp_path):
    dest = tmp_path / "out.txt"
    dest.write_text("velho", encoding="utf-8")
    atomic_write_text(dest, "novo")
    assert dest.read_text(encoding="utf-8") == "novo"


def test_cria_diretorio_pai(tmp_path):
    dest = tmp_path / "sub" / "a" / "out.txt"
    atomic_write_text(dest, "x")
    assert dest.read_text(encoding="utf-8") == "x"


def test_falha_nao_deixa_temp_para_tras(tmp_path, monkeypatch):
    dest = tmp_path / "out.txt"

    def boom(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr("job_radar.fsutil.os.replace", boom)
    try:
        atomic_write_text(dest, "x")
    except OSError:
        pass
    leftovers = list(tmp_path.glob(".*"))
    assert leftovers == []
    assert not dest.exists()


def test_preserva_mode_do_arquivo_existente(tmp_path):
    # mkstemp cria 0600 e os.replace mantinha: 0644 virava 0600 em silêncio.
    dest = tmp_path / "out.txt"
    dest.write_text("velho", encoding="utf-8")
    os.chmod(dest, 0o644)
    atomic_write_text(dest, "novo")
    assert stat.S_IMODE(dest.stat().st_mode) == 0o644


def test_arquivo_novo_respeita_umask(tmp_path, monkeypatch):
    dest = tmp_path / "novo.txt"
    monkeypatch.setattr("job_radar.fsutil._umask", lambda: 0o022)
    atomic_write_text(dest, "x")
    assert stat.S_IMODE(dest.stat().st_mode) == 0o644
