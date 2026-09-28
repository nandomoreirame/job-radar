"""Filtros duros: descartam a vaga antes de gastar avaliação semântica com ela.

A ordem importa. Senioridade e modalidade são baratas e cortam muito; o salário
exige parsing; o casamento de qualificações é o último porque é o mais caro.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

from job_radar.models import Job
from job_radar.settings import commute_cities, min_salary


class Seniority(str, Enum):
    SENIOR = "senior"
    BELOW = "below"
    UNKNOWN = "unknown"


class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


_SENIOR_RE = re.compile(
    r"\b(s[êe]nior|senior|sr\.?\b|staff|principal|especialista|lead|l[íi]der|head|manager|gerente|arquitet\w*)",
    re.I,
)
# "SR", "JR" e "PL" aparecem sem ponto na maioria dos anúncios, então o ponto é
# opcional. O "pl" tem ressalva: em "PL/SQL" é a linguagem da Oracle, não "pleno".
_BELOW_RE = re.compile(
    r"\b(j[úu]nior|junior|jr\.?\b|est[áa]gi\w*|trainee|aprendiz|plenos?\b|pl\.?\b(?!/?sql))",
    re.I,
)

_REMOTE_RE = re.compile(r"\b(remot[oa]|remote|home\s*office|anywhere|teletrabalho)\b", re.I)
_HYBRID_RE = re.compile(r"\b(h[íi]brid[oa]|hybrid)\b", re.I)
_ONSITE_RE = re.compile(r"\b(presencial|on-?site|no local)\b", re.I)
def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def in_commute_range(location: str) -> bool:
    """True quando a vaga híbrida fica numa cidade alcançável.

    Sem `COMMUTE_CITIES` configurado não há restrição de praça, e toda híbrida
    passa: descartar por uma lista que o dono nunca preencheu seria pior.
    """
    cidades = commute_cities()
    if not cidades:
        return True
    if not location:
        return False
    city = _strip_accents(location.split(",")[0]).strip().casefold()
    return city in cidades

_PJ_RE = re.compile(r"\b(pj|pessoa\s+jur[íi]dica|cnpj)\b", re.I)
_CLT_RE = re.compile(r"\b(clt|carteira\s+assinada|efetiv[oa]|regime\s+celetista)\b", re.I)

# "R$ 14.000,00", "14.000", "14k". Exige o marcador de moeda ou o sufixo k para
# não confundir número solto (ano, quantidade de usuários) com remuneração.
_MONEY_RE = re.compile(r"(?:r\$\s*)(\d{1,3}(?:[.\s]\d{3})+|\d{4,6})(?:,\d{2})?|(\d{1,3})\s*k\b", re.I)
# Contextos em que um valor NÃO é salário
_BENEFIT_RE = re.compile(r"\b(vr|va|vale[\s-]?(refei[çc][ãa]o|alimenta[çc][ãa]o|transporte)|aux[íi]lio|plano de sa[úu]de|gympass)\b", re.I)


def parse_salary(text: str) -> int | None:
    """Menor valor monetário mensal plausível do texto, ou None.

    Usa o MENOR da faixa porque é o que a vaga garante: "até R$ 20.000" não
    significa que você receberá 20.000.
    """
    if not text:
        return None
    values: list[int] = []
    for match in _MONEY_RE.finditer(text):
        # descarta valor que aparece colado a um benefício
        window = text[max(0, match.start() - 40) : match.end() + 20]
        if _BENEFIT_RE.search(window):
            continue
        if match.group(1):
            values.append(int(re.sub(r"[.\s]", "", match.group(1))))
        elif match.group(2):
            values.append(int(match.group(2)) * 1000)
    return min(values) if values else None


def detect_contract(text: str) -> str | None:
    """Regime de contratação declarado, ou None."""
    if not text:
        return None
    if _PJ_RE.search(text):
        return "PJ"
    if _CLT_RE.search(text):
        return "CLT"
    return None


def detect_seniority(title: str) -> Seniority:
    """Classifica pelo título. 'Pleno/Sênior' conta como sênior: a porta está aberta."""
    if not title:
        return Seniority.UNKNOWN
    if _SENIOR_RE.search(title):
        return Seniority.SENIOR
    if _BELOW_RE.search(title):
        return Seniority.BELOW
    return Seniority.UNKNOWN


def detect_work_mode(text: str) -> WorkMode:
    """Remoto vence híbrido, que vence presencial: o anúncio costuma citar o mais permissivo."""
    if not text:
        return WorkMode.UNKNOWN
    if _REMOTE_RE.search(text):
        return WorkMode.REMOTE
    if _HYBRID_RE.search(text):
        return WorkMode.HYBRID
    if _ONSITE_RE.search(text):
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def count_skill_hits(job: Job, skills: set[str]) -> set[str]:
    """Quais qualificações do perfil aparecem na vaga."""
    hay = job.haystack
    return {s for s in skills if re.search(rf"(?<![a-z0-9+#.]){re.escape(s.casefold())}(?![a-z0-9+#])", hay)}


def _mode_from_hint(hint: str | None) -> WorkMode | None:
    """A fonte declarando a modalidade vale mais que qualquer heurística de texto."""
    if not hint:
        return None
    normalized = hint.strip().casefold().replace("-", "").replace("_", "")
    return {
        "remote": WorkMode.REMOTE,
        "hybrid": WorkMode.HYBRID,
        "onsite": WorkMode.ONSITE,
        "presencial": WorkMode.ONSITE,
    }.get(normalized)


# "Banco de talentos" é cadastro de currículo, não vaga: não há posição aberta
# para se candidatar, e ocupa espaço no canal como se houvesse.
_NOT_A_JOB_RE = re.compile(r"\b(banco de talentos|cadastro de curr[íi]culo|talent pool|candidatura espont[âa]nea)\b", re.I)


# Vaga afirmativa: reservada a um grupo do qual o usuário não faz parte.
# O sinal confiável é a ADJACÊNCIA entre o substantivo e o adjetivo ("vaga
# exclusiva para X"), não a mera coexistência dos termos numa frase. O Itaú
# escreve "vagas sinalizadas como exclusivas ou não para pessoas com deficiência",
# que é um CONVITE, e a versão frouxa lia isso como restrição.
_GROUP = (r"(?:mulher(?:es)?|negr[ao]s?|pretos?|pardos?|pcd|pessoas?\s+com\s+defici[êe]ncia|"
          r"lgbtq?i?a?\+?|ind[íi]genas?|trans|50\+|refugiad[ao]s?)")
_MARK = r"(?:exclusiv|afirmativ|destinad|reservad)\w*"

# No título o contexto já é a própria vaga, então o marcador sozinho basta.
_AFFIRMATIVE_TITLE_RE = re.compile(rf"{_MARK}\W+(?:\w+\W+){{0,3}}?{_GROUP}", re.I)
# Na descrição exige-se a construção completa, com o substantivo colado ao marcador.
_AFFIRMATIVE_DESC_RE = re.compile(
    rf"\b(?:vagas?|posi[çc][ãa]o|posi[çc][õo]es|oportunidades?|processo\s+seletivo)\s+"
    rf"(?:é|s[ãa]o|est[áa]\s+)?{_MARK}\s+(?:a|ao|à|aos|às|para)\s+(?:\w+\s+){{0,3}}?{_GROUP}",
    re.I,
)


# Fontes que declaram o dado estruturalmente (a Sólides tem `affirmative` e
# `pcdOnly`) marcam a vaga com esta tag. Campo declarado vence texto interpretado.
AFFIRMATIVE_TAG = "vaga afirmativa"


def is_affirmative(job: Job) -> bool:
    """True quando a vaga é reservada a um grupo do qual o usuário não faz parte."""
    if any(t.casefold() == AFFIRMATIVE_TAG for t in job.tags):
        return True
    return bool(_AFFIRMATIVE_TITLE_RE.search(job.title) or _AFFIRMATIVE_DESC_RE.search(job.description))


# Linguagens fora do perfil. `java` NÃO pode casar dentro de "javascript": o \b
# final garante isso, e existe um teste travando o comportamento.
_EXCLUDED_LANG_RE = re.compile(
    r"(\bjava\b|\bkotlin\b|\bc#|\bc\+\+|\.net\b|\bdotnet\b|\basp\.net\b|\bspring\s*boot\b|"
    r"\bdelphi\b|\bcobol\b|\babap\b|\bsap\b|\bvisual\s*basic\b|\bvb\.net\b|\bscala\b|\bperl\b)",
    re.I,
)
# Linguagens e frameworks que SÃO do perfil. Servem de contrapeso: uma menção a
# Java num anúncio de Python é "diferencial", não é a vaga.
_PROFILE_LANG_RE = re.compile(
    r"(\bpython\b|\btypescript\b|\bjavascript\b|\bnode(\.?js)?\b|\breact\b|\bnext(\.?js)?\b|"
    r"\brust\b|\bgolang\b|\bgo\b|\bphp\b|\blaravel\b|\bfastapi\b|\bdjango\b|\bpolars\b|\bpandas\b)",
    re.I,
)


# Funções fora do perfil. A função é declarada no TÍTULO, e é só lá que este
# filtro olha: citar "o time de QA" é rotina em vaga de desenvolvimento, e olhar
# a descrição transformaria isso em reprovação.
_EXCLUDED_ROLE_RE = re.compile(
    r"(\bq\.?a\.?\b|\bsdet\b|\btesters?\b|quality\s+assurance|test\s+engineer|"
    r"(analista|engenheir[oa]|especialista|l[íi]der)\s+(de\s+)?(testes?|qualidade\s+de\s+software)|"
    r"automa[çc][ãa]o\s+de\s+testes|garantia\s+de\s+qualidade|"
    r"scrum\s+master|product\s+owner|agile\s+(coach|master)|"
    r"\bdba\b|administrador\s+de\s+banco|"
    r"suporte\s+t[ée]cnico|service\s+desk|help\s+desk|"
    r"ux/ui|(ux|ui|product)\s+designer|recrutador|business\s+analyst)",
    re.I,
)


def has_excluded_role(job: Job) -> bool:
    """True quando o cargo anunciado não é o dele.

    Olha apenas o título: "Product Engineer" é vaga dele e "Product Owner" não é,
    e a diferença só existe no cargo, nunca no corpo do anúncio.
    """
    return bool(_EXCLUDED_ROLE_RE.search(job.title))


def has_excluded_language(job: Job) -> bool:
    """True quando a vaga é de uma stack que o usuário não trabalha.

    Decide por PESO, não por presença. "Desenvolvedor Java Sênior" é vaga de Java,
    mas "(React / Python / Go or Node.js or Java)" lista Java como alternativa e
    descartar isso jogaria fora uma vaga da stack dele. Só o título sem nenhuma
    linguagem própria reprova de imediato.
    """
    def termos(regex: re.Pattern[str], texto: str) -> set[str]:
        return {m.group().casefold() for m in regex.finditer(texto)}

    alheias_titulo = termos(_EXCLUDED_LANG_RE, job.title)
    if alheias_titulo and not termos(_PROFILE_LANG_RE, job.title):
        return True

    texto = f"{job.title} {job.description}"
    alheias = termos(_EXCLUDED_LANG_RE, texto)
    if not alheias:
        return False
    return len(alheias) > len(termos(_PROFILE_LANG_RE, texto))


def passes_hard_filters(job: Job, skills: set[str], min_skill_hits: int = 3) -> tuple[bool, str]:
    """Aplica os cortes inegociáveis. Devolve (passou, motivo da reprovação)."""
    if _NOT_A_JOB_RE.search(job.title):
        return False, "não é vaga (banco de talentos)"

    if detect_seniority(job.title) is Seniority.BELOW:
        return False, "senioridade abaixo de sênior"

    if is_affirmative(job):
        return False, "vaga afirmativa (reservada a grupo específico)"

    if has_excluded_role(job):
        return False, "função fora do perfil"

    if has_excluded_language(job):
        return False, "linguagem principal fora do perfil"

    mode = _mode_from_hint(job.work_mode_hint) or detect_work_mode(job.haystack)
    if mode is WorkMode.ONSITE:
        return False, "modalidade presencial"
    if mode is WorkMode.HYBRID and not in_commute_range(job.location):
        return False, "modalidade híbrida fora da região configurada"

    salary = parse_salary(job.description)
    if salary is not None:
        floor = min_salary(detect_contract(job.haystack))
        if floor and salary < floor:
            return False, f"salário declarado (R$ {salary:,}) abaixo do piso de R$ {floor:,}".replace(",", ".")

    hits = count_skill_hits(job, skills)
    if len(hits) < min_skill_hits:
        return False, f"qualificações insuficientes ({len(hits)} de {min_skill_hits} exigidas)"

    return True, ""
