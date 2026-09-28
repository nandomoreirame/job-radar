from job_radar.contact import extract_email, extract_phone


def test_extrai_email_de_candidatura():
    assert extract_email("Envie seu CV para vagas@empresa.com.br") == "vagas@empresa.com.br"


def test_ignora_email_de_privacidade_e_do_ats():
    # rodapé de LGPD e domínio do próprio ATS não servem para candidatura
    assert extract_email("Dúvidas: privacidade@empresa.com") == ""
    assert extract_email("suporte da plataforma: ajuda@gupy.io") == ""


def test_sem_email_retorna_vazio():
    assert extract_email("Candidate-se pelo botão acima.") == ""


def test_extrai_telefone_br():
    assert extract_phone("WhatsApp (11) 98765-4321") == "(11) 98765-4321"


def test_sem_telefone_retorna_vazio():
    assert extract_phone("Nenhum contato aqui") == ""
