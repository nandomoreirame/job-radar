"""Country gate e normalização de localização para boards internacionais."""

from job_radar.geo import is_brazil_relevant, normalize_location


class TestNormalizeLocation:
    def test_cidade_estado_pais_vira_cidade_uf(self):
        assert normalize_location("São Paulo, São Paulo, Brazil") == "São Paulo, SP"

    def test_brasil_sozinho_permanece(self):
        assert normalize_location("Brasil") == "Brasil"

    def test_mexico_nao_mapeia_uf_brasileira(self):
        # não inventa UF; devolve o que der para o filtro de commute ler a cidade
        assert normalize_location("Mexico City, Mexico City, Mexico") == "Mexico City, Mexico City"

    def test_varios_locais_usa_o_primeiro(self):
        assert normalize_location("São Paulo, SP; Campinas, SP") == "São Paulo, SP"

    def test_vazio(self):
        assert normalize_location("") == ""


class TestBrazilRelevant:
    def test_mantem_sao_paulo_e_brasil(self):
        assert is_brazil_relevant(location="São Paulo, São Paulo, Brazil") is True
        assert is_brazil_relevant(location="Brasil") is True
        assert is_brazil_relevant(country="BR") is True
        assert is_brazil_relevant(country="Brazil") is True

    def test_descarta_mexico_e_argentina(self):
        assert is_brazil_relevant(location="Mexico City, Mexico City, Mexico") is False
        assert is_brazil_relevant(location="Argentina") is False

    def test_descarta_eua(self):
        assert is_brazil_relevant(
            location="Miami",
            country="United States",
            work_mode="hybrid",
        ) is False
        assert is_brazil_relevant(
            location="Virginia",
            country="United States",
            work_mode="hybrid",
        ) is False

    def test_uf_brasileira_nao_salva_cidade_americana_com_pais(self):
        # MA/PA/SC são UF BR e também estados dos EUA; país explícito vence
        assert is_brazil_relevant(
            location="Boston, MA, United States",
            work_mode="hybrid",
        ) is False
        assert is_brazil_relevant(
            location="Charleston, SC, USA",
            work_mode="onsite",
        ) is False

    def test_cidade_estrangeira_com_uf_nua_sem_pais_cai(self):
        # sem país e sem cidade BR conhecida, o código de 2 letras não conta
        assert is_brazil_relevant(location="Philadelphia, PA", work_mode="onsite") is False

    def test_cidades_brasileiras_com_uf_passam(self):
        assert is_brazil_relevant(location="Recife, PE") is True
        assert is_brazil_relevant(location="Campinas, SP") is True
        assert is_brazil_relevant(location="Rio de Janeiro, RJ") is True
        assert is_brazil_relevant(location="Curitiba") is True

    def test_cidade_br_em_frase_sem_virgula_passa(self):
        # split só em ",;/|" perdia "or", "e", hífen e parênteses
        assert is_brazil_relevant(location="Curitiba or São Paulo") is True
        assert is_brazil_relevant(location="São Paulo e Campinas") is True
        assert is_brazil_relevant(location="São Paulo - SP") is True
        assert is_brazil_relevant(location="(São Paulo)") is True

    def test_remoto_sem_pais_passa(self):
        assert is_brazil_relevant(location="", country="", work_mode="remote") is True

    def test_remoto_com_latam_ou_br_passa(self):
        assert is_brazil_relevant(location="Remote - BR", work_mode="remote") is True
        assert is_brazil_relevant(location="LATAM", work_mode="remote") is True
        assert is_brazil_relevant(location="América Latina", work_mode="remote") is True
        assert is_brazil_relevant(location="Remote - Latin America", work_mode="remote") is True
        assert is_brazil_relevant(location="Remote LATAM", work_mode="remote") is True
        assert is_brazil_relevant(location="South America", work_mode="remote") is True

    def test_remoto_worldwide_ou_anywhere_sem_pais_passa(self):
        assert is_brazil_relevant(location="Remote, anywhere", work_mode="remote") is True
        assert is_brazil_relevant(location="Worldwide", work_mode="remote") is True
        assert is_brazil_relevant(location="Global", work_mode="remote") is True

    def test_remoto_explicito_nos_eua_cai(self):
        assert is_brazil_relevant(
            location="Remote - US",
            country="United States",
            work_mode="remote",
        ) is False

    def test_presencial_sem_sinal_de_brasil_cai(self):
        assert is_brazil_relevant(location="Berlin", work_mode="onsite") is False
