"""Identidade de vaga: fingerprint, URL e SimHash."""

from job_radar.identity import (
    company_key,
    fold,
    hamming,
    simhash,
    title_key,
    url_key,
)
from job_radar.models import Job


class TestFold:
    def test_remove_acentos_e_pontuacao(self):
        assert fold("Desenvolvedor Sênior!") == "desenvolvedor senior"

    def test_colapsa_espacos(self):
        assert fold("  Foo   Bar  ") == "foo bar"


class TestTitleKey:
    def test_ordem_das_palavras_nao_muda_a_chave(self):
        assert title_key("Backend Sr") == title_key("Sr Backend")

    def test_acento_nao_muda_a_chave(self):
        assert title_key("Desenvolvedor Sênior") == title_key("Desenvolvedor Senior")

    def test_remove_tag_remoto_entre_parenteses(self):
        assert title_key("Engenheiro de Dados (Remoto)") == title_key("Engenheiro de Dados")

    def test_remove_sufixo_cidade_apos_traco(self):
        assert title_key("Dev Sênior - São Paulo") == title_key("Dev Sênior")

    def test_remove_cidade_barra_uf(self):
        assert title_key("Engenheiro de Dados - São Paulo/SP") == title_key(
            "Engenheiro de Dados"
        )

    def test_remove_hibrido_com_cidade_nos_parenteses(self):
        assert title_key("Tech Lead (Híbrido - São Paulo/SP)") == title_key("Tech Lead")

    def test_remove_uf_quando_cidade_precede(self):
        # Goiânia é cidade conhecida: a UF solta depois do traço é tag de local.
        assert title_key("Engenheiro de Dados - Goiânia - GO") == title_key(
            "Engenheiro de Dados"
        )

    def test_nao_remove_palavra_do_meio_do_titulo(self):
        # "remoto" no meio de um título real permanece
        chave = title_key("Engenheiro Remoto de Plataforma")
        assert "remoto" in chave

    def test_go_solto_nao_e_uf_de_local(self):
        # "GO" sozinho pode ser a linguagem Go; UF só sai após cidade ou "/".
        assert title_key("Desenvolvedor - GO") != title_key("Desenvolvedor - Remoto")
        assert "go" in title_key("Desenvolvedor - GO")

    def test_to_solto_nao_e_uf_de_local(self):
        assert title_key("Dev - TO") != title_key("Dev - Remoto")
        assert "to" in title_key("Dev - TO")

    def test_porto_solto_nao_e_cidade(self):
        assert title_key("Desenvolvedor - Porto") != title_key("Desenvolvedor - Remoto")
        assert "porto" in title_key("Desenvolvedor - Porto")

    def test_backend_go_distinto_de_backend_remoto(self):
        assert title_key("Desenvolvedor Backend - GO") != title_key(
            "Desenvolvedor Backend - Remoto"
        )


class TestCompanyKey:
    def test_remove_sufixo_ltda(self):
        assert company_key("Acme Ltda") == company_key("Acme")

    def test_remove_s_a_e_variantes(self):
        assert company_key("Acme S.A.") == company_key("Acme SA") == company_key("Acme")

    def test_remove_grupo_no_inicio(self):
        assert company_key("Grupo Acme") == company_key("Acme")

    def test_nunca_esvazia(self):
        assert company_key("Ltda") == fold("Ltda")


class TestFingerprint:
    def test_empresa_com_e_sem_sufixo_legal_sao_a_mesma(self):
        a = Job(source="gupy", external_id="1", title="Dev Sênior", company="Acme Ltda", url="u")
        b = Job(source="gupy", external_id="2", title="Dev Senior", company="Acme S.A.", url="v")
        assert a.fingerprint == b.fingerprint

    def test_titulo_com_ordem_diferente_e_a_mesma_vaga(self):
        a = Job(source="gupy", external_id="1", title="Backend Sr", company="Acme", url="u")
        b = Job(source="gupy", external_id="2", title="Sr Backend", company="Acme", url="v")
        assert a.fingerprint == b.fingerprint

    def test_sem_empresa_usa_so_o_titulo(self):
        a = Job(source="gh", external_id="1", title="Engenheiro de Dados", company="", url="u")
        b = Job(source="gh", external_id="2", title="Engenheiro de Dados", company="", url="v")
        assert a.fingerprint == b.fingerprint
        # com empresa distinta NÃO colapsa no título-only da outra
        c = Job(source="gh", external_id="3", title="Engenheiro de Dados", company="Outra", url="w")
        assert a.fingerprint != c.fingerprint


class TestUrlKey:
    def test_normaliza_https_www_e_barra_final(self):
        assert url_key("http://WWW.Example.com/jobs/1/") == url_key("https://example.com/jobs/1")

    def test_remove_params_de_tracking(self):
        assert url_key("https://x.com/j?utm_source=li&id=1&fbclid=abc") == url_key(
            "https://x.com/j?id=1"
        )

    def test_ordena_params_restantes(self):
        assert url_key("https://x.com/j?b=2&a=1") == url_key("https://x.com/j?a=1&b=2")

    def test_vazio_ou_invalido_devolve_string_vazia(self):
        assert url_key("") == ""
        assert url_key("not a url") == ""

    def test_remove_fragmento(self):
        assert url_key("https://x.com/j#topo") == url_key("https://x.com/j")

    def test_ref_generico_distingue_vagas_na_mesma_pagina(self):
        # Em páginas pequenas ref/src/source/origin selecionam a vaga; strip
        # genérico colidia e is_new silenciava a segunda por 45 dias.
        a = url_key("https://x.com/vaga?ref=2")
        b = url_key("https://x.com/vaga?ref=3")
        assert a != b
        assert "ref=2" in a and "ref=3" in b

    def test_src_source_origin_genericos_permanecem(self):
        assert "src=a" in url_key("https://careers.example.com/j?src=a")
        assert "source=b" in url_key("https://careers.example.com/j?source=b")
        assert "origin=c" in url_key("https://careers.example.com/j?origin=c")

    def test_linkedin_remove_tracking_especifico(self):
        raw = (
            "https://www.linkedin.com/jobs/view/123?"
            "trk=public&trackingId=x&refId=y&eBP=z&lipi=w&utm_source=li"
        )
        assert url_key(raw) == url_key("https://linkedin.com/jobs/view/123")

    def test_gh_src_e_lever_ashby_sao_host_especificos(self):
        assert url_key("https://boards.greenhouse.io/acme/jobs/1?gh_src=li") == url_key(
            "https://boards.greenhouse.io/acme/jobs/1"
        )
        assert url_key(
            "https://jobs.lever.co/acme/abc?lever-source=li&lever-origin=x"
        ) == url_key("https://jobs.lever.co/acme/abc")
        assert url_key("https://jobs.ashbyhq.com/acme/1?ashby_src=li") == url_key(
            "https://jobs.ashbyhq.com/acme/1"
        )

    def test_jobboardsource_da_gupy_permanece(self):
        assert "jobBoardSource=gupy" in url_key(
            "https://example.gupy.io/jobs/1?jobBoardSource=gupy"
        )


class TestSimHash:
    def test_descricao_curta_devolve_none(self):
        assert simhash("texto curto demais") is None

    def test_textos_identicos_tem_hamming_zero(self):
        texto = " ".join(["python aws docker kubernetes typescript fastapi"] * 20)
        a = simhash(texto)
        b = simhash(texto)
        assert a is not None and b is not None
        assert hamming(a, b) == 0

    def test_textos_parecidos_ficam_perto(self):
        # uma troca mínima num corpo longo fica dentro do limiar (≤5 bits)
        base = (
            "Buscamos engenheiro sênior com Python, AWS, Docker, TypeScript e FastAPI. "
            "Experiência com dados, LLMs e pipelines de ML é diferencial. "
            "Trabalho remoto com time distribuído no Brasil. "
        ) * 6
        a = simhash(base)
        b = simhash(base.replace("diferencial", "desejavel", 1))
        assert a is not None and b is not None
        assert hamming(a, b) <= 5

    def test_empresas_diferentes_com_corpo_igual_sao_quase_duplicata(self):
        from job_radar.identity import are_near_duplicates

        desc = ("Requisitos: Python, AWS, Docker, Kubernetes, TypeScript, React. " * 8)
        a = Job(source="gh", external_id="1", title="Dev", company="Consultoria X",
                url="https://a", description=desc)
        b = Job(source="gh", external_id="2", title="Dev", company="Cliente Y",
                url="https://b", description=desc)
        assert are_near_duplicates(a, b) is True

    def test_mesma_empresa_nao_e_quase_duplicata_por_simhash(self):
        # mesma empresa já é coberta pelo fingerprint; simhash não deve marcar
        from job_radar.identity import are_near_duplicates

        desc = ("Requisitos: Python, AWS, Docker, Kubernetes, TypeScript, React. " * 8)
        a = Job(source="gh", external_id="1", title="Dev A", company="Acme",
                url="https://a", description=desc)
        b = Job(source="gh", external_id="2", title="Dev B", company="Acme Ltda",
                url="https://b", description=desc)
        assert are_near_duplicates(a, b) is False
