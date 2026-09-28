from job_radar.profile import extract_skills

CV = """
# Fulano

## Resumo
Texto qualquer que não deve virar skill.

## Stack técnica

| Área | Tecnologias |
|---|---|
| **IA aplicada** | Claude Code (skills, hooks), orquestração multi-agente, Gemini |
| **Backend** | Python 3.12 (FastAPI, Polars, pytest), TypeScript (Hono, Node.js) |
| **Frontend** | React 19, Next.js 16 (App Router), Angular |

## Experiência profissional
Nada aqui deve ser extraído.
"""


def test_extrai_termos_da_tabela_de_stack():
    skills = extract_skills(CV)
    assert "python" in skills
    assert "fastapi" in skills
    assert "typescript" in skills
    assert "react" in skills  # versão removida


def test_abre_os_parenteses_em_termos_proprios():
    # "Python 3.12 (FastAPI, Polars)" precisa render Python, FastAPI e Polars
    skills = extract_skills(CV)
    assert {"polars", "pytest", "hono"} <= skills


def test_ignora_secoes_fora_da_stack():
    skills = extract_skills(CV)
    assert not any("experiência" in s for s in skills)
    assert "texto qualquer que não deve virar skill" not in skills


def test_cv_sem_secao_de_stack_retorna_vazio():
    assert extract_skills("# CV\n\n## Resumo\nnada") == set()


# --- vocabulário: o CV e as vagas nomeiam a mesma coisa de formas diferentes ---

from job_radar.profile import expand_synonyms, load_profile  # noqa: E402


def test_termos_de_agentes_do_cv_viram_vocabulario_de_vaga():
    # o CV diz "harness de agentes"; a vaga diz "LLM" e "IA Generativa".
    # sem a ponte, a vaga mais aderente ao perfil pontua como se não fosse.
    out = expand_synonyms({"harness de agentes", "orquestração multi-agente"})
    assert {"llm", "llms", "agentes de ia", "ia generativa"} <= out


def test_llms_no_plural_e_termo_proprio():
    # count_skill_hits exige limite de palavra: "llm" NÃO casa dentro de "LLMs"
    assert "llms" in expand_synonyms({"harness de agentes"})


def test_preserva_as_skills_originais():
    orig = {"python", "aws", "harness de agentes"}
    assert orig <= expand_synonyms(orig)


def test_nao_expande_o_que_o_cv_nao_declara():
    # ninguém ganha "llm" por ter "python": a ponte parte de termo declarado
    assert "llm" not in expand_synonyms({"python", "aws"})


def test_variantes_de_grafia_de_ferramentas():
    out = expand_synonyms({"next.js", "node.js", "ci/cd", "gcp"})
    assert "nextjs" in out and "nodejs" in out
    assert "google cloud" in out


def test_load_profile_ja_entrega_expandido(tmp_path):
    cv = tmp_path / "cv.md"
    cv.write_text(
        "# CV\n\n## Stack técnica\n\n"
        "| **IA** | Harness de agentes, Orquestração multi-agente |\n"
        "| **Back-end** | Python, FastAPI |\n",
        encoding="utf-8",
    )
    _, skills = load_profile(cv)
    assert "python" in skills
    assert "llm" in skills and "agentes de ia" in skills
