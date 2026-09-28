"""Modelo canônico de vaga, comum a todas as fontes."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]+")


def clean_html(raw: str | None) -> str:
    """Descrições vêm em HTML em quase toda fonte; o filtro precisa de texto puro."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")):
        text = text.replace(entity, char)
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

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        self.location = (self.location or "").strip()
        self.description = clean_html(self.description)

    @property
    def fingerprint(self) -> str:
        """Identidade da vaga, para não republicar o mesmo anúncio.

        Quando a empresa não foi extraída com confiança, o título sozinho decide:
        a mesma vaga publicada em dois repositórios traz empresas diferentes
        (o nome do repo), e incluí-la geraria duas entradas para um anúncio só.
        """
        title = _PUNCT_RE.sub(" ", self.title.casefold())
        parts = [_WS_RE.sub(" ", title).strip()]
        if self.company:
            parts.insert(0, _WS_RE.sub(" ", self.company.casefold()).strip())
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    @property
    def haystack(self) -> str:
        """Texto único onde os filtros procuram os termos."""
        parts = [self.title, self.company, self.description, " ".join(self.tags), self.location]
        return " ".join(p for p in parts if p).casefold()
