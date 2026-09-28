"""Extrai do currículo as qualificações usadas para casar com a vaga.

O perfil é o currículo em markdown: ele já é mantido atualizado e é a fonte da
verdade do que a pessoa sabe. Derivar daí evita manter uma segunda lista que
envelhece em silêncio.
"""

from __future__ import annotations

import re
from pathlib import Path

# Termos que aparecem em currículo mas não são qualificação buscável numa vaga
_STOPWORDS = {
    "e", "de", "da", "do", "em", "com", "para", "produção", "app router", "design systems",
    "arquitetura hexagonal", "acessibilidade", "testes e2e", "engenharia", "agentes",
}

# O currículo e o anúncio nomeiam a mesma competência de formas diferentes: o CV
# diz "harness de agentes", a vaga diz "LLM" e "IA Generativa". Sem esta ponte a
# vaga MAIS aderente ao perfil casa só termos genéricos (aws, python) e fica com
# nota de vaga qualquer, que foi o que travou o radar por dois dias.
#
# A expansão parte sempre de um termo DECLARADO no currículo: ninguém ganha "llm"
# por ter "python". O plural entra separado porque o casamento exige limite de
# palavra, e "llm" não casa dentro de "LLMs".
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "harness de agentes": ("llm", "llms", "agentes de ia", "ai agents", "ia generativa",
                           "genai", "inteligência artificial", "agentic"),
    "orquestração multi-agente": ("multi-agente", "multiagente", "orquestração de agentes",
                                  "agentes de ia", "llm", "llms", "ia generativa"),
    "subagentes": ("agentes de ia", "ai agents"),
    "claude code": ("claude", "anthropic"),
    "codex": ("openai",),
    "gemini": ("vertex ai",),
    "mcp": ("model context protocol",),
    "next.js": ("nextjs", "next js"),
    "node.js": ("nodejs", "node js"),
    "ci/cd": ("cicd", "integração contínua"),
    "gcp": ("google cloud",),
    "aws": ("amazon web services",),
    "etl em produção": ("etl", "pipeline de dados", "data pipeline"),
    "normalização e validação de dados": ("qualidade de dados", "data quality"),
    "tdd": ("test driven development",),
    "testes e2e com playwright": ("playwright", "testes e2e"),
    "vue.js e nuxt": ("vue", "nuxt"),
}


def expand_synonyms(skills: set[str]) -> set[str]:
    """Acrescenta as grafias que as vagas usam, sem remover as do currículo."""
    out = set(skills)
    for term in skills:
        out.update(_SYNONYMS.get(term.casefold(), ()))
    return out


_SECTION_RE = re.compile(r"^##\s+Stack\s+t[ée]cnica\s*$", re.I | re.M)
_ROW_RE = re.compile(r"^\|\s*\*\*(?P<area>[^*]+)\*\*\s*\|(?P<items>.+?)\|\s*$", re.M)
_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _split_terms(cell: str) -> list[str]:
    """Quebra a célula da tabela em termos, abrindo o que está entre parênteses."""
    expanded = _PAREN_RE.sub(lambda m: ", " + m.group(1), cell)
    parts = re.split(r"[,;]", expanded)
    out: list[str] = []
    for raw in parts:
        term = raw.strip().strip("*` ").rstrip(".")
        term = re.sub(r"\s+\d+(\.\d+)?\+?$", "", term)  # "React 19" -> "React"
        if len(term) < 2 or term.casefold() in _STOPWORDS:
            continue
        out.append(term)
    return out


def extract_skills(markdown: str) -> set[str]:
    """Qualificações declaradas na seção 'Stack técnica' do currículo."""
    match = _SECTION_RE.search(markdown)
    if not match:
        return set()
    tail = markdown[match.end() :]
    end = tail.find("\n## ")
    block = tail[: end if end != -1 else len(tail)]
    skills: set[str] = set()
    for row in _ROW_RE.finditer(block):
        skills.update(_split_terms(row.group("items")))
    return {s.casefold() for s in skills}


def load_profile(path: Path) -> tuple[str, set[str]]:
    """Devolve (texto integral do currículo, qualificações extraídas)."""
    text = path.read_text(encoding="utf-8")
    return text, expand_synonyms(extract_skills(text))
