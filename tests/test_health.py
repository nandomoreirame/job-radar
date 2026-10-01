"""Saúde por fonte: status derivado de requests/jobs/erros."""

from job_radar.health import SourceHealth, is_degraded_job, update_failure_streaks
from job_radar.models import Job


def _job(**kwargs) -> Job:
    base = dict(source="x", external_id="1", title="Dev", company="Acme", url="https://x.com/1")
    base.update(kwargs)
    return Job(**base)


class TestStatus:
    def test_ok_quando_ha_vagas_saudaveis(self):
        h = SourceHealth(name="gupy")
        h.record_ok()
        h.record_job(_job())
        assert h.status == "ok"
        assert h.jobs == 1

    def test_vazia_quando_requests_ok_sem_vagas(self):
        h = SourceHealth(name="gupy")
        h.record_ok()
        h.record_ok()
        assert h.status == "vazia"
        assert h.requests == 2 and h.ok == 2

    def test_sem_resposta_quando_todas_as_requests_falharam(self):
        h = SourceHealth(name="gupy")
        h.record_error("timeout")
        h.record_error("503")
        assert h.status == "sem_resposta"
        assert h.ok == 0 and h.requests == 2

    def test_degradada_quando_todas_as_vagas_estao_ruins(self):
        h = SourceHealth(name="gupy")
        h.record_ok()
        h.record_job(_job(company="", title="Dev &amp; Lead"))
        h.record_job(_job(company="", title="<b>Dev</b>", url="ftp://x"))
        assert h.status == "degradada"
        assert h.degraded == 2

    def test_ok_quando_so_parte_esta_degradada(self):
        h = SourceHealth(name="gupy")
        h.record_ok()
        h.record_job(_job())
        h.record_job(_job(company=""))
        assert h.status == "ok"
        assert h.degraded == 1

    def test_degradada_quando_toda_resposta_veio_sem_payload(self):
        h = SourceHealth(name="x")
        for _ in range(3):
            h.record_ok()
            h.record_parse_error("payload ausente")
        assert h.requests == 3
        assert h.status == "degradada"

    def test_vazia_quando_so_parte_das_respostas_veio_sem_payload(self):
        h = SourceHealth(name="x")
        h.record_ok()
        h.record_ok()
        h.record_parse_error("payload ausente")
        assert h.status == "vazia"

    def test_guarda_no_maximo_cinco_erros(self):
        h = SourceHealth(name="gupy")
        for i in range(7):
            h.record_error(f"e{i}")
        assert h.errors == ["e0", "e1", "e2", "e3", "e4"]

    def test_to_dict_para_last_run(self):
        h = SourceHealth(name="gupy")
        h.record_ok()
        h.record_job(_job())
        d = h.to_dict()
        assert d == {
            "status": "ok",
            "requests": 1,
            "ok": 1,
            "jobs": 1,
            "degraded": 0,
            "errors": [],
        }


class TestDegradedJob:
    def test_empresa_vazia_degrada(self):
        assert is_degraded_job(_job(company="")) is True

    def test_titulo_com_entidade_ou_tag_degrada(self):
        assert is_degraded_job(_job(title="A &amp; B")) is True
        assert is_degraded_job(_job(title="A < B")) is True

    def test_url_nao_http_degrada(self):
        assert is_degraded_job(_job(url="javascript:alert(1)")) is True
        assert is_degraded_job(_job(url="")) is True

    def test_vaga_normal_nao_degrada(self):
        assert is_degraded_job(_job()) is False


class TestFailureStreak:
    def test_incrementa_em_sem_resposta_e_zera_nos_outros(self):
        prev = {"gupy": 2, "github": 1}
        health = {
            "gupy": {"status": "sem_resposta"},
            "github": {"status": "ok"},
            "solides": {"status": "vazia"},
        }
        nxt = update_failure_streaks(prev, health)
        assert nxt == {"gupy": 3, "github": 0, "solides": 0}


class TestHealthWarnings:
    def test_formata_aviso_com_streak(self):
        from job_radar.health import format_health_warnings

        lines = format_health_warnings(
            {
                "gupy": {"status": "sem_resposta", "requests": 12, "ok": 0},
                "github": {"status": "ok", "requests": 1, "ok": 1},
            },
            {"gupy": 2},
        )
        assert len(lines) == 1
        assert "gupy" in lines[0] and "sem resposta" in lines[0]
        assert "0/12" in lines[0]
        assert "2 falhas seguidas" in lines[0]
