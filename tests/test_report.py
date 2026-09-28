from job_radar.report import MAX_CHARS_PER_MESSAGE, chunk_embeds, embed_size


def embed(chars: int) -> dict:
    return {"title": "t", "description": "x" * chars, "fields": [], "footer": {"text": ""}}


def test_agrupa_no_maximo_dez_embeds():
    chunks = chunk_embeds([embed(10) for _ in range(25)])
    assert all(len(c) <= 10 for c in chunks)
    assert sum(len(c) for c in chunks) == 25


def test_quebra_antes_de_estourar_o_orcamento_de_caracteres():
    # 8 embeds de 800 chars somam 6400: cabem em 10 por contagem, mas estouram o limite
    chunks = chunk_embeds([embed(800) for _ in range(8)])
    assert len(chunks) > 1
    for chunk in chunks:
        assert sum(embed_size(e) for e in chunk) <= MAX_CHARS_PER_MESSAGE


def test_embed_unico_gigante_nao_trava_o_agrupamento():
    chunks = chunk_embeds([embed(6000)])
    assert len(chunks) == 1
