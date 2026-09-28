"""Extração de contato direto da descrição da vaga.

A maioria das vagas de ATS não expõe contato: a candidatura é pelo próprio
sistema. Quando a descrição traz e-mail ou telefone, normalmente é vaga de
agência ou de empresa pequena, e aí a candidatura por e-mail é possível.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+55\s*)?\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}\b")

# E-mails que não servem para candidatura (ruído de rodapé, LGPD, imprensa)
_BLOCKED_LOCAL = {"privacidade", "lgpd", "dpo", "imprensa", "contato", "suporte", "sac", "noreply", "no-reply"}
_BLOCKED_DOMAIN = {"gupy.io", "sentry.io", "example.com"}


def extract_email(text: str) -> str:
    """Primeiro e-mail plausível para candidatura, ou vazio."""
    for match in _EMAIL_RE.finditer(text or ""):
        email = match.group(0).casefold().rstrip(".")
        local, _, domain = email.partition("@")
        if local in _BLOCKED_LOCAL or domain in _BLOCKED_DOMAIN:
            continue
        return email
    return ""


def extract_phone(text: str) -> str:
    """Primeiro telefone plausível, ou vazio."""
    match = _PHONE_RE.search(text or "")
    return match.group(0).strip() if match else ""
