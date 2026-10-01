"""Identidade de vaga: fingerprint estável, chave de URL e SimHash de conteúdo.

O fingerprint decide se duas postagens são A MESMA vaga. Erro para o lado de
NÃO fundir: over-merging esconde uma vaga em silêncio; under-merging produz
duplicata visível no canal, que se corrige. Na dúvida, não funde.

SimHash (port de career-ops fingerprint-core.mjs, MIT,
Copyright 2026 Santiago Fernández de Valderrama) pega o caso em que uma
consultoria republica a vaga do cliente com outro nome de empresa: o corpo
quase idêntico, empresas diferentes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

if TYPE_CHECKING:
    from job_radar.models import Job

# Sufixos jurídicos e abreviações de razão social, já na forma fold()'ada.
# Ordem: mais longos primeiro, para "ltda me" sair antes de "ltda"/"me".
_COMPANY_SUFFIXES = (
    "ltda me",
    "ltda",
    "s a",
    "sa",
    "eireli",
    "epp",
    "inc",
    "llc",
    "ltd",
    "corp",
    "gmbh",
    "me",
)

# UFs brasileiras (já casefold). Sozinhas NÃO são tag: "GO"/"TO" colidem com
# linguagem Go e abreviações reais do título.
_UF = frozenset(
    "ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to".split()
)

# Palavras de modalidade / local de trabalho (já fold).
_MODALITY = frozenset(
    {
        "remoto",
        "remota",
        "remote",
        "hibrido",
        "hibrida",
        "hybrid",
        "presencial",
        "onsite",
        "on",
        "site",
        "home",
        "office",
        "homeoffice",
        "teletrabalho",
        "anywhere",
        "100",
    }
)

# Frases de cidade (fold). Matching por frase evita strip de "porto"/"rio"/"go"
# quando o token sozinho é título real (linguagem, bairro, etc.).
_CITY_PHRASES = frozenset(
    {
        "sao paulo",
        "rio de janeiro",
        "rio janeiro",
        "belo horizonte",
        "porto alegre",
        "campo grande",
        "ribeirao preto",
        "brasilia",
        "curitiba",
        "salvador",
        "recife",
        "fortaleza",
        "manaus",
        "belem",
        "goiania",
        "campinas",
        "guarulhos",
        "osasco",
        "barueri",
        "santos",
        "niteroi",
        "florianopolis",
        "vitoria",
        "cuiaba",
        "joinville",
        "sorocaba",
        "uberlandia",
        "londrina",
        "maringa",
        "cotia",
        "jandira",
        "alphaville",
        "brasil",
        "brazil",
        "latam",
    }
)

# Params de tracking universais (casefold). Prefixo utm_ tratado à parte.
# ref/src/source/origin NÃO entram: em páginas pequenas selecionam a vaga.
_TRACKING_PARAMS = frozenset({"gclid", "fbclid"})

# Tracking por host (suffix match no hostname).
_HOST_TRACKING: dict[str, frozenset[str]] = {
    "linkedin.com": frozenset(
        {"trk", "trackingid", "refid", "ebp", "lipi", "originalsubdomain"}
    ),
    "greenhouse.io": frozenset({"gh_src"}),
    "lever.co": frozenset({"lever-source", "lever-origin"}),
    "ashbyhq.com": frozenset({"ashby_src"}),
}

_TRAILING_SEP = re.compile(r"^(?P<head>.*?)\s*[-|/]\s*(?P<tail>[^-|/]+)$")
_TRAILING_PAREN = re.compile(r"^(?P<head>.*?)\s*\((?P<inner>[^()]*)\)\s*$")

SIMHASH_MIN_CHARS = 200
NEAR_DUP_HAMMING = 5


def fold(text: str) -> str:
    """NFKD sem diacríticos, casefold, não-alfanuméricos viram espaço."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    lowered = plain.casefold()
    spaced = re.sub(r"[^0-9a-z]+", " ", lowered)
    return re.sub(r"\s+", " ", spaced).strip()


def _folded_endswith_city(folded_head: str) -> bool:
    """True se o head (já fold) termina numa frase de cidade conhecida."""
    if not folded_head:
        return False
    for phrase in _CITY_PHRASES:
        if folded_head == phrase or folded_head.endswith(" " + phrase):
            return True
    return False


def _segment_is_location_tag(segment: str, *, head: str = "") -> bool:
    """True quando o segmento é só modalidade/cidade (UF só após cidade).

    UF solta ("- GO") e tokens ambíguos ("- Porto") ficam no título: colidem
    com linguagem (Go) e com palavras reais do cargo.
    """
    tokens = fold(segment).split()
    if not tokens:
        return True
    if all(t in _MODALITY for t in tokens):
        return True
    # "Híbrido - São Paulo/SP" dentro de parênteses: mistura modalidade+local
    body = tokens[:]
    while body and body[0] in _MODALITY:
        body = body[1:]
    if not body:
        return True
    phrase = " ".join(body)
    if phrase in _CITY_PHRASES:
        return True
    # UF sozinha só conta se o head termina em cidade ("Goiânia - GO", "SP" após "/")
    if len(body) == 1 and body[0] in _UF:
        return _folded_endswith_city(fold(head))
    # "São Paulo SP" (cidade + UF sem barra)
    if len(body) >= 2 and body[-1] in _UF:
        city_part = " ".join(body[:-1])
        if city_part in _CITY_PHRASES:
            return True
    return False


def _strip_trailing_tags(title: str) -> str:
    """Remove sufixos de local/modalidade que as fontes colam no título.

    Só mexe em segmentos finais após '-', '|', '/' ou dentro de '(...)'.
    Palavras iguais no meio do título real ficam intactas.
    """
    text = (title or "").strip()
    while text:
        changed = False
        m = _TRAILING_PAREN.match(text)
        if m and _segment_is_location_tag(m.group("inner"), head=m.group("head")):
            text = m.group("head").rstrip()
            changed = True
            continue
        m = _TRAILING_SEP.match(text)
        if m and _segment_is_location_tag(m.group("tail"), head=m.group("head")):
            text = m.group("head").rstrip()
            changed = True
            continue
        if not changed:
            break
    return text


def title_key(title: str) -> str:
    """Chave de título: tags de local/modalidade fora, palavras em ordem canônica.

    Conjunto ordenado: 'Backend Sr' e 'Sr Backend' são a mesma vaga.
    """
    cleaned = _strip_trailing_tags(title)
    words = fold(cleaned).split()
    return " ".join(sorted(set(words)))


def company_key(company: str) -> str:
    """Chave de empresa sem sufixo jurídico nem 'Grupo ' inicial."""
    folded = fold(company)
    if not folded:
        return ""
    original = folded
    while True:
        next_val = folded
        if next_val.startswith("grupo ") and next_val[6:]:
            next_val = next_val[6:]
        for suffix in _COMPANY_SUFFIXES:
            token = f" {suffix}"
            if next_val.endswith(token):
                candidate = next_val[: -len(token)].rstrip()
                if candidate:
                    next_val = candidate
                    break
            if next_val == suffix:
                # stripping esvaziaria: para e mantém o valor anterior ao loop
                next_val = folded
                break
        if next_val == folded:
            break
        folded = next_val
    return folded if folded else original


def job_fingerprint(company: str, title: str) -> str:
    """sha256(company_key | title_key)[:16]; só título quando a empresa é vazia."""
    tkey = title_key(title)
    ckey = company_key(company)
    parts = [tkey] if not ckey else [ckey, tkey]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def url_key(url: str) -> str:
    """Identidade canônica da URL publicada (a URL em si nunca é alterada).

    https forçado, host em minúsculas sem www., sem fragmento nem barra final,
    sem params de tracking, params restantes ordenados. Entrada inválida -> ''.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if not parsed.scheme or not parsed.netloc:
        # urlparse("not a url") cai aqui (scheme vazio)
        if "://" not in raw and raw.startswith("http"):
            return ""
        # tenta com https:// se veio host/path sem scheme
        return ""
    scheme = "https"
    host = parsed.hostname or ""
    if not host:
        return ""
    host = host.casefold()
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    host_params: frozenset[str] = frozenset()
    for suffix, params in _HOST_TRACKING.items():
        if host == suffix or host.endswith("." + suffix):
            host_params = params
            break
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lk = key.casefold()
        # utm_* e gclid/fbclid em qualquer host; o resto só no ATS/LinkedIn certo.
        # ref/src/source/origin genéricos ficam: selecionam a vaga na página.
        if lk.startswith("utm_") or lk in _TRACKING_PARAMS or lk in host_params:
            continue
        query_pairs.append((key, value))
    query_pairs.sort(key=lambda kv: (kv[0].casefold(), kv[1]))
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def simhash(text: str) -> int | None:
    """64-bit SimHash sobre shingles de 3 palavras de fold(text).

    Descrição com menos de 200 caracteres (após fold) -> None: pouco sinal,
    risco de falso positivo. Port de career-ops fingerprint-core.mjs (MIT,
    Copyright 2026 Santiago Fernández de Valderrama).
    """
    normalized = fold(text)
    if len(normalized) < SIMHASH_MIN_CHARS:
        return None
    tokens = normalized.split()
    if len(tokens) < 3:
        return None
    weights = [0] * 64
    for i in range(len(tokens) - 2):
        shingle = f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}"
        digest = hashlib.sha1(shingle.encode()).digest()  # noqa: S324 (fingerprint, não crypto)
        for bit in range(64):
            byte = digest[bit >> 3]
            weights[bit] += 1 if (byte >> (7 - (bit & 7))) & 1 else -1
    value = 0
    for bit in range(64):
        if weights[bit] > 0:
            value |= 1 << (63 - bit)
    # força intervalo unsigned 64-bit
    return value & ((1 << 64) - 1)


def hamming(a: int, b: int) -> int:
    """Distância de Hamming entre dois SimHashes de 64 bits."""
    return (a ^ b).bit_count()


def are_near_duplicates(a: Job, b: Job) -> bool:
    """True quando corpos são quase iguais e as empresas SÃO diferentes.

    Mesma empresa já é coberta pelo fingerprint; o alvo aqui é consultoria
    republicando vaga do cliente sob outro nome.
    """
    sa = simhash(a.description)
    sb = simhash(b.description)
    if sa is None or sb is None:
        return False
    if company_key(a.company) == company_key(b.company):
        return False
    return hamming(sa, sb) <= NEAR_DUP_HAMMING


def simhash_hex(value: int | None) -> str:
    """Formato persistido no banco (16 hex chars) ou string vazia."""
    if value is None:
        return ""
    return f"{value:016x}"


def parse_simhash_hex(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw, 16) & ((1 << 64) - 1)
    except ValueError:
        return None
