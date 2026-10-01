"""Gate de robots.txt (RFC 9309), sem rede."""

from job_radar.robots import (
    allowed,
    crawl_delay_from_body,
    is_robots_body,
    select_rules,
)

# Corpo real do Barclays: linhas em branco entre User-agent e as regras.
BARCLAYS = "User-agent: *\n\n\nAllow: /\n\nDisallow: /cs/\n\nSitemap: https://x/sitemap.xml\n"
JOBUP = "User-agent: *\nDisallow: /api/\n"


class TestPathRules:
    def test_linhas_em_branco_dentro_do_registro_nao_encerram(self):
        assert allowed(BARCLAYS, "job-radar", "/cs/") is False

    def test_caminho_permitido_no_mesmo_site(self):
        assert allowed(BARCLAYS, "job-radar", "/careers/") is True

    def test_maior_especificidade_vence_a_ordem(self):
        body = "User-agent: *\nAllow: /\nDisallow: /cs/\n"
        assert allowed(body, "job-radar", "/cs/deep/page") is False

    def test_maior_especificidade_pode_liberar(self):
        body = "User-agent: *\nDisallow: /\nAllow: /jobs/\n"
        assert allowed(body, "job-radar", "/jobs/x") is True
        assert allowed(body, "job-radar", "/other") is False

    def test_empate_de_tamanho_fica_com_allow(self):
        # RFC 9309 §2.2.2: no empate Allow vence (diferente do arquivo portado)
        assert allowed("User-agent: *\nDisallow: /a\nAllow: /a\n", "job-radar", "/a") is True
        assert allowed("User-agent: *\nAllow: /a\nDisallow: /a\n", "job-radar", "/a") is True

    def test_wildcard_e_ancora_final(self):
        body = "User-agent: *\nDisallow: /*.pdf$\n"
        assert allowed(body, "job-radar", "/files/cv.pdf") is False
        assert allowed(body, "job-radar", "/files/cv.pdf.html") is True

    def test_disallow_vazio_libera_tudo(self):
        assert allowed("User-agent: *\nDisallow:\n", "job-radar", "/anything") is True

    def test_robots_vazio_ou_sem_regra_libera(self):
        assert allowed("", "job-radar", "/x") is True
        assert allowed("# só comentário\n", "job-radar", "/x") is True

    def test_comentarios_sao_ignorados(self):
        assert allowed("User-agent: *\nDisallow: /x  # nope\n", "job-radar", "/x") is False

    def test_padrao_percent_encoded_bate_no_caminho_decodificado(self):
        assert allowed("User-agent: *\nDisallow: /foo%20bar\n", "job-radar", "/foo bar") is False
        assert allowed("User-agent: *\nDisallow: /foo%20bar\n", "job-radar", "/foobar") is True


class TestAgentSelection:
    def test_grupo_especifico_do_produto_vence_estrela(self):
        body = "User-agent: job-radar\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        assert allowed(body, "job-radar", "/a") is False
        assert allowed(body, "outro", "/a") is True

    def test_token_do_produto_casa_como_substring(self):
        # o User-Agent completo é "job-radar/0.1 (...)", o grupo declara só "job-radar"
        body = "User-agent: job-radar\nDisallow: /privado\n\nUser-agent: *\nAllow: /\n"
        assert allowed(body, "job-radar/0.1 (+https://x)", "/privado") is False
        assert allowed(body, "job-radar/0.1 (+https://x)", "/ok") is True

    def test_grupo_mais_especifico_vence(self):
        body = (
            "User-agent: job\nDisallow: /a\n\n"
            "User-agent: job-radar\nDisallow: /b\n\n"
            "User-agent: *\nAllow: /\n"
        )
        assert allowed(body, "job-radar", "/b") is False
        assert allowed(body, "job-radar", "/a") is True  # regra de "job" não se aplica

    def test_cai_no_estrela_quando_nao_ha_grupo_do_produto(self):
        assert allowed(JOBUP, "job-radar", "/api/v1") is False

    def test_varios_agentes_compartilham_o_mesmo_bloco(self):
        body = "User-agent: A\nUser-agent: job-radar\nDisallow: /z\n"
        assert allowed(body, "job-radar", "/z") is False
        rules = select_rules(body, "job-radar")
        assert ("disallow", "/z") in [(("allow" if a else "disallow"), p) for a, p in rules]


class TestIsRobotsBody:
    def test_pagina_html_nao_e_robots(self):
        assert is_robots_body("<html><body>404 Not Found</body></html>") is False

    def test_json_nao_e_robots(self):
        assert is_robots_body('{"error":"not found"}') is False

    def test_corpo_vazio_e_robots_valido(self):
        assert is_robots_body("") is True
        assert is_robots_body("\n\n   \n") is True

    def test_politica_real_e_reconhecida(self):
        assert is_robots_body(BARCLAYS) is True
        assert is_robots_body(JOBUP) is True

    def test_sitemap_sozinho_conta(self):
        assert is_robots_body("Sitemap: https://x.example/sitemap.xml\n") is True


class TestCrawlDelay:
    def test_le_crawl_delay_do_grupo_selecionado(self):
        body = "User-agent: job-radar\nCrawl-delay: 2.5\nDisallow:\n\nUser-agent: *\nCrawl-delay: 10\n"
        assert crawl_delay_from_body(body, "job-radar") == 2.5

    def test_sem_crawl_delay_devolve_none(self):
        assert crawl_delay_from_body(JOBUP, "job-radar") is None


class TestFetchStatusHandling:
    """Como o cache interpreta o status HTTP do robots.txt."""

    def test_4xx_significa_sem_restricao(self):
        from job_radar.robots import RobotsCache

        def fetch(_url):
            return 401, b"Unauthorized"

        cache = RobotsCache(fetcher=fetch)
        assert cache.allowed("https://api.ashbyhq.com/posting-api/job-board/x") is True

    def test_404_significa_sem_restricao(self):
        from job_radar.robots import RobotsCache

        cache = RobotsCache(fetcher=lambda _u: (404, b"missing"))
        assert cache.allowed("https://exemplo.com/jobs") is True

    def test_5xx_e_inalcancavel_e_bloqueia(self):
        from job_radar.robots import RobotsCache, RobotsUnreachable

        # sleep noop: o cache retenta 5xx antes de declarar inalcançável
        cache = RobotsCache(fetcher=lambda _u: (503, b"down"), sleep=lambda _: None)
        assert cache.allowed("https://exemplo.com/jobs") is False
        assert cache.unreachable("https://exemplo.com/jobs") is True
        # propriedade útil para a saúde da fonte
        assert isinstance(RobotsUnreachable("x"), Exception)

    def test_erro_de_rede_bloqueia(self):
        from job_radar.robots import RobotsCache

        def fetch(_url):
            raise TimeoutError("timeout")

        cache = RobotsCache(fetcher=fetch, sleep=lambda _: None)
        assert cache.allowed("https://exemplo.com/jobs") is False
        assert cache.unreachable("https://exemplo.com/jobs") is True

    def test_rede_transiente_retenta_antes_de_bloquear(self):
        from job_radar.robots import RobotsCache

        calls = {"n": 0}
        sleeps: list[float] = []

        def fetch(_url):
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("timeout")
            return 200, b"User-agent: *\nAllow: /\n"

        cache = RobotsCache(fetcher=fetch, sleep=sleeps.append, retries=2)
        assert cache.allowed("https://api.ashbyhq.com/jobs") is True
        assert calls["n"] == 3
        assert len(sleeps) == 2

    def test_5xx_transiente_retenta_antes_de_bloquear(self):
        from job_radar.robots import RobotsCache

        calls = {"n": 0}

        def fetch(_url):
            calls["n"] += 1
            if calls["n"] < 2:
                return 503, b"down"
            return 200, b"User-agent: *\nAllow: /\n"

        cache = RobotsCache(fetcher=fetch, sleep=lambda _: None, retries=2)
        assert cache.allowed("https://api.ashbyhq.com/jobs") is True
        assert calls["n"] == 2

    def test_fetcher_padrao_envia_user_agent_completo(self, monkeypatch):
        from job_radar import robots as robots_mod

        monkeypatch.setenv("USER_AGENT", "job-radar-teste/1.0")
        seen = {}

        class _Resp:
            def getcode(self):
                return 200

            def read(self):
                return b"User-agent: *\nAllow: /\n"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=12):
            seen["ua"] = req.headers.get("User-agent") or req.headers.get("User-Agent")
            return _Resp()

        monkeypatch.setattr(robots_mod, "urlopen", fake_urlopen)
        cache = robots_mod.RobotsCache()  # usa _default_fetch
        assert cache.allowed("https://exemplo.com/jobs") is True
        assert seen["ua"] == "job-radar-teste/1.0"

    def test_200_com_html_e_ilegivel_e_bloqueia(self):
        from job_radar.robots import RobotsCache

        cache = RobotsCache(fetcher=lambda _u: (200, b"<html>oops</html>"))
        assert cache.allowed("https://exemplo.com/jobs") is False
        assert cache.unreachable("https://exemplo.com/jobs") is True

    def test_200_com_politica_real_obedece(self):
        from job_radar.robots import RobotsCache

        body = b"User-agent: *\nDisallow: /privado\nAllow: /\n"
        cache = RobotsCache(fetcher=lambda _u: (200, body))
        assert cache.allowed("https://exemplo.com/ok") is True
        assert cache.allowed("https://exemplo.com/privado") is False
        assert cache.unreachable("https://exemplo.com/ok") is False

    def test_cacheia_por_host_uma_unica_busca(self):
        from job_radar.robots import RobotsCache

        calls = []

        def fetch(url):
            calls.append(url)
            return 200, b"User-agent: *\nAllow: /\n"

        cache = RobotsCache(fetcher=fetch)
        assert cache.allowed("https://exemplo.com/a") is True
        assert cache.allowed("https://exemplo.com/b") is True
        assert cache.allowed("https://outro.com/a") is True
        assert calls == ["https://exemplo.com/robots.txt", "https://outro.com/robots.txt"]

    def test_crawl_delay_do_cache(self):
        from job_radar.robots import RobotsCache

        body = b"User-agent: *\nCrawl-delay: 3\nAllow: /\n"
        cache = RobotsCache(fetcher=lambda _u: (200, body))
        assert cache.crawl_delay("https://exemplo.com/jobs") == 3.0
