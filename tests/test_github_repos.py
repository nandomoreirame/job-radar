from job_radar.sources.github_repos import parse_issue, parse_title


class TestParseTitle:
    def test_modalidade_e_empresa_com_na(self):
        role, company, mode, city = parse_title("[Híbrido-SP] Fullstack developer Python/React & IA na Evertec 🧡")
        assert company == "Evertec"
        assert mode == "hybrid"
        assert city == "SP"
        assert "Fullstack developer" in role

    def test_empresa_entre_parenteses(self):
        role, company, mode, city = parse_title("[Híbrido/Curitiba] Tech Lead - USD (Jcal)")
        assert company == "Jcal"
        assert mode == "hybrid"
        assert city == "Curitiba"

    def test_remoto_sem_cidade(self):
        role, company, mode, city = parse_title("[Remoto] Back-end Engineer")
        assert mode == "remote"
        assert city == ""

    def test_titulo_fora_do_padrao_nao_quebra(self):
        role, company, mode, city = parse_title("Vaga para pessoa desenvolvedora")
        assert role == "Vaga para pessoa desenvolvedora"
        assert mode == ""


class TestParseIssue:
    def test_extrai_email_de_contato_do_corpo(self):
        issue = {
            "number": 42,
            "title": "[Remoto] Engenheiro de Dados na Acme",
            "body": "Vaga sênior. Envie CV para talentos@acme.com.br",
            "html_url": "https://github.com/x/y/issues/42",
            "labels": [{"name": "Sênior"}],
            "created_at": "2026-09-01T10:00:00Z",
        }
        job = parse_issue(issue, "datascience-br/vagas")
        assert job.contact_email == "talentos@acme.com.br"
        assert job.company == "Acme"
        assert job.work_mode_hint == "remote"
        assert job.source == "github:datascience-br"

    def test_modalidade_vem_da_label_quando_o_titulo_nao_traz(self):
        issue = {
            "number": 7, "title": "Pessoa Desenvolvedora Sênior", "body": "texto",
            "html_url": "u", "labels": [{"name": "Remoto"}], "created_at": "2026-09-01T10:00:00Z",
        }
        assert parse_issue(issue, "frontendbr/vagas").work_mode_hint == "remote"


class TestFrescor:
    def test_descarta_vaga_antiga(self):
        # issue aberta há 570 dias com e-mail já desativado foi o caso real que motivou isto
        from datetime import datetime, timedelta, timezone

        from job_radar.sources.github_repos import is_fresh
        from job_radar.models import Job

        antiga = Job(source="github", external_id="1", title="Dev", company="X", url="u",
                     published_at=datetime.now(timezone.utc) - timedelta(days=570))
        assert is_fresh(antiga, 45) is False

    def test_mantem_vaga_recente(self):
        from datetime import datetime, timedelta, timezone

        from job_radar.sources.github_repos import is_fresh
        from job_radar.models import Job

        nova = Job(source="github", external_id="2", title="Dev", company="X", url="u",
                   published_at=datetime.now(timezone.utc) - timedelta(days=10))
        assert is_fresh(nova, 45) is True

    def test_vaga_sem_data_passa(self):
        from job_radar.sources.github_repos import is_fresh
        from job_radar.models import Job

        sem_data = Job(source="github", external_id="3", title="Dev", company="X", url="u")
        assert is_fresh(sem_data, 45) is True


def test_nao_usa_nome_do_repo_como_empresa():
    # dois repos publicando a mesma vaga geravam "empresas" diferentes e duplicavam
    issue = {"number": 1, "title": "Product Engineer (LLMs, Next.js)", "body": "x",
             "html_url": "u", "labels": [], "created_at": "2026-09-20T10:00:00Z"}
    a = parse_issue(issue, "frontendbr/vagas")
    b = parse_issue(issue, "backend-br/vagas")
    assert a.company == "" and b.company == ""
    assert a.fingerprint == b.fingerprint


def test_remove_colchete_final_do_titulo():
    issue = {"number": 2, "title": "[Remoto] Senior Backend na Pontaltech [PJ, LATAM]", "body": "x",
             "html_url": "u", "labels": [], "created_at": "2026-09-20T10:00:00Z"}
    assert parse_issue(issue, "phpdevbr/vagas").company == "Pontaltech"


def test_parenteses_com_stack_nao_vira_empresa():
    role, company, _, _ = parse_title("Product Engineer (LLMs, Next.js, Python)")
    assert company == ""
    assert "Product Engineer" in role


def test_parenteses_com_nome_curto_vira_empresa():
    _, company, _, _ = parse_title("[Híbrido/Curitiba] Tech Lead - USD (Jcal)")
    assert company == "Jcal"
