"""Formatação da mensagem publicada no Discord."""

from __future__ import annotations

from job_radar.filters import WorkMode, detect_contract, detect_work_mode, parse_salary, _mode_from_hint
from job_radar.models import Job

MODE_LABEL = {
    WorkMode.REMOTE: "Remoto",
    WorkMode.HYBRID: "Híbrido",
    WorkMode.ONSITE: "Presencial",
    WorkMode.UNKNOWN: "Não informado",
}
COLOR_BY_SCORE = [(90, 0x2ECC71), (75, 0x3498DB), (0, 0x95A5A6)]


def summarize(text: str, limit: int = 320) -> str:
    """Resumo curto: o canal precisa ser escaneável, não completo."""
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    return cut[: cut.rfind(" ")] + "..."


def job_to_embed(job: Job, score: int, reason: str, summary_chars: int = 320) -> dict:
    mode = _mode_from_hint(job.work_mode_hint) or detect_work_mode(job.haystack)
    salary = parse_salary(job.description)
    contract = detect_contract(job.haystack)

    fields = [{"name": "Modalidade", "value": MODE_LABEL[mode], "inline": True}]
    if job.location:
        fields.append({"name": "Local", "value": job.location, "inline": True})
    if contract:
        fields.append({"name": "Contrato", "value": contract, "inline": True})
    if salary:
        fields.append({"name": "Salário", "value": f"R$ {salary:,}".replace(",", "."), "inline": True})
    if job.contact_email:
        fields.append({"name": "E-mail", "value": job.contact_email, "inline": True})
    if job.contact_phone:
        fields.append({"name": "Telefone", "value": job.contact_phone, "inline": True})
    fields.append({"name": "Por que encaixa", "value": summarize(reason, 200), "inline": False})
    fields.append({"name": "Candidatar-se", "value": job.url or "sem link", "inline": False})

    color = next(c for threshold, c in COLOR_BY_SCORE if score >= threshold)
    return {
        "title": f"{job.title} — {job.company}"[:250],
        "url": job.url or None,
        "description": summarize(job.description, summary_chars),
        "color": color,
        "fields": fields,
        "footer": {"text": f"{job.source} · compatibilidade {score}/100"},
    }


MAX_EMBEDS_PER_MESSAGE = 10
MAX_CHARS_PER_MESSAGE = 5500  # o limite real é 6000; a folga cobre o texto de cabeçalho


def embed_size(embed: dict) -> int:
    """Caracteres que o Discord conta no orçamento da mensagem."""
    total = len(embed.get("title") or "") + len(embed.get("description") or "")
    total += len((embed.get("footer") or {}).get("text", ""))
    return total + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))


def chunk_embeds(embeds: list[dict]) -> list[list[dict]]:
    """Agrupa respeitando os DOIS limites do Discord: 10 embeds e 6000 caracteres
    somados por mensagem. Agrupar só por contagem estoura o orçamento e devolve 400."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    running = 0
    for embed in embeds:
        size = embed_size(embed)
        if current and (len(current) >= MAX_EMBEDS_PER_MESSAGE or running + size > MAX_CHARS_PER_MESSAGE):
            chunks.append(current)
            current, running = [], 0
        current.append(embed)
        running += size
    if current:
        chunks.append(current)
    return chunks


# Cinza: é aviso de estado, não oportunidade. Cor distinta dos cards de vaga
# para a mensagem não competir visualmente com o que importa ler.
EMPTY_COLOR = 0x95A5A6


def build_empty_embed(stats: dict) -> dict:
    """Aviso de varredura sem resultado.

    Existe para que silêncio no canal signifique "a automação não rodou", e
    nunca "rodou e não achou". Leva o funil junto porque o número é que separa
    as três causas possíveis: fonte quebrada, tudo repetido, ou corte alto.
    """
    coletadas = stats.get("coletadas")
    avaliadas = stats.get("avaliadas")
    aprovadas = stats.get("aprovadas")
    melhor = stats.get("melhor_nota")
    corte = stats.get("min_score")

    if coletadas == 0:
        motivo = ("Nenhuma vaga voltou das fontes. Isso não é falta de oportunidade: "
                  "provavelmente uma fonte mudou de formato ou está bloqueando o acesso.")
    elif avaliadas == 0 and stats.get("ja_enviadas"):
        motivo = f"Tudo que apareceu já enviado antes ({stats['ja_enviadas']} vagas no histórico desta rodada)."
    elif melhor is not None and corte is not None and melhor < corte:
        motivo = (f"{avaliadas} vaga(s) passaram os filtros, mas nenhuma atingiu o corte: "
                  f"a melhor ficou em {melhor} de {corte}.")
    else:
        motivo = "Nenhuma vaga nova compatível com o perfil nesta varredura."

    fields = []
    for nome, valor in (("Coletadas", coletadas), ("Avaliadas", avaliadas), ("Aprovadas", aprovadas)):
        if valor is not None:
            fields.append({"name": nome, "value": str(valor), "inline": True})
    if melhor is not None and corte is not None:
        fields.append({"name": "Melhor nota", "value": f"{melhor} (corte {corte})", "inline": True})

    return {
        "title": "Nenhuma vaga nova nesta varredura",
        "description": motivo,
        "color": EMPTY_COLOR,
        "fields": fields,
        "footer": {"text": f"job-radar · {stats.get('at', 'sem horário registrado')}"},
    }
