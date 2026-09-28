"""Estatísticas da última varredura, compartilhadas entre as etapas da rodada.

O `collect` sabe quantas vagas entraram e quantas foram reprovadas; o `triage`
sabe quantas passaram do corte. Sem um lugar comum, esses números só existem no
stdout do serviço, e foi por isso que dois dias de silêncio passaram por "não
apareceu vaga nova" quando na verdade o corte estava inatingível.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def merge_stats(current: dict, new: dict) -> dict:
    """Combina os números das etapas: a etapa seguinte acrescenta, não substitui."""
    return {**current, **new}


def read_stats(path: Path) -> dict:
    """Lê as estatísticas. Arquivo ausente ou corrompido vira dicionário vazio.

    Nunca levanta: isto alimenta uma mensagem informativa, e falhar aqui
    silenciaria justamente o aviso que o arquivo existe para dar.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_stats(path: Path, reset: bool = False, **values: object) -> dict:
    """Acrescenta valores às estatísticas da rodada e devolve o resultado.

    `reset` é para a PRIMEIRA etapa da rodada: sem ele, números da varredura
    anterior sobrevivem e o aviso de "nada encontrado" cita um funil que não é
    o desta execução.
    """
    path = Path(path)
    merged = merge_stats({} if reset else read_stats(path), dict(values))
    merged["at"] = datetime.now().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
