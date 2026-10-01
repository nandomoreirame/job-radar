"""Triage: pontuação preserva published_at para a penalidade de idade."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "tests" / "fixtures" / "perfil.md"


def _run_triage(items: list[dict], tmp_path: Path) -> list[dict]:
    inp = tmp_path / "candidates.json"
    out_all = tmp_path / "all.json"
    out_email = tmp_path / "email.json"
    out_manual = tmp_path / "manual.json"
    stats = tmp_path / "stats.json"
    inp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "triage.py"),
        "--input",
        str(inp),
        "--profile",
        str(PROFILE),
        "--out-email",
        str(out_email),
        "--out-manual",
        str(out_manual),
        "--out-all",
        str(out_all),
        "--stats",
        str(stats),
        "--min-score",
        "0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(out_all.read_text(encoding="utf-8"))


def test_vaga_de_40_dias_pontua_menos_que_a_fresca(tmp_path):
    # Sem published_at no Job, a penalidade de idade nunca roda em produção.
    base = {
        "source": "gupy",
        "external_id": "1",
        "title": "Engenheiro de Dados Sênior",
        "company": "Acme",
        "url": "https://example.com/jobs/1",
        "description": "Vaga remota com Python, AWS, Docker e TypeScript.",
        "location": "Remoto",
        "work_mode_hint": "remote",
        "tags": [],
        "contact_email": "",
        "contact_phone": "",
    }
    fresca = dict(base, url="https://example.com/jobs/fresh")
    antiga = dict(
        base,
        url="https://example.com/jobs/old",
        published_at=(datetime.now() - timedelta(days=40)).isoformat(),
    )
    scored = _run_triage([fresca, antiga], tmp_path)
    by_url = {j["url"]: j["score"] for j in scored}
    assert by_url[antiga["url"]] == by_url[fresca["url"]] - 10
