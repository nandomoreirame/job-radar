"""Log TSV de descartes da rodada."""

from job_radar.discards import HEADER, format_row, write_discards
from job_radar.models import Job


def test_format_row_substitui_tabs_e_newlines():
    job = Job(
        source="gupy",
        external_id="1",
        title="Dev\tSênior\nX",
        company="Acme",
        url="https://x",
    )
    line = format_row(job, "motivo\tcom\ttab")
    assert "\t" not in line.split("\t")[3]  # company cell
    assert "\n" not in line
    assert line.count("\t") == 5


def test_write_sobrescreve_com_header(tmp_path):
    path = tmp_path / "d.tsv"
    job = Job(source="gupy", external_id="1", title="Dev", company="Acme", url="https://x")
    write_discards(path, [format_row(job, "reprovada")], append=False)
    text = path.read_text(encoding="utf-8")
    assert text.startswith(HEADER)
    assert "reprovada" in text


def test_write_append_preserva_linhas(tmp_path):
    path = tmp_path / "d.tsv"
    job = Job(source="gupy", external_id="1", title="Dev", company="Acme", url="https://x")
    write_discards(path, [format_row(job, "a")], append=False)
    write_discards(path, [format_row(job, "b")], append=True)
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[0] == HEADER
    assert sum(1 for ln in lines if ln.startswith("20") or "\tgupy\t" in ln) >= 2
