"""Termos de busca por alvo de cargo.

Cada alvo vira várias consultas porque o mercado brasileiro nomeia o mesmo cargo
de formas diferentes, e a busca da fonte é por correspondência de título.
"""

TARGETS: dict[str, list[str]] = {
    "ai": ["ai engineer", "engenheiro de ia", "machine learning engineer", "engenheiro de machine learning"],
    "fullstack": ["desenvolvedor senior", "engenheiro de software senior", "full stack senior", "desenvolvedor full stack"],
    "techlead": ["tech lead", "lider tecnico", "engineering manager", "gerente de tecnologia"],
    "dados": ["engenheiro de dados", "data engineer", "engenheiro de dados senior"],
}
