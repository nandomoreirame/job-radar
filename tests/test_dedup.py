"""Variantes da mesma vaga e quase-duplicatas na rodada."""

from job_radar.dedup import drop_near_duplicates, matches_history_simhash, select_variant
from job_radar.identity import company_key, simhash
from job_radar.models import Job


def _job(**kw) -> Job:
    base = dict(
        source="gupy",
        external_id="1",
        title="Desenvolvedor Python Sênior",
        company="Acme",
        url="https://x/1",
        description="Vaga remota. Python, AWS, TypeScript, Docker, React.",
        work_mode_hint="remote",
    )
    base.update(kw)
    return Job(**base)


def test_escolhe_variante_que_passa_no_filtro(monkeypatch):
    monkeypatch.setenv("COMMUTE_CITIES", "São Paulo")
    skills = {"python", "aws", "typescript"}
    hibrida_longe = _job(
        location="Florianópolis, SC",
        work_mode_hint="hybrid",
        external_id="1",
        url="https://x/1",
    )
    remota = _job(
        location="Remoto",
        work_mode_hint="remote",
        external_id="2",
        url="https://x/2",
    )
    chosen, ok, _reason = select_variant([hibrida_longe, remota], skills, min_skill_hits=3)
    assert ok is True
    assert chosen.work_mode_hint == "remote"
    assert "Florianópolis, SC" in chosen.other_locations


def test_sem_variante_aprovada_fica_com_a_primeira():
    skills = {"python", "aws", "typescript"}
    a = _job(title="Estagiário Python", external_id="1")  # abaixo de sênior
    b = _job(title="Trainee Dev", external_id="2")
    chosen, ok, reason = select_variant([a, b], skills, min_skill_hits=3)
    assert chosen is a
    assert ok is False
    assert "senioridade" in reason


def test_select_variant_devolve_resultado_do_filtro_para_reuso():
    # collect não deve chamar passes_hard_filters de novo na variante escolhida.
    skills = {"python", "aws", "typescript"}
    job = _job()
    chosen, ok, reason = select_variant([job], skills, min_skill_hits=3)
    assert chosen is job
    assert ok is True
    assert reason == ""


def test_drop_near_duplicates_mantem_descricao_maior():
    desc = ("Python AWS Docker Kubernetes TypeScript React FastAPI dados LLM. " * 8)
    curta = desc[: len(desc) // 2]
    a = _job(company="Consultoria X", description=curta, url="https://a")
    b = _job(company="Cliente Y", description=desc, url="https://b")
    kept, dropped = drop_near_duplicates([a, b])
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0].company == "Cliente Y"


def test_drop_near_duplicates_simhash_no_maximo_uma_vez_por_vaga(monkeypatch):
    # Recomputar simhash(other) a cada iteração era O(n²) (~3 ms × 500 ≈ minutos).
    desc = ("Python AWS Docker Kubernetes TypeScript React FastAPI dados LLM. " * 8)
    jobs = [
        _job(company=f"Empresa {i}", description=desc + f" extra {i}.", url=f"https://x/{i}")
        for i in range(8)
    ]
    calls: list[str] = []
    real = simhash

    def counting(text: str):
        calls.append(text)
        return real(text)

    monkeypatch.setattr("job_radar.dedup.simhash", counting)
    drop_near_duplicates(jobs)
    # uma chamada por vaga candidata; kept rivals reusam o hash cacheado
    assert len(calls) == len(jobs)


def test_matches_history_simhash():
    desc = ("Python AWS Docker Kubernetes TypeScript React FastAPI dados LLM. " * 8)
    job = _job(company="Cliente Y", description=desc)
    history = [(simhash(desc), company_key("Consultoria X"))]
    assert matches_history_simhash(job, history) is True
    # mesma empresa: não conta
    history_same = [(simhash(desc), company_key("Cliente Y Ltda"))]
    assert matches_history_simhash(job, history_same) is False
