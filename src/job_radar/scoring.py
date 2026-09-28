"""Pontuação determinística de compatibilidade, de 0 a 100.

Serve para ORDENAR o que vai à avaliação final e ao canal. Não substitui a
leitura da descrição: mede sobreposição de qualificações e aderência do título
ao alvo, que é o que dá para medir sem interpretar texto.
"""

from __future__ import annotations

import re

from job_radar.filters import Seniority, WorkMode, detect_seniority, detect_work_mode, _mode_from_hint
from job_radar.models import Job

# Títulos que indicam o núcleo do posicionamento, com o peso de cada família
TARGET_PATTERNS: list[tuple[str, int]] = [
    (r"\b(ai|i\.?a\.?|intelig[êe]ncia artificial|llm|genai|machine learning|ml)\b", 30),
    (r"\b(dados|data)\b", 20),
    (r"\b(tech lead|l[íi]der t[ée]cnico|staff|principal|arquitet\w*)\b", 20),
    (r"\b(full ?stack|back ?end|software)\b", 15),
]

# Stacks que dominam a vaga e não são as dele: sinalizam encaixe fraco
FOREIGN_STACK_RE = re.compile(r"\b(salesforce|sap|abap|cobol|mainframe|delphi|sharepoint|power ?bi|dynamics)\b", re.I)


def score_job(job: Job, skills: set[str], skill_hits: set[str]) -> int:
    """Nota 0-100. Qualificações pesam mais que título, porque título mente."""
    score = 0

    # sobreposição de qualificações: até 45 pontos, saturando em 9 acertos
    score += min(len(skill_hits), 9) * 5

    # aderência do título ao alvo: pega a família de maior peso, sem somar todas
    title = job.title.casefold()
    score += max((weight for pattern, weight in TARGET_PATTERNS if re.search(pattern, title, re.I)), default=0)

    # senioridade explícita no título
    if detect_seniority(job.title) is Seniority.SENIOR:
        score += 10

    # remoto vale mais que híbrido para quem filtra por remoto
    mode = _mode_from_hint(job.work_mode_hint) or detect_work_mode(job.haystack)
    if mode is WorkMode.REMOTE:
        score += 15
    elif mode is WorkMode.HYBRID:
        score += 5

    # stack alheia dominando a descrição derruba a nota
    if len(FOREIGN_STACK_RE.findall(job.description)) >= 3:
        score -= 25

    return max(0, min(100, score))
