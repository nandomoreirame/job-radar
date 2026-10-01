"""Saúde por fonte: distingue "fonte caiu" de "não achou vaga".

Antes cada conector engolia erro de rede e devolvia []. O aviso de rodada
vazia não sabia se a fonte estava fora ou se simplesmente não havia match.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from job_radar.models import Job


def is_degraded_job(job: Job) -> bool:
    """Vaga com sinal de parse quebrado (empresa vazia, HTML no título, URL inválida)."""
    if not (job.company or "").strip():
        return True
    title = job.title or ""
    if "&amp;" in title or "<" in title:
        return True
    url = (job.url or "").strip().lower()
    if not (url.startswith("http://") or url.startswith("https://")):
        return True
    return False


@dataclass
class SourceHealth:
    """Contadores de uma fonte nesta varredura."""

    name: str
    requests: int = 0
    ok: int = 0
    errors: list[str] = field(default_factory=list)
    jobs: int = 0
    degraded: int = 0
    foreign: int = 0  # vagas fora do Brasil descartadas pelo country gate
    # respostas HTTP ok cujo corpo não trouxe o payload esperado (contrato mudou)
    parse_failures: int = 0

    def record_ok(self) -> None:
        self.requests += 1
        self.ok += 1

    def record_error(self, message: str) -> None:
        self.requests += 1
        short = (message or "erro").strip()[:120]
        if len(self.errors) < 5:
            self.errors.append(short)

    def record_parse_error(self, message: str) -> None:
        """Resposta chegou, mas sem o payload esperado.

        Não conta como requisição nova: ela já foi registrada em `record_ok`.
        Contar de novo dobrava o total e escondia a proporção real de falhas.
        """
        self.parse_failures += 1
        short = (message or "payload inválido").strip()[:120]
        if len(self.errors) < 5:
            self.errors.append(short)

    def record_job(self, job: Job) -> None:
        self.jobs += 1
        if is_degraded_job(job):
            self.degraded += 1

    def record_foreign(self) -> None:
        self.foreign += 1

    @property
    def status(self) -> str:
        if self.requests > 0 and self.ok == 0:
            return "sem_resposta"
        if self.jobs > 0 and self.degraded == self.jobs:
            return "degradada"
        # toda resposta veio sem payload: a fonte mudou de contrato, o que "vazia"
        # esconderia como se simplesmente não houvesse vaga
        if self.jobs == 0 and self.ok > 0 and self.parse_failures >= self.ok:
            return "degradada"
        if self.requests > 0 and self.jobs == 0:
            return "vazia"
        return "ok"

    def to_dict(self) -> dict:
        data = {
            "status": self.status,
            "requests": self.requests,
            "ok": self.ok,
            "jobs": self.jobs,
            "degraded": self.degraded,
            "errors": list(self.errors),
        }
        if self.foreign:
            data["foreign"] = self.foreign
        if self.parse_failures:
            data["parse_failures"] = self.parse_failures
        return data


def update_failure_streaks(previous: dict[str, int], health: dict[str, dict]) -> dict[str, int]:
    """Incrementa a sequência em `sem_resposta`; zera nos demais status."""
    nxt: dict[str, int] = dict(previous)
    for name, info in health.items():
        if (info or {}).get("status") == "sem_resposta":
            nxt[name] = int(nxt.get(name, 0)) + 1
        else:
            nxt[name] = 0
    return nxt


def format_health_warnings(
    health: dict[str, dict],
    streaks: dict[str, int] | None = None,
) -> list[str]:
    """Linhas de aviso para fontes que não estão ok/vazia."""
    streaks = streaks or {}
    lines: list[str] = []
    for name, info in sorted(health.items()):
        status = (info or {}).get("status", "ok")
        if status in ("ok", "vazia"):
            continue
        req = (info or {}).get("requests", 0)
        ok = (info or {}).get("ok", 0)
        label = {
            "sem_resposta": "sem resposta",
            "degradada": "degradada",
        }.get(status, status)
        line = f"⚠️ {name}: {label} ({ok}/{req} requisições)"
        streak = int(streaks.get(name, 0))
        if streak >= 2:
            line += f" · {streak} falhas seguidas"
        lines.append(line)
    return lines
