from job_radar.sources.programathor import parse_listing

CARD = """
<div class="cell-list ">
  <a href="/jobs/33685-desenvolvedor-back-end-senior-ai-engineer">
    <div class="cell-list-content">
      <h3 class="text-24 line-height-30">Desenvolvedor Back-End Senior (AI Engineer)</h3>
      <div class='cell-list-content-icon'>
        <span><i class='fa fa-briefcase'></i>LOLDESIGN Solucoes Digitais LTDA</span>
        <span><i class='fas fa-map-marker-alt'></i>Remoto</span>
        <span><i class='far fa-chart-bar'></i>Sênior</span>
        <span><i class='far fa-file-alt'></i>PJ</span>
      </div>
      <div><span class='tag-list background-gray'>API</span><span class='tag-list background-gray'>Python</span></div>
    </div>
  </a>
</div>
"""


def test_extrai_titulo_empresa_e_link():
    jobs = parse_listing(CARD)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Desenvolvedor Back-End Senior (AI Engineer)"
    assert job.company == "LOLDESIGN Solucoes Digitais LTDA"
    assert job.url.endswith("/jobs/33685-desenvolvedor-back-end-senior-ai-engineer")


def test_reconhece_modalidade_remota():
    assert parse_listing(CARD)[0].work_mode_hint == "remote"


def test_traz_senioridade_e_contrato_como_tags():
    tags = {t.casefold() for t in parse_listing(CARD)[0].tags}
    assert "sênior" in tags and "pj" in tags
    assert "python" in tags


def test_html_sem_vaga_nao_quebra():
    assert parse_listing("<html><body>nada aqui</body></html>") == []


def test_descarta_vaga_marcada_como_vencida():
    # o board mantém vaga encerrada na listagem, prefixada com "Vencida"
    html = CARD.replace("Desenvolvedor Back-End Senior (AI Engineer)", "Vencida Lead AI Engineer")
    assert parse_listing(html) == []
