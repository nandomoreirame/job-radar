import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from delete_messages import select_targets  # noqa: E402

LOG = [
    {"id": "a", "title": "Engenheiro de IA SR"},
    {"id": "b", "title": "Desenvolvedor Java Sênior"},
    {"id": "c", "title": "Vaga Afirmativa para Mulheres"},
    {"id": "d", "title": "Tech Lead Python"},
]


def test_sem_criterio_apaga_tudo():
    alvos, restantes = select_targets(LOG)
    assert [e["id"] for e in alvos] == ["a", "b", "c", "d"]
    assert restantes == []


def test_last_apaga_apenas_as_ultimas():
    alvos, restantes = select_targets(LOG, last=2)
    assert [e["id"] for e in alvos] == ["c", "d"]
    assert [e["id"] for e in restantes] == ["a", "b"]


def test_ids_apaga_so_os_escolhidos_e_preserva_o_resto():
    # apagar por critério (vaga afirmativa, stack alheia) exige escolher no meio do log
    alvos, restantes = select_targets(LOG, ids={"b", "c"})
    assert [e["id"] for e in alvos] == ["b", "c"]
    assert [e["id"] for e in restantes] == ["a", "d"]


def test_id_inexistente_nao_inventa_alvo():
    alvos, restantes = select_targets(LOG, ids={"zzz"})
    assert alvos == []
    assert len(restantes) == 4
