"""Cliente HTTP compartilhado: User-Agent, robots.txt, retry com backoff.

Conectores não falam mais com urllib direto. Assim a política de acesso
(identidade, robots, pausa, retry) fica num lugar só e os testes injetam
opener/sleep/robots sem rede.
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from job_radar.robots import PRODUCT_TOKEN, RobotsCache, RobotsDisallowed

DEFAULT_UA = f"{PRODUCT_TOKEN}/0.1 (+https://github.com/topics/job-search)"
_DEFAULT_ROBOTS = RobotsCache()

# último instante de request por host, para respeitar Crawl-delay / pausa mínima
_last_request_at: dict[str, float] = {}

# reexport: quem importa de http não precisa conhecer robots
__all__ = ["RobotsDisallowed", "get", "get_json", "default_headers", "reset_host_pauses"]

BackoffFn = Callable[[int, str | None], float]


def default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": os.getenv("USER_AGENT") or DEFAULT_UA, "Accept": "*/*"}
    if extra:
        headers.update(extra)
    return headers


def reset_host_pauses() -> None:
    """Zera o relógio de pausa entre hosts (útil nos testes)."""
    _last_request_at.clear()


def _host_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _respect_pace(
    url: str,
    *,
    sleep: Callable[[float], None],
    robots: RobotsCache,
    min_pause: float = 1.0,
    now: Callable[[], float] = time.monotonic,
) -> None:
    """Espera pelo menos max(1s, Crawl-delay) desde o último request ao host."""
    key = _host_key(url)
    delay = robots.crawl_delay(url)
    pause = max(min_pause, delay or 0.0)
    last = _last_request_at.get(key)
    if last is not None:
        wait = pause - (now() - last)
        if wait > 0:
            sleep(wait)


def _backoff_seconds(attempt: int, retry_after: str | None, jitter: Callable[[], float]) -> float:
    """Backoff exponencial (0.5 → 8) + jitter, ou Retry-After (teto 60s)."""
    if retry_after is not None:
        try:
            return min(60.0, max(0.0, float(retry_after.strip())))
        except ValueError:
            pass
    base = min(8.0, 0.5 * (2**attempt))
    return base + jitter()


def get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    retries: int = 4,
    sleep: Callable[[float], None] = time.sleep,
    opener: Callable[..., object] | None = None,
    robots: RobotsCache | None = None,
    jitter: Callable[[], float] | None = None,
    min_pause: float = 1.0,
    skip_pace: bool = False,
    retry_statuses: set[int] | None = None,
    backoff: BackoffFn | None = None,
) -> bytes:
    """GET com robots, User-Agent, retry em 429/5xx/rede e pausa por host.

    `retry_statuses` acrescenta códigos 4xx opt-in (ex.: {403, 429} na Sólides,
    que responde rajada com 403). `backoff(attempt, retry_after)` substitui o
    exponencial padrão quando o caller precisa de pacing fixo (5s/10s).
    """
    robots = robots if robots is not None else _DEFAULT_ROBOTS
    jitter = jitter if jitter is not None else (lambda: random.uniform(0.0, 0.5))
    open_url = opener or urlopen
    extra_retry = retry_statuses or set()

    if not robots.allowed(url):
        raise RobotsDisallowed(url)

    if not skip_pace:
        _respect_pace(url, sleep=sleep, robots=robots, min_pause=min_pause)

    req = Request(url, headers=default_headers(headers))
    last_exc: BaseException | None = None

    for attempt in range(retries + 1):
        try:
            with open_url(req, timeout=timeout) as resp:  # noqa: S310
                body = resp.read()  # type: ignore[union-attr]
            _last_request_at[_host_key(url)] = time.monotonic()
            return body
        except HTTPError as exc:
            last_exc = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600 or exc.code in extra_retry
            if retryable:
                if attempt >= retries:
                    break
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if backoff is not None:
                    sleep(backoff(attempt, retry_after))
                else:
                    sleep(_backoff_seconds(attempt, retry_after, jitter))
                continue
            raise
        except (URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            if backoff is not None:
                sleep(backoff(attempt, None))
            else:
                sleep(_backoff_seconds(attempt, None, jitter))
            continue

    assert last_exc is not None
    raise last_exc


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    retries: int = 4,
    sleep: Callable[[float], None] = time.sleep,
    opener: Callable[..., object] | None = None,
    robots: RobotsCache | None = None,
    jitter: Callable[[], float] | None = None,
    min_pause: float = 1.0,
    skip_pace: bool = False,
    retry_statuses: set[int] | None = None,
    backoff: BackoffFn | None = None,
) -> object:
    """GET + json.loads. Mesmos knobs de `get`."""
    raw = get(
        url,
        headers=headers,
        timeout=timeout,
        retries=retries,
        sleep=sleep,
        opener=opener,
        robots=robots,
        jitter=jitter,
        min_pause=min_pause,
        skip_pace=skip_pace,
        retry_statuses=retry_statuses,
        backoff=backoff,
    )
    return json.loads(raw.decode("utf-8"))
