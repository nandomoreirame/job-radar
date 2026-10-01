"""Modelo canônico de vaga, comum a todas as fontes."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime

from job_radar.identity import job_fingerprint

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def parse_published_at(value: object) -> datetime | None:
    """ISO string -> datetime; inválido/ausente -> None.

    JSON das etapas intermediárias serializa a data como string. Sem o parse,
    o Job fica com str e a penalidade de idade no score nunca aplica.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def clean_html(raw: str | None) -> str:
    """Descrições vêm em HTML em quase toda fonte; o filtro precisa de texto puro.

    `html.unescape` cobre o catálogo de entidades; a lista manual anterior
    perdia casos (&quot;, &apos;, numéricos). Quem recebe HTML escapado duas
    vezes (Greenhouse) deve unescape antes de passar pelo Job.
    """
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


@dataclass
class Job:
    """Uma vaga normalizada, venha de API, RSS ou e-mail."""

    source: str
    external_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    work_mode_hint: str | None = None  # 'remote' | 'hybrid' | 'onsite', quando a fonte declara
    tags: list[str] = field(default_factory=list)
    contact_email: str = ""
    contact_phone: str = ""
    published_at: datetime | None = None
    # Outras cidades da mesma vaga na rodada (Gupy publica uma variante por praça).
    other_locations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        self.location = (self.location or "").strip()
        self.description = clean_html(self.description)
        if self.other_locations is None:
            self.other_locations = []

    @property
    def fingerprint(self) -> str:
        """Identidade da vaga, para não republicar o mesmo anúncio.

        Quando a empresa não foi extraída com confiança, o título sozinho decide:
        a mesma vaga publicada em dois repositórios traz empresas diferentes
        (o nome do repo), e incluí-la geraria duas entradas para um anúncio só.

        Prefere under-merging a over-merging: fundir demais esconde uma vaga em
        silêncio; fundir de menos deixa duplicata visível no canal.
        """
        return job_fingerprint(self.company, self.title)

    @property
    def haystack(self) -> str:
        """Texto único onde os filtros procuram os termos."""
        parts = [self.title, self.company, self.description, " ".join(self.tags), self.location]
        return " ".join(p for p in parts if p).casefold()
