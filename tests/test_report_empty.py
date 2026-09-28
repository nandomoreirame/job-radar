from job_radar.report import build_empty_embed


def test_diz_que_nada_foi_encontrado():
    e = build_empty_embed({})
    assert "nenhuma vaga" in e["title"].lower()


def _campo(e, nome):
    return next((f["value"] for f in e.get("fields", []) if f["name"] == nome), None)


def test_mostra_o_funil_quando_ha_estatisticas():
    e = build_empty_embed({"coletadas": 526, "avaliadas": 103, "aprovadas": 0,
                           "min_score": 70, "melhor_nota": 65})
    assert _campo(e, "Coletadas") == "526"
    assert _campo(e, "Avaliadas") == "103"


def test_avisa_quando_o_corte_e_o_gargalo():
    # foi exatamente o caso que deixou o radar mudo: teto 65 contra corte 70
    e = build_empty_embed({"avaliadas": 74, "aprovadas": 0, "min_score": 70, "melhor_nota": 65})
    texto = e.get("description", "")
    assert "65" in texto and "70" in texto


def test_sem_coleta_alerta_fonte_em_vez_de_falta_de_vaga():
    # 0 coletadas não é "não apareceu vaga", é fonte quebrada
    e = build_empty_embed({"coletadas": 0, "avaliadas": 0, "aprovadas": 0})
    assert "fonte" in e.get("description", "").lower()


def test_tudo_repetido_nao_e_alarme():
    e = build_empty_embed({"coletadas": 526, "avaliadas": 0, "aprovadas": 0, "ja_enviadas": 526})
    assert "já enviad" in e.get("description", "").lower()
