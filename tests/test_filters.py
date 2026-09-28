"""Filtros duros: o que é descartado antes de qualquer avaliação semântica."""

import pytest

from job_radar.filters import (
    Seniority,
    has_excluded_language,
    has_excluded_role,
    is_affirmative,
    WorkMode,
    detect_contract,
    detect_seniority,
    detect_work_mode,
    parse_salary,
    passes_hard_filters,
)
from job_radar.models import Job


def make_job(**kw) -> Job:
    base = dict(
        source="test", external_id="1", title="Desenvolvedor Sênior", company="Acme",
        url="https://x", description="Vaga remota. Python, AWS, TypeScript.", location="São Paulo, SP",
    )
    base.update(kw)
    return Job(**base)


class TestParseSalary:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Salário: R$ 14.000,00", 14000),
            ("R$ 12.000 a R$ 18.000", 12000),
            ("Remuneração de R$ 8.500,00 mensais", 8500),
            ("Faixa: 15k", 15000),
            ("até R$ 20.000/mês", 20000),
            ("Salário a combinar", None),
            ("Vaga sem informação de remuneração", None),
            ("R$ 1.500,00 de auxílio", None),
        ],
    )
    def test_extrai_o_menor_valor_da_faixa(self, text, expected):
        # a faixa mínima é o que decide o corte: anunciar "até 20k" não garante 20k
        assert parse_salary(text) == expected

    def test_ignora_valores_irrelevantes_de_beneficio(self):
        # vale-refeição não é salário e não pode reprovar uma vaga boa
        assert parse_salary("VR de R$ 800,00 e plano de saúde") is None


class TestDetectContract:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Contratação PJ", "PJ"),
            ("Trabalhamos no modelo Pessoa Jurídica", "PJ"),
            ("Vaga CLT efetiva", "CLT"),
            ("Contratação via carteira assinada", "CLT"),
            ("Contratação a combinar", None),
        ],
    )
    def test_detecta_regime(self, text, expected):
        assert detect_contract(text) == expected


class TestDetectSeniority:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Desenvolvedor Sênior", Seniority.SENIOR),
            ("Senior Software Engineer", Seniority.SENIOR),
            ("Tech Lead", Seniority.SENIOR),
            ("Staff Engineer", Seniority.SENIOR),
            ("Especialista em Dados", Seniority.SENIOR),
            ("Desenvolvedor Pleno/Sênior", Seniority.SENIOR),
            ("Desenvolvedor Júnior", Seniority.BELOW),
            ("Estágio em Desenvolvimento", Seniority.BELOW),
            ("Desenvolvedor Pleno", Seniority.BELOW),
            ("Analista de Sistemas", Seniority.UNKNOWN),
        ],
    )
    def test_classifica_pelo_titulo(self, title, expected):
        assert detect_seniority(title) == expected


class TestDetectWorkMode:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Vaga 100% remota", WorkMode.REMOTE),
            ("Home office", WorkMode.REMOTE),
            ("Modelo híbrido, 2x por semana", WorkMode.HYBRID),
            ("Presencial em Belo Horizonte", WorkMode.ONSITE),
            ("Não informado", WorkMode.UNKNOWN),
        ],
    )
    def test_classifica_modalidade(self, text, expected):
        assert detect_work_mode(text) == expected


class TestPassesHardFilters:
    """Cenário do usuário do exemplo: piso de 14k PJ / 12k CLT e Grande São Paulo.

    Declarado aqui e não no código: piso salarial e região são de quem usa o
    radar, e o projeto é público.
    """

    @pytest.fixture(autouse=True)
    def _perfil_de_exemplo(self, monkeypatch):
        monkeypatch.setenv("MIN_SALARY_PJ", "14000")
        monkeypatch.setenv("MIN_SALARY_CLT", "12000")
        monkeypatch.setenv("COMMUTE_CITIES", (
            "São Paulo, Guarulhos, Osasco, Barueri, Santo André, São Bernardo do Campo, "
            "São Caetano do Sul, Diadema, Cotia, Taboão da Serra, Embu das Artes, "
            "Carapicuíba, Mauá, Jandira, Santana de Parnaíba, Itapevi, Alphaville"
        ))

    def test_aprova_remota_senior_sem_salario(self):
        # a maioria das vagas BR omite salário: omitir não pode reprovar
        ok, _ = passes_hard_filters(make_job(), skills={"python", "aws"}, min_skill_hits=2)
        assert ok is True

    def test_reprova_banco_de_talentos(self):
        # cadastro de currículo não tem posição aberta: não é candidatura
        job = make_job(title="Banco de Talentos | Desenvolvedor Fullstack Sênior")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is False and "não é vaga" in reason.lower()

    def test_reprova_junior(self):
        ok, reason = passes_hard_filters(
            make_job(title="Desenvolvedor Júnior"), skills={"python"}, min_skill_hits=1
        )
        assert ok is False and "senioridade" in reason.lower()

    def test_reprova_presencial(self):
        job = make_job(description="Vaga presencial em Curitiba", location="Curitiba, PR")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=0)
        assert ok is False and "modalidade" in reason.lower()

    def test_aprova_hibrido_em_sao_paulo(self):
        job = make_job(description="Modelo híbrido. Python.", location="São Paulo, SP")
        ok, _ = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is True

    def test_reprova_hibrido_em_cidade_do_estado_mas_fora_da_grande_sp(self):
        # "São José dos Campos, São Paulo" carrega o ESTADO São Paulo e fica a 90 km
        # da capital: casar pelo estado aprovava vaga inviável para quem mora em SP.
        job = make_job(description="Modelo híbrido. Python.", location="São José dos Campos, São Paulo")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is False and "modalidade" in reason.lower()

    def test_aprova_hibrido_em_municipio_da_grande_sp(self):
        job = make_job(description="Modelo híbrido. Python.", location="Barueri, São Paulo")
        ok, _ = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is True

    def test_reprova_hibrido_fora_de_sao_paulo(self):
        job = make_job(description="Modelo híbrido. Python.", location="Florianópolis, SC")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is False and "modalidade" in reason.lower()

    def test_reprova_pj_abaixo_de_14k(self):
        job = make_job(description="Vaga remota PJ. Python. Salário: R$ 11.000,00")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is False and "salário" in reason.lower()

    def test_aprova_pj_acima_de_14k(self):
        job = make_job(description="Vaga remota PJ. Python. Salário: R$ 16.000,00")
        ok, _ = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is True

    def test_reprova_clt_abaixo_de_12k(self):
        job = make_job(description="Vaga remota CLT. Python. R$ 9.000,00")
        ok, reason = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is False and "salário" in reason.lower()

    def test_aprova_clt_acima_de_12k(self):
        job = make_job(description="Vaga remota CLT. Python. R$ 13.000,00")
        ok, _ = passes_hard_filters(job, skills={"python"}, min_skill_hits=1)
        assert ok is True

    def test_reprova_sem_skills_do_perfil(self):
        # stack neutra de propósito: nem do perfil, nem barrada por linguagem,
        # senão o teste passaria pelo motivo errado
        job = make_job(description="Vaga remota. Atuação com Salesforce e CRM.")
        ok, reason = passes_hard_filters(job, skills={"python", "typescript"}, min_skill_hits=2)
        assert ok is False and "qualifica" in reason.lower()


# --- vagas afirmativas: o usuário não é elegível, então são ruído no canal ---

def _vaga(titulo: str, descricao: str = "", **kw) -> Job:
    base = dict(source="t", external_id="1", company="Empresa", url="https://x/1",
                work_mode_hint="remote")
    return Job(title=titulo, description=descricao, **(base | kw))


def test_reprova_vaga_exclusiva_para_mulheres():
    assert is_affirmative(_vaga("Desenvolvedora Sênior (vaga exclusiva para mulheres)"))


def test_reprova_vaga_afirmativa_para_pessoas_negras():
    assert is_affirmative(_vaga("Engenheiro de Dados", "Vaga afirmativa para pessoas negras."))


def test_reprova_vaga_exclusiva_para_pcd():
    assert is_affirmative(_vaga("Desenvolvedor Python", "Posição exclusiva para PCD."))


def test_secao_de_diversidade_nao_torna_a_vaga_afirmativa():
    # quase toda descrição tem um parágrafo de diversidade: sozinho ele não exclui ninguém
    desc = ("Somos uma empresa plural e incentivamos a candidatura de mulheres, "
            "pessoas negras e pessoas com deficiência. Valorizamos a diversidade.")
    assert not is_affirmative(_vaga("Desenvolvedor Python Sênior", desc))


def test_vaga_comum_nao_e_afirmativa():
    assert not is_affirmative(_vaga("Desenvolvedor Python Sênior", "Trabalhamos com Django."))


# --- linguagens fora do perfil ---

def test_reprova_titulo_de_csharp():
    assert has_excluded_language(_vaga("Desenvolvedor BackEnd C# SR"))


def test_reprova_titulo_de_java_e_delphi_e_cpp():
    assert has_excluded_language(_vaga("Desenvolvedor Java Sênior"))
    assert has_excluded_language(_vaga("Analista Programador Delphi"))
    assert has_excluded_language(_vaga("Engenheiro de Software C++"))


def test_javascript_nao_e_java():
    # a armadilha clássica: bloquear Java derrubaria toda vaga de JavaScript
    assert not has_excluded_language(_vaga("Desenvolvedor JavaScript Sênior"))
    assert not has_excluded_language(_vaga("Dev Full Stack", "Stack: JavaScript, TypeScript, Node.js"))


def test_mencao_de_passagem_nao_reprova_quando_a_stack_e_do_perfil():
    desc = ("Buscamos pessoa desenvolvedora Python com FastAPI e React. "
            "Conhecimento em Java é considerado diferencial.")
    assert not has_excluded_language(_vaga("Desenvolvedor Python Sênior", desc))


def test_descricao_so_de_stack_alheia_reprova_mesmo_com_titulo_generico():
    desc = "Atuação com Java, Spring Boot e Oracle em sistemas legados."
    assert has_excluded_language(_vaga("Pessoa Desenvolvedora Sênior", desc))


def test_filtros_duros_barram_afirmativa_e_stack_alheia():
    skills = {"python", "fastapi", "react", "typescript", "aws"}
    ok, motivo = passes_hard_filters(
        _vaga("Desenvolvedor Java Sênior", "Java, Spring, Python, React, FastAPI, AWS, TypeScript"), skills)
    assert not ok and "linguagem" in motivo.lower()
    ok, motivo = passes_hard_filters(
        _vaga("Desenvolvedora Python Sênior (exclusiva para mulheres)",
              "Python, FastAPI, React, TypeScript, AWS"), skills)
    assert not ok and "afirmativa" in motivo.lower()


# --- regressões colhidas de vagas reais já recebidas ---

def test_titulo_com_alternativas_preserva_vaga_de_stack_propria():
    # real: "... (React / Python / Go or Node.js or Java) | Remote | Velozient".
    # Java é UMA das opções; bloquear pelo título descartaria uma vaga da stack dele.
    j = _vaga("Senior Full Stack Software Engineer (React / Python / Go or Node.js or Java) | Remote")
    assert not has_excluded_language(j)


def test_titulo_so_de_stack_alheia_continua_reprovado():
    assert has_excluded_language(_vaga("Desenvolvedor Full Stack Sênior - Java e Vue.js"))


def test_convite_a_candidatura_nao_e_vaga_afirmativa():
    # real (Itaú): o texto diz o OPOSTO de restringir, e casava por proximidade frouxa
    desc = ("*Estimulamos candidaturas de pessoas com deficiência em todas as nossas posições, "
            "sendo assim, sinta-se à vontade para se candidatar em vagas sinalizadas como "
            "exclusivas ou não para pessoas com deficiência")
    assert not is_affirmative(_vaga("Tech Lead de Engenharia de Dados Sênior", desc))


def test_afirmativa_anunciada_no_titulo_continua_reprovada():
    assert is_affirmative(_vaga("Data Platform Engineer - Vaga Afirmativa para Mulheres"))
    assert is_affirmative(_vaga("Tech Lead | Afirmativa para mulheres e pessoas negras"))


# --- funções fora do perfil: ele é engenheiro de software, não QA nem PO ---

def test_reprova_vagas_de_qa():
    # real: "QA Engineer Senior AI — Techne" chegou ao canal
    assert has_excluded_role(_vaga("QA Engineer Senior AI"))
    assert has_excluded_role(_vaga("Analista de Testes Sênior"))
    assert has_excluded_role(_vaga("SDET Pleno/Sênior"))
    assert has_excluded_role(_vaga("Quality Assurance Engineer"))
    assert has_excluded_role(_vaga("Engenheiro de Qualidade de Software"))
    assert has_excluded_role(_vaga("Especialista em Automação de Testes"))


def test_reprova_funcoes_nao_tecnicas_de_produto_e_suporte():
    assert has_excluded_role(_vaga("Scrum Master Sênior"))
    assert has_excluded_role(_vaga("Product Owner - Plataforma"))
    assert has_excluded_role(_vaga("Analista de Suporte Técnico N2"))
    assert has_excluded_role(_vaga("DBA Oracle Sênior"))


def test_product_engineer_nao_e_product_owner():
    # real: "Product Engineer (LLMs, Next.js, Python, AWS) - Strider" é vaga dele
    assert not has_excluded_role(_vaga("Product Engineer (LLMs, Next.js, Python, AWS)"))


def test_qualidade_de_dados_nao_e_qa():
    # engenharia de dados usa "qualidade": não pode virar QA por causa da palavra
    assert not has_excluded_role(_vaga("Engenheiro de Qualidade de Dados"))
    assert not has_excluded_role(_vaga("Engenheiro de Dados Sênior - GCP"))


def test_funcoes_do_perfil_seguem_passando():
    for titulo in ("Desenvolvedor Python Sênior", "Tech Lead Full Stack",
                   "Engenheiro(a) de IA SR", "Cloud Engineer / Analista de Infraestrutura Cloud",
                   "Senior Backend Engineer", "Arquiteto de Software Sênior"):
        assert not has_excluded_role(_vaga(titulo)), titulo


def test_mencao_a_qa_na_descricao_nao_reprova_vaga_de_dev():
    # a função é declarada no título; citar o time de QA é rotina em vaga de dev
    j = _vaga("Desenvolvedor Python Sênior", "Você trabalhará junto ao time de QA e de produto.")
    assert not has_excluded_role(j)


def test_filtros_duros_barram_funcao_fora_do_perfil():
    skills = {"python", "ci/cd", "cursor", "gemini"}
    ok, motivo = passes_hard_filters(_vaga("QA Engineer Senior AI", "Python, CI/CD, Cursor, Gemini"), skills)
    assert not ok and "função" in motivo.lower()


def test_tag_estrutural_da_fonte_marca_vaga_afirmativa():
    # a Sólides declara isso em campo próprio; vale mais que interpretar o texto
    j = _vaga("Engenheiro de Dados Sênior")
    j.tags = ["CLT", "vaga afirmativa"]
    assert is_affirmative(j)


# --- abreviações sem ponto: "SR", "JR/PL" são a grafia mais comum em anúncio ---

def test_sr_sem_ponto_conta_como_senior():
    # real: "DESENVOLVEDOR DE HARDWARE SR" ficava UNKNOWN e perdia pontos
    assert detect_seniority("DESENVOLVEDOR DE HARDWARE SR") is Seniority.SENIOR
    assert detect_seniority("Desenvolvedor Back-end Sr") is Seniority.SENIOR


def test_jr_pl_sem_ponto_reprova():
    # real: "Fullstack AI Engineer - (JR/PL)" passou e tirou nota 80
    assert detect_seniority("Fullstack AI Engineer - (JR/PL)") is Seniority.BELOW
    assert detect_seniority("Desenvolvedor Python JR") is Seniority.BELOW


def test_pl_sr_continua_senior_porque_a_porta_esta_aberta():
    assert detect_seniority("Analista Finops PL/SR - Cooperado") is Seniority.SENIOR
    assert detect_seniority("Back-end developer Node.js Pleno/Sênior") is Seniority.SENIOR


def test_pl_sql_nao_e_senioridade():
    # "PL" ali é a linguagem da Oracle, não "pleno"
    assert detect_seniority("Desenvolvedor PL/SQL") is not Seniority.BELOW


# --- configuração externa: o repo é público, os valores são de quem usa ---

def test_sem_piso_configurado_o_salario_nao_reprova(monkeypatch):
    monkeypatch.delenv("MIN_SALARY_PJ", raising=False)
    monkeypatch.delenv("MIN_SALARY_CLT", raising=False)
    j = _vaga("Desenvolvedor Python Sênior", "Vaga remota CLT. Python, React, AWS. R$ 3.000,00")
    ok, motivo = passes_hard_filters(j, {"python", "react", "aws"})
    assert ok, motivo


def test_sem_cidades_configuradas_hibrido_nao_e_barrado(monkeypatch):
    monkeypatch.delenv("COMMUTE_CITIES", raising=False)
    j = _vaga("Desenvolvedor Python Sênior", "Modelo híbrido. Python, React, AWS.",
              location="Florianópolis, SC", work_mode_hint="hybrid")
    ok, motivo = passes_hard_filters(j, {"python", "react", "aws"})
    assert ok, motivo
