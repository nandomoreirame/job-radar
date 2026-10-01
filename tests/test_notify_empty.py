import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from notify import append_health_warnings, should_notify_empty  # noqa: E402


def test_avisa_quando_nao_ha_nada_e_a_flag_esta_ligada():
    assert should_notify_empty(items=[], notify_empty=True) is True


def test_nao_avisa_quando_ha_vagas_para_enviar():
    assert should_notify_empty(items=[{"title": "x"}], notify_empty=True) is False


def test_nao_avisa_com_a_flag_desligada():
    # o padrão continua sendo o silêncio: quem liga é o run.sh
    assert should_notify_empty(items=[], notify_empty=False) is False


def test_append_health_warnings_na_ultima_mensagem():
    """Com resultados, avisos de fonte doente entram no content da última msg."""
    stats = {
        "fontes": {
            "gupy": {"status": "ok", "requests": 1, "ok": 1, "jobs": 2},
            "ashby": {
                "status": "sem_resposta",
                "requests": 3,
                "ok": 0,
                "jobs": 0,
                "errors": ["timeout"],
            },
        },
        "streaks": {"ashby": 2},
    }
    payload = {"embeds": [{"title": "vaga"}]}
    out = append_health_warnings(payload, stats)
    assert "ashby" in (out.get("content") or "")
    assert "sem resposta" in (out["content"])
    assert "embeds" in out


def test_append_health_warnings_sem_doente_nao_mexe():
    stats = {
        "fontes": {"gupy": {"status": "ok", "requests": 1, "ok": 1, "jobs": 1}},
        "streaks": {},
    }
    payload = {"embeds": [{"title": "vaga"}], "content": "cabeçalho"}
    out = append_health_warnings(payload, stats)
    assert out["content"] == "cabeçalho"
