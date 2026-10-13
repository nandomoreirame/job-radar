"""Boards ATS conhecidos e override por ATS_BOARDS.

Formato do env: `greenhouse:slug=Nome,lever:slug=Nome,ashby:slug,inhire:tenant=Nome`
(nome opcional; sem nome usa o próprio slug). Quando setado, SUBSTITUI os
defaults — não mescla — para o dono controlar exatamente quais boards rodar.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping

KNOWN_ATS = ("greenhouse", "lever", "ashby", "inhire")

# Boards verificados com vaga ao vivo na data da feature. Nome de exibição
# entra no Job.company (Lever/Ashby não mandam o nome no payload).
DEFAULT_BOARDS: dict[str, dict[str, str]] = {
    "greenhouse": {
        "quintoandar": "Grupo QuintoAndar",
        "stone": "Stone",
        "inter": "Inter",
        "ebanx": "EBANX",
        "vtex": "VTEX",
        "wildlifestudios": "Wildlife Studios",
        "gympass": "Wellhub",
        "c6bank": "C6 Bank",
        "jusbrasil": "Jusbrasil",
    },
    "lever": {
        "neon": "Neon",
    },
    "ashby": {
        "nubank": "Nubank",
    },
    # slug = tenant da InHire (o subdomínio de <tenant>.inhire.app)
    "inhire": {
        "olist": "Olist",
        "dock": "Dock",
        "contaazul": "Conta Azul",
        "cora": "Cora",
    },
}


def parse_ats_boards(raw: str) -> dict[str, dict[str, str]]:
    """Parseia `ATS_BOARDS`. Entradas inválidas geram aviso em stderr e são puladas."""
    boards: dict[str, dict[str, str]] = {}
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" not in item:
            print(f"ATS_BOARDS: entrada ignorada (malformada): {item!r}", file=sys.stderr)
            continue
        ats, _, rest = item.partition(":")
        ats = ats.strip().casefold()
        if ats not in KNOWN_ATS:
            print(f"ATS_BOARDS: ATS desconhecido ignorado: {ats!r}", file=sys.stderr)
            continue
        if "=" in rest:
            slug, _, name = rest.partition("=")
        else:
            slug, name = rest, ""
        slug, name = slug.strip(), name.strip()
        if not slug:
            print(f"ATS_BOARDS: entrada ignorada (slug vazio): {item!r}", file=sys.stderr)
            continue
        boards.setdefault(ats, {})[slug] = name or slug
    return boards


def resolve_boards(env: Mapping[str, str] | None = None) -> dict[str, dict[str, str]]:
    """Boards efetivos: ATS_BOARDS se setado, senão DEFAULT_BOARDS.

    Env setado mas todo inválido → cai nos defaults com aviso em stderr
    (senão a rodada ATS rodaria vazia em silêncio).
    """
    source = env if env is not None else os.environ
    raw = (source.get("ATS_BOARDS") or "").strip()
    if raw:
        parsed = parse_ats_boards(raw)
        if any(parsed.values()):
            return parsed
        print(
            "ATS_BOARDS: nenhuma entrada válida; usando defaults",
            file=sys.stderr,
        )
    # cópia rasa para o chamador não mutar o default do módulo
    return {ats: dict(slugs) for ats, slugs in DEFAULT_BOARDS.items()}
