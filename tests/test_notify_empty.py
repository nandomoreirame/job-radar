import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from notify import should_notify_empty  # noqa: E402


def test_avisa_quando_nao_ha_nada_e_a_flag_esta_ligada():
    assert should_notify_empty(items=[], notify_empty=True) is True


def test_nao_avisa_quando_ha_vagas_para_enviar():
    assert should_notify_empty(items=[{"title": "x"}], notify_empty=True) is False


def test_nao_avisa_com_a_flag_desligada():
    # o padrão continua sendo o silêncio: quem liga é o run.sh
    assert should_notify_empty(items=[], notify_empty=False) is False
