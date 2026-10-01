"""Cliente HTTP compartilhado: retry, Retry-After, robots, sem rede."""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from job_radar.http import RobotsDisallowed, get, get_json, reset_host_pauses
from job_radar.robots import RobotsCache


@pytest.fixture(autouse=True)
def _sem_pausa_entre_hosts():
    reset_host_pauses()
    yield
    reset_host_pauses()


class _FakeResp:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int, body: bytes = b"", headers: dict | None = None) -> HTTPError:
    return HTTPError(
        "https://exemplo.com/x",
        code,
        "err",
        hdrs=headers or {},  # type: ignore[arg-type]
        fp=BytesIO(body),
    )


def test_get_devolve_bytes_em_sucesso():
    sleeps: list[float] = []

    def opener(req, timeout=25):
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    assert (
        get(
            "https://exemplo.com/x",
            opener=opener,
            sleep=sleeps.append,
            robots=robots,
            skip_pace=True,
        )
        == b"ok"
    )
    assert sleeps == []


def test_get_json_decodifica_payload():
    robots = RobotsCache(fetcher=lambda _u: (404, b""))

    def opener(req, timeout=25):
        return _FakeResp(json.dumps({"a": 1}).encode())

    assert get_json(
        "https://exemplo.com/x",
        opener=opener,
        sleep=lambda _: None,
        robots=robots,
        skip_pace=True,
    ) == {"a": 1}


def test_rejeita_url_bloqueada_pelo_robots():
    robots = RobotsCache(fetcher=lambda _u: (200, b"User-agent: *\nDisallow: /\n"))
    with pytest.raises(RobotsDisallowed):
        get(
            "https://exemplo.com/x",
            opener=lambda *a, **k: _FakeResp(b"x"),
            sleep=lambda _: None,
            robots=robots,
            skip_pace=True,
        )


def test_retenta_em_429_e_5xx_com_backoff_exponencial():
    attempts = {"n": 0}
    sleeps: list[float] = []

    def opener(req, timeout=25):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(503)
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    body = get(
        "https://exemplo.com/x",
        opener=opener,
        sleep=sleeps.append,
        robots=robots,
        retries=4,
        jitter=lambda: 0.0,  # determinístico nos testes
        skip_pace=True,
    )
    assert body == b"ok"
    assert attempts["n"] == 3
    # base 0.5, dobra: 0.5 depois 1.0 (sem jitter)
    assert sleeps == [0.5, 1.0]


def test_retenta_em_urlerror_e_timeout():
    attempts = {"n": 0}

    def opener(req, timeout=25):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise URLError("down")
        if attempts["n"] == 2:
            raise TimeoutError("slow")
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    assert (
        get(
            "https://exemplo.com/x",
            opener=opener,
            sleep=lambda _: None,
            robots=robots,
            jitter=lambda: 0.0,
            skip_pace=True,
        )
        == b"ok"
    )
    assert attempts["n"] == 3


def test_nao_retenta_em_outros_4xx():
    def opener(req, timeout=25):
        raise _http_error(404, b"missing")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    with pytest.raises(HTTPError) as exc:
        get(
            "https://exemplo.com/x",
            opener=opener,
            sleep=lambda _: None,
            robots=robots,
            retries=4,
            skip_pace=True,
        )
    assert exc.value.code == 404


def test_retry_statuses_opt_in_retenta_403_com_backoff_fixo():
    """Sólides responde rajada com 403; o caller pede retry explícito em 403/429."""
    attempts = {"n": 0}
    sleeps: list[float] = []

    def opener(req, timeout=25):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(403)
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    body = get(
        "https://exemplo.com/x",
        opener=opener,
        sleep=sleeps.append,
        robots=robots,
        retries=2,
        retry_statuses={403, 429},
        # pacing antigo da Sólides: 5s, 10s
        backoff=lambda attempt, _ra: 5.0 * (attempt + 1),
        skip_pace=True,
    )
    assert body == b"ok"
    assert attempts["n"] == 3
    assert sleeps == [5.0, 10.0]


def test_sem_retry_statuses_403_falha_na_hora():
    def opener(req, timeout=25):
        raise _http_error(403)

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    with pytest.raises(HTTPError) as exc:
        get(
            "https://exemplo.com/x",
            opener=opener,
            sleep=lambda _: None,
            robots=robots,
            retries=4,
            skip_pace=True,
        )
    assert exc.value.code == 403


def test_honra_retry_after_em_segundos_com_teto_de_60():
    attempts = {"n": 0}
    sleeps: list[float] = []

    def opener(req, timeout=25):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, headers={"Retry-After": "12"})
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    get(
        "https://exemplo.com/x",
        opener=opener,
        sleep=sleeps.append,
        robots=robots,
        jitter=lambda: 0.0,
        skip_pace=True,
    )
    assert sleeps == [12.0]

    attempts["n"] = 0
    sleeps.clear()

    def opener_capped(req, timeout=25):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, headers={"Retry-After": "999"})
        return _FakeResp(b"ok")

    get(
        "https://exemplo.com/x",
        opener=opener_capped,
        sleep=sleeps.append,
        robots=robots,
        jitter=lambda: 0.0,
        skip_pace=True,
    )
    assert sleeps == [60.0]


def test_envia_user_agent_do_ambiente(monkeypatch):
    monkeypatch.setenv("USER_AGENT", "meu-radar/9")
    seen = {}

    def opener(req, timeout=25):
        seen["ua"] = req.get_header("User-agent") or req.headers.get("User-agent")
        # urllib guarda headers com capitalização variável
        seen["ua"] = req.headers.get("User-agent") or req.headers.get("User-Agent")
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    get(
        "https://exemplo.com/x",
        opener=opener,
        sleep=lambda _: None,
        robots=robots,
        skip_pace=True,
    )
    assert seen["ua"] == "meu-radar/9"


def test_user_agent_padrao_quando_env_vazio(monkeypatch):
    monkeypatch.delenv("USER_AGENT", raising=False)
    seen = {}

    def opener(req, timeout=25):
        seen["ua"] = req.headers.get("User-agent") or req.headers.get("User-Agent")
        return _FakeResp(b"ok")

    robots = RobotsCache(fetcher=lambda _u: (404, b""))
    get(
        "https://exemplo.com/x",
        opener=opener,
        sleep=lambda _: None,
        robots=robots,
        skip_pace=True,
    )
    assert seen["ua"].startswith("job-radar/")
