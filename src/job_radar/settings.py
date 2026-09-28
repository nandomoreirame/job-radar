"""Configuração vinda do ambiente.

Piso salarial e região de deslocamento são dados de quem usa o radar, não do
projeto. Ficam aqui, lidos do ambiente a cada chamada, para que um clone não
herde a pretensão salarial nem o endereço de outra pessoa.

Os defaults são NEUTROS de propósito: sem configuração, nenhum dos dois filtra
nada. É melhor um radar que deixa passar do que um que descarta em silêncio por
um valor que o dono nunca escolheu.
"""

from __future__ import annotations

import os
import unicodedata


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def min_salary(contract: str | None) -> int:
    """Piso mensal para o tipo de contrato. Zero significa "não filtrar".

    Contrato não declarado usa o piso de CLT, que é o mais baixo dos dois no uso
    típico: na dúvida, exigir menos.
    """
    name = "MIN_SALARY_PJ" if contract == "PJ" else "MIN_SALARY_CLT"
    try:
        return max(0, int(os.getenv(name, "0")))
    except ValueError:
        # configuração malformada não pode derrubar a varredura inteira
        return 0


def commute_cities() -> frozenset[str]:
    """Cidades onde uma vaga híbrida é viável, normalizadas para comparação.

    Conjunto vazio significa "sem restrição de praça". A checagem é por CIDADE e
    não por estado: "São José dos Campos, São Paulo" carrega o estado São Paulo e
    fica a 90 km da capital.
    """
    raw = os.getenv("COMMUTE_CITIES", "")
    cities = (_strip_accents(part).strip().casefold() for part in raw.split(","))
    return frozenset(c for c in cities if c)
