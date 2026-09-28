import json

from job_radar.runstats import merge_stats, read_stats, write_stats


def test_grava_e_le(tmp_path):
    p = tmp_path / "last_run.json"
    write_stats(p, coletadas=526, reprovadas=404)
    assert read_stats(p)["coletadas"] == 526


def test_segunda_escrita_soma_ao_inves_de_substituir(tmp_path):
    # collect e triage escrevem em etapas diferentes da mesma rodada
    p = tmp_path / "last_run.json"
    write_stats(p, coletadas=526)
    write_stats(p, avaliadas=103, aprovadas=8)
    d = read_stats(p)
    assert d["coletadas"] == 526 and d["avaliadas"] == 103 and d["aprovadas"] == 8


def test_arquivo_ausente_devolve_vazio(tmp_path):
    assert read_stats(tmp_path / "nao_existe.json") == {}


def test_arquivo_corrompido_nao_quebra(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{isso não é json", encoding="utf-8")
    assert read_stats(p) == {}


def test_merge_registra_o_horario(tmp_path):
    p = tmp_path / "r.json"
    write_stats(p, coletadas=1)
    assert "at" in read_stats(p)


def test_merge_puro_nao_toca_disco():
    assert merge_stats({"a": 1}, {"b": 2})["a"] == 1
    assert merge_stats({"a": 1}, {"a": 9})["a"] == 9


def test_reset_descarta_a_rodada_anterior(tmp_path):
    # o collect abre a rodada: sem reset, um número velho do triage sobreviveria
    # e a mensagem de "nada encontrado" citaria o funil da varredura passada
    p = tmp_path / "r.json"
    write_stats(p, coletadas=500, avaliadas=99, aprovadas=8)
    write_stats(p, coletadas=10, reset=True)
    d = read_stats(p)
    assert d["coletadas"] == 10
    assert "avaliadas" not in d and "aprovadas" not in d
