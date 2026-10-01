"""Country gate e normalização de praça para boards internacionais.

Greenhouse/Lever/Ashby misturam BR com MX/AR/US no mesmo board. Sem este
corte o radar encheria de vaga estrangeira que o dono não pode assumir.
"""

from __future__ import annotations

import re
import unicodedata

# UF por nome do estado (com e sem acento), para "São Paulo, São Paulo, Brazil" → "São Paulo, SP"
_STATE_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "distrito federal": "DF",
    "espirito santo": "ES",
    "goias": "GO",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "para": "PA",
    "paraiba": "PB",
    "parana": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}

_UF_CODES = set(_STATE_UF.values())

_BR_COUNTRY = {"br", "brazil", "brasil", "bra"}

# Nomes longos de país estrangeiro: vencem código UF de 2 letras (MA/PA/SC
# colidem com estados dos EUA). Códigos curtos que também são UF BR (pe/es)
# ficam de fora desta lista — só o nome por extenso conta.
_FOREIGN_COUNTRY_NAMES = {
    "united states", "usa", "estados unidos",
    "mexico", "méxico",
    "argentina",
    "colombia", "colômbia",
    "canada", "canadá",
    "peru", "perú",
    "chile",
    "uruguay", "uruguai",
    "paraguay", "paraguai",
    "ecuador", "equador",
    "bolivia", "bolívia",
    "portugal",
    "germany", "alemanha",
    "spain", "espanha",
    "united kingdom", "england", "reino unido",
    "india", "índia",
    "france", "frança",
    "italy", "itália",
    "netherlands", "holanda",
    "ireland", "irlanda",
    "australia", "austrália",
    "japan", "japão",
    "china",
    "singapore", "singapura",
}

# Códigos ISO/curtos que NÃO colidem com UF brasileiras (pe=Peru/PE, es=Spain/ES)
_FOREIGN_SHORT = {
    "us", "usa", "mx", "ar", "co", "ca", "cl", "uy", "py",
    "ec", "bo", "pt", "de", "gb", "uk", "in", "fr", "it", "nl", "ie", "au", "jp", "cn", "sg",
}

# Remoto acessível do Brasil: LATAM / mundial sem país específico
_REMOTE_OK = re.compile(
    r"\b("
    r"latam|latin\s+america|am[eé]rica\s+latina|south\s+america|"
    r"america\s+do\s+sul|am[eé]rica\s+do\s+sul|"
    r"worldwide|global|anywhere|any\s+where|"
    r"remote\s*[-–]?\s*br"
    r")\b",
    re.I,
)

_BR_HINT = re.compile(
    r"\b(brasil|brazil|latam|latin\s+america|am[eé]rica\s+latina|"
    r"south\s+america|america\s+do\s+sul|am[eé]rica\s+do\s+sul|"
    r"remote\s*[-–]?\s*br)\b",
    re.I,
)

# Capitais / praças frequentes nos boards BR (quando o país não vem no campo)
_BR_CITY = {
    "sao paulo", "rio de janeiro", "belo horizonte", "brasilia", "curitiba",
    "porto alegre", "salvador", "fortaleza", "recife", "campinas", "florianopolis",
    "goiania", "manaus", "belem", "vitoria", "natal", "joao pessoa", "maceio",
    "teresina", "cuiaba", "campo grande", "sao luis", "joinville", "ribeirao preto",
    "uberlandia", "sorocaba", "santos",
}

# word-boundary sobre texto folded: "Curitiba or São Paulo", "São Paulo - SP"
_BR_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in sorted(_BR_CITY, key=len, reverse=True)) + r")\b",
    re.I,
)
_BR_STATE_RE = re.compile(
    r"\b("
    + "|".join(re.escape(s) for s in sorted(_STATE_UF.keys(), key=len, reverse=True))
    + r")\b",
    re.I,
)
_UF_RE = re.compile(
    r"\b(" + "|".join(sorted(_UF_CODES)) + r")\b",
    re.I,
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    return _strip_accents((text or "").strip()).casefold()


def normalize_location(raw: str) -> str:
    """Normaliza para `Cidade, UF` quando dá, para o filtro de commute funcionar.

    `in_commute_range` compara só o pedaço antes da primeira vírgula; manter
    "São Paulo, São Paulo, Brazil" faria a cidade ser "São Paulo" (ok), mas
    exibir "São Paulo, SP" é o que o canal e o dono esperam.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # boards juntam vários locais com "; "
    text = text.split(";")[0].strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return ""

    # "Brasil" / "Brazil" sozinho
    if len(parts) == 1 and _norm(parts[0]) in _BR_COUNTRY | {"brasil", "brazil"}:
        return "Brasil" if _norm(parts[0]) in {"brasil", "brazil", "br", "bra"} else parts[0]

    city = parts[0]
    state_uf = ""
    for part in parts[1:]:
        key = _norm(part)
        if key in _BR_COUNTRY:
            continue
        if key.upper() in _UF_CODES and len(key) == 2:
            state_uf = key.upper()
            break
        if key in _STATE_UF:
            state_uf = _STATE_UF[key]
            break
        # segundo token sem UF conhecida: mantém como veio (ex.: Mexico City)
        if not state_uf:
            state_uf = part
            break

    if state_uf and state_uf.upper() in _UF_CODES:
        return f"{city}, {state_uf.upper()}"
    if state_uf:
        return f"{city}, {state_uf}"
    return city


def _foreign_country_name_in(text: str) -> bool:
    """True se um nome longo de país estrangeiro aparece (vence UF de 2 letras)."""
    n = _norm(text)
    if not n:
        return False
    if n in _FOREIGN_COUNTRY_NAMES:
        return True
    for name in _FOREIGN_COUNTRY_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", n):
            return True
    return False


def _mentions_foreign_country(text: str) -> bool:
    n = _norm(text)
    if not n:
        return False
    if _foreign_country_name_in(text):
        return True
    for token in re.split(r"[\s,;/|_\-]+", n):
        if token in _FOREIGN_SHORT:
            return True
    return False


def _has_br_city(folded: str) -> bool:
    return bool(_BR_CITY_RE.search(folded))


def _has_br_state_name(folded: str) -> bool:
    return bool(_BR_STATE_RE.search(folded))


def _uf_counts_as_brazil(text: str, *, country: str = "") -> bool:
    """UF de 2 letras só conta como BR sem país estrangeiro e com contexto BR.

    "Philadelphia, PA" não passa: PA é UF e estado US, cidade não é BR.
    "Recife, PE" passa: Recife está no conjunto de cidades BR.
    """
    if _foreign_country_name_in(text) or _foreign_country_name_in(country):
        return False
    folded = _norm(text)
    if not _UF_RE.search(folded):
        return False
    if _norm(country) in _BR_COUNTRY:
        return True
    if _BR_HINT.search(text or ""):
        return True
    if _has_br_city(folded) or _has_br_state_name(folded):
        return True
    return False


def _mentions_brazil(text: str, *, country: str = "") -> bool:
    n = _norm(text)
    if not n:
        return False
    if _BR_HINT.search(text or ""):
        return True
    if n in _BR_COUNTRY:
        return True
    # cidade ou nome completo de estado (word-boundary: aguenta "or", "e", "-")
    if _has_br_city(n) or _has_br_state_name(n):
        return True
    # UF nua só com contexto BR (e nunca contra país estrangeiro explícito)
    if _uf_counts_as_brazil(text, country=country):
        return True
    return False


def is_brazil_relevant(
    *,
    location: str = "",
    country: str = "",
    work_mode: str | None = None,
) -> bool:
    """True se a vaga é do Brasil ou remoto aceitável para o dono.

    Mantém: país BR/Brazil/Brasil, ou localização com cidade/estado BR, ou
    remoto com menção a Brasil/LATAM/"Remote - BR", ou remoto sem país algum.
    Descarta: US/Mexico/Argentina/etc. (mesmo híbrido/remoto declarado).
    País estrangeiro por extenso vence código UF de 2 letras (MA≠Maranhão).
    """
    country_n = _norm(country)
    location_s = location or ""

    # país estrangeiro explícito no campo country: corta cedo
    if country_n and (
        country_n in _FOREIGN_COUNTRY_NAMES
        or country_n in _FOREIGN_SHORT
        or _foreign_country_name_in(country)
    ):
        # ainda mantém se a location afirma Brasil com clareza
        if not (_BR_HINT.search(location_s) or _has_br_city(_norm(location_s))):
            return False

    if country_n in _BR_COUNTRY:
        return True

    # país estrangeiro no texto da location vence UF ambígua
    if _foreign_country_name_in(location_s):
        if not (_has_br_city(_norm(location_s)) or _BR_HINT.search(location_s)):
            return False

    if _mentions_brazil(location_s, country=country) or _mentions_brazil(country):
        return True

    remote = (work_mode or "").casefold() in {"remote", "remoto"}

    if remote:
        if _REMOTE_OK.search(location_s) or _BR_HINT.search(location_s):
            return True
        # remoto sem país declarado: boards BR costumam omitir; worldwide/global
        # sem país específico também é acessível do Brasil
        if not country_n and not _mentions_foreign_country(location_s):
            return True
        return False

    # presencial/híbrido sem sinal de Brasil
    if country_n and (
        country_n in _FOREIGN_COUNTRY_NAMES or country_n in _FOREIGN_SHORT
    ):
        return False
    if _mentions_foreign_country(location_s) or _mentions_foreign_country(country):
        return False
    return False
