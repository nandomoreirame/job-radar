"""Gate de robots.txt para o job-radar.

Portado de tools/robots_check.py do projeto ai-job-search
(MIT, Copyright (c) 2026 Mads Lorentzen).

Diferenças em relação ao arquivo portado:
- No empate de especificidade (mesmo comprimento de padrão), Allow vence
  (RFC 9309 §2.2.2). O original resolvia o empate a favor de Disallow, por
  cautela no contexto daquele retry de browser.
- Seleção de grupo: o user-agent mais específico que casa como substring
  case-insensitive do token de produto ("job-radar"), senão "*".
- Status HTTP (RFC 9309 §2.3.1.3): 4xx (incl. 401/403/404) = sem restrição;
  5xx ou erro de rede = inalcançável → bloqueia tudo; 2xx cujo corpo não
  parece robots (ex.: página HTML) = ilegível → bloqueia.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

PRODUCT_TOKEN = "job-radar"
_DEFAULT_UA = f"{PRODUCT_TOKEN}/0.1 (+https://github.com/topics/job-search)"

_DIRECTIVES = {"user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host"}


class RobotsDisallowed(Exception):
    """A URL pedida está proibida pelo robots.txt do host."""


class RobotsUnreachable(Exception):
    """robots.txt inacessível ou ilegível; tratamos como bloqueio total."""


def is_robots_body(text: str) -> bool:
    """O corpo parece um robots.txt de verdade?

    Host mal configurado pode responder /robots.txt com 200 e uma página HTML.
    Corpo vazio é allow-all válido (RFC 9309); corpo não-vazio sem diretiva
    reconhecida é tratado como ilegível.
    """
    if not text.strip():
        return True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if ":" in line and line.split(":", 1)[0].strip() in _DIRECTIVES:
            return True
    return False


def _parse_records(text: str) -> tuple[dict[str, list[tuple[bool, str]]], dict[str, float]]:
    """user-agent -> [(is_allow, pattern)] e user-agent -> crawl-delay.

    Linhas em branco dentro de um registro NÃO o encerram (o robotparser da
    stdlib trata como separador e perde regras, falhando aberto).
    """
    rules: dict[str, list[tuple[bool, str]]] = {}
    delays: dict[str, float] = {}
    agents: list[str] = []
    expect_agents = True

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name, value = field_name.strip().lower(), value.strip()
        if field_name == "user-agent":
            if not expect_agents:
                agents, expect_agents = [], True
            agent = value.lower()
            agents.append(agent)
            rules.setdefault(agent, [])
        elif field_name in ("allow", "disallow") and agents:
            expect_agents = False
            for agent in agents:
                rules[agent].append((field_name == "allow", value))
        elif field_name == "crawl-delay" and agents:
            expect_agents = False
            try:
                delay = float(value)
            except ValueError:
                continue
            for agent in agents:
                delays[agent] = delay
    return rules, delays


def _match_length(pattern: str, path: str) -> int:
    """Comprimento do padrão se casa com o path; -1 se não.

    O padrão é percent-decoded para bater no path já decodificado. Sem isso,
    `Disallow: /foo%20bar` nunca casaria com `/foo bar` e a regra seria
    ignorada em silêncio.
    """
    if pattern == "":
        return -1
    pattern = unquote(pattern)
    regex = "^" + "".join(
        ".*" if char == "*" else ("$" if char == "$" else re.escape(char)) for char in pattern
    )
    return len(pattern) if re.match(regex, path) else -1


def _pick_agent(rules: dict[str, list], product: str) -> str | None:
    """Escolhe o user-agent mais específico que casa com o token de produto."""
    product_l = product.lower()
    # substring match: o grupo "job-radar" casa com "job-radar/0.1 (...)"
    candidates = [agent for agent in rules if agent != "*" and agent in product_l]
    if not candidates:
        return "*" if "*" in rules else None
    # mais específico = token mais longo
    return max(candidates, key=len)


def select_rules(text: str, product: str = PRODUCT_TOKEN) -> list[tuple[bool, str]]:
    """Regras (is_allow, pattern) do grupo selecionado para o produto."""
    rules, _ = _parse_records(text)
    agent = _pick_agent(rules, product)
    if agent is None:
        return []
    return list(rules.get(agent) or [])


def allowed(text: str, product: str, path: str) -> bool:
    """True se o path é permitido para o produto neste corpo de robots.txt."""
    best_len, best_allow = -1, True
    for is_allow, pattern in select_rules(text, product):
        length = _match_length(pattern, path)
        # empate: Allow vence (RFC 9309 §2.2.2)
        if length > best_len or (length == best_len and length >= 0 and is_allow):
            best_len, best_allow = length, is_allow
    return True if best_len < 0 else best_allow


def crawl_delay_from_body(text: str, product: str = PRODUCT_TOKEN) -> float | None:
    """Crawl-delay do grupo selecionado, ou None."""
    rules, delays = _parse_records(text)
    agent = _pick_agent(rules, product)
    if agent is None:
        return None
    return delays.get(agent)


def _request_ua() -> str:
    """Mesmo User-Agent das requests de conteúdo (USER_AGENT env ou default)."""
    return os.getenv("USER_AGENT") or _DEFAULT_UA


def _default_fetch(url: str) -> tuple[int, bytes]:
    # UA completo: hosts que bloqueiam o token nu (só "job-radar") aceitam o default
    req = Request(url, headers={"User-Agent": _request_ua(), "Accept": "text/plain,*/*"})
    try:
        with urlopen(req, timeout=12) as resp:  # noqa: S310
            return resp.getcode() or 200, resp.read()
    except Exception as exc:  # noqa: BLE001 — status via HTTPError
        code = getattr(exc, "code", None)
        if isinstance(code, int):
            body = b""
            try:
                body = exc.read()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            return code, body
        raise


@dataclass
class _HostPolicy:
    allow_all: bool = False
    unreachable: bool = False
    body: str = ""
    crawl_delay: float | None = None


@dataclass
class RobotsCache:
    """Cache de robots.txt por scheme+host, válido pela vida do processo.

    Falha transitória (rede/5xx) retenta antes de marcar o host como
    inalcançável: um 503 pontual em api.ashbyhq.com não pode derrubar o board
    inteiro da rodada.
    """

    fetcher: Callable[[str], tuple[int, bytes]] = field(default=_default_fetch)
    product: str = PRODUCT_TOKEN
    retries: int = 2
    sleep: Callable[[float], None] = field(default=time.sleep)
    _cache: dict[str, _HostPolicy] = field(default_factory=dict)

    def _host_key(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}".lower()

    def _path(self, url: str) -> str:
        parts = urlsplit(url)
        path = unquote(parts.path) or "/"
        if parts.query:
            path += "?" + parts.query
        return path

    def _fetch_with_retry(self, robots_url: str) -> tuple[int, bytes] | None:
        """Tenta buscar robots.txt; None = rede esgotou as retentativas."""
        last_exc: BaseException | None = None
        for attempt in range(self.retries + 1):
            try:
                code, raw = self.fetcher(robots_url)
            except Exception as exc:  # noqa: BLE001 — rede: retenta
                last_exc = exc
                if attempt >= self.retries:
                    return None
                self.sleep(min(8.0, 0.5 * (2**attempt)))
                continue
            # 5xx transitório: retenta antes de declarar inalcançável
            if code >= 500 or code < 200:
                if attempt >= self.retries:
                    return code, raw
                self.sleep(min(8.0, 0.5 * (2**attempt)))
                continue
            return code, raw
        if last_exc is not None:
            return None
        return None

    def _load(self, url: str) -> _HostPolicy:
        key = self._host_key(url)
        if key in self._cache:
            return self._cache[key]

        robots_url = f"{key}/robots.txt"
        fetched = self._fetch_with_retry(robots_url)
        if fetched is None:
            policy = _HostPolicy(unreachable=True)
            self._cache[key] = policy
            return policy

        code, raw = fetched

        if 400 <= code < 500:
            # RFC 9309 §2.3.1.3: 4xx = sem restrição publicada
            policy = _HostPolicy(allow_all=True)
            self._cache[key] = policy
            return policy

        if code >= 500 or code < 200:
            policy = _HostPolicy(unreachable=True)
            self._cache[key] = policy
            return policy

        text = raw.decode("utf-8", errors="replace")
        if not is_robots_body(text):
            policy = _HostPolicy(unreachable=True)
            self._cache[key] = policy
            return policy

        policy = _HostPolicy(
            body=text,
            crawl_delay=crawl_delay_from_body(text, self.product),
        )
        self._cache[key] = policy
        return policy

    def allowed(self, url: str) -> bool:
        policy = self._load(url)
        if policy.unreachable:
            return False
        if policy.allow_all:
            return True
        return allowed(policy.body, self.product, self._path(url))

    def unreachable(self, url: str) -> bool:
        return self._load(url).unreachable

    def crawl_delay(self, url: str) -> float | None:
        return self._load(url).crawl_delay
