import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "tests" / "fixtures" / "perfil.md"

PROFILE.parent.mkdir(parents=True, exist_ok=True)
PROFILE.write_text(
    "## Stack técnica\n\n| Área | Tecnologias |\n|---|---|\n"
    "| **Backend** | Python, TypeScript, AWS, Docker |\n",
    encoding="utf-8",
)


def run(payload, tmp_path, extra=None):
    out = tmp_path / "c.json"
    db = tmp_path / "s.db"
    discards = tmp_path / "d.tsv"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "ingest.py"),
        "--profile",
        str(PROFILE),
        "--out",
        str(out),
        "--db",
        str(db),
        "--discards",
        str(discards),
        "--min-skills",
        "1",
        *(extra or []),
    ]
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_text(encoding="utf-8")), proc.stdout


def test_run_helper_aponta_discards_para_tmp(tmp_path):
    # Sem --discards o default era data/discarded.tsv (arquivo real).
    run(
        [
            {
                "title": "Desenvolvedor Júnior",
                "company": "Acme",
                "url": "u",
                "description": "Vaga remota com Python",
            }
        ],
        tmp_path,
    )
    assert (tmp_path / "d.tsv").exists()
    assert "senioridade" in (tmp_path / "d.tsv").read_text(encoding="utf-8")


def test_aceita_vaga_valida(tmp_path):
    vagas, saida = run([{
        "title": "Engenheiro de Software Sênior", "company": "Acme",
        "url": "https://linkedin.com/jobs/view/1", "description": "Vaga remota com Python e AWS",
    }], tmp_path)
    assert len(vagas) == 1
    assert vagas[0]["source"] == "email"
    assert "ACEITAS:     1" in saida


def test_aplica_os_mesmos_filtros_duros(tmp_path):
    # júnior precisa ser reprovado aqui exatamente como nas fontes de API
    vagas, saida = run([{
        "title": "Desenvolvedor Júnior", "company": "Acme",
        "url": "u", "description": "Vaga remota com Python",
    }], tmp_path)
    assert vagas == []
    assert "senioridade" in saida


def test_descarta_repetida_no_mesmo_lote(tmp_path):
    vaga = {"title": "Dev Sênior", "company": "Acme", "url": "u", "description": "remoto Python AWS"}
    vagas, _ = run([vaga, dict(vaga)], tmp_path)
    assert len(vagas) == 1


def test_discards_sempre_anexa_mesmo_sem_merge(tmp_path):
    # Sem --merge o ingest sobrescrevia o TSV que o collect acabou de gravar.
    discards = tmp_path / "d.tsv"
    discards.write_text(
        "timestamp\tsource\treason\tcompany\ttitle\turl\n"
        "2026-01-01T00:00:00\tgupy\tjá enviada\tOldCo\tOld\thttps://old\n",
        encoding="utf-8",
    )
    run(
        [
            {
                "title": "Desenvolvedor Júnior",
                "company": "Acme",
                "url": "u",
                "description": "Vaga remota com Python",
            }
        ],
        tmp_path,
    )
    text = discards.read_text(encoding="utf-8")
    assert "OldCo" in text
    assert "senioridade" in text
    assert text.count("timestamp\tsource") == 1
