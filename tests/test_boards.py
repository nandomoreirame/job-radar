"""Configuração de boards ATS (defaults + override por ATS_BOARDS)."""

from job_radar.boards import DEFAULT_BOARDS, parse_ats_boards, resolve_boards


def test_defaults_tem_os_boards_verificados():
    assert "quintoandar" in DEFAULT_BOARDS["greenhouse"]
    assert DEFAULT_BOARDS["greenhouse"]["quintoandar"] == "Grupo QuintoAndar"
    assert DEFAULT_BOARDS["lever"]["neon"] == "Neon"
    assert DEFAULT_BOARDS["ashby"]["nubank"] == "Nubank"
    for slug in ("stone", "inter", "ebanx", "vtex", "wildlifestudios", "gympass", "c6bank", "jusbrasil"):
        assert slug in DEFAULT_BOARDS["greenhouse"]


def test_parse_ats_boards_substitui_defaults():
    raw = "greenhouse:stone=Stone,lever:neon=Neon,ashby:nubank"
    boards = parse_ats_boards(raw)
    assert boards == {
        "greenhouse": {"stone": "Stone"},
        "lever": {"neon": "Neon"},
        "ashby": {"nubank": "nubank"},  # sem nome: usa o slug
    }


def test_entrada_malformada_e_ignorada_com_aviso(capsys):
    boards = parse_ats_boards("greenhouse:ok=OK,quebrado,lever:,ashby:nubank=Nubank,lixo:x=Y")
    assert boards["greenhouse"] == {"ok": "OK"}
    assert boards["ashby"] == {"nubank": "Nubank"}
    assert "lever" not in boards or boards.get("lever") == {}
    err = capsys.readouterr().err
    assert "quebrado" in err or "malform" in err.lower() or "ignor" in err.lower()


def test_resolve_boards_usa_env_quando_setado(monkeypatch):
    monkeypatch.setenv("ATS_BOARDS", "ashby:nubank=Nubank")
    boards = resolve_boards()
    assert list(boards.keys()) == ["ashby"]
    assert boards["ashby"]["nubank"] == "Nubank"


def test_resolve_boards_cai_nos_defaults(monkeypatch):
    monkeypatch.delenv("ATS_BOARDS", raising=False)
    assert resolve_boards() == DEFAULT_BOARDS


def test_resolve_boards_env_todo_invalido_cai_nos_defaults(capsys, monkeypatch):
    monkeypatch.setenv("ATS_BOARDS", "lixo:x=Y,quebrado,outro:=")
    boards = resolve_boards()
    assert boards == DEFAULT_BOARDS
    err = capsys.readouterr().err
    assert "default" in err.lower() or "padrão" in err.lower() or "ignor" in err.lower()
