# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A job-posting crawler: collects listings from Brazilian sources, drops what fails the owner's hard
cuts, scores the rest 0-100 against the owner's CV, and posts the best ones to a Discord webhook.
It runs unattended (cron/systemd timer on the homelab via `run.sh`) and is also driven
interactively by the `job-radar` Claude skill (`~/.claude/skills/job-radar/SKILL.md`), which adds
a Gmail step (LinkedIn/InfoJobs/Vagas.com alerts) that the scheduled run cannot do and feeds those
jobs in through `scripts/ingest.py`.

**Runtime is stdlib only (Python 3.12+).** Do not add runtime dependencies; `pytest`, `ruff` and
`mypy` are dev-only (`[project.optional-dependencies] dev`).

Comments, docstrings, CLI output, test names and README are in **pt-BR**; keep that convention in
this repo. Comments explain *why* a rule exists (usually a real failure); preserve that style.

## Commands

```bash
# tests (pythonpath=src is set in pyproject, so no install needed)
python3 -m pytest tests/ -q
python3 -m pytest tests/test_filters.py -q
python3 -m pytest tests/test_filters.py::test_name -q
./scripts/setup-test-env.sh            # alternative: creates .venv with pytest and runs the suite

# lint / types (configured in pyproject: line-length 100, mypy strict)
ruff check src scripts tests
mypy src

# full pipeline (what the timer runs)
./run.sh

# stages individually
python3 scripts/collect.py --sources gupy,github,programathor,solides,ats
python3 scripts/triage.py --min-score 70 --top 8 --out-all data/to_send.json
python3 scripts/notify.py --input data/to_send.json --notify-empty --dry-run   # --dry-run: no POST

# maintenance
python3 scripts/history.py                 # read data/seen.db
python3 scripts/ingest.py < jobs.json      # inject externally collected jobs (title, company, url, ...)
python3 scripts/migrate_fingerprints.py --dry-run
python3 scripts/delete_messages.py         # delete messages this webhook posted, by recorded ID
```

`notify.py` and `delete_messages.py` hit the real Discord webhook from `.env`. Use `--dry-run`
unless a real post is intended.

## Architecture

Pipeline of three scripts that communicate through JSON files in `data/` (gitignored, along with
`profile/` and `.env`):

```
collect.py ──candidates.json──▶ triage.py ──to_send.json / apply_{email,manual}.json──▶ notify.py
     │                                                                                   │
     └──────────────── data/seen.db (dedup) ◀─────────── mark_sent after each POST ─────┘
     └── data/last_run.json (run funnel stats, reset by collect, merged by triage/notify)
```

Scripts are thin CLIs: each prepends `src/` to `sys.path` and imports from `job_radar`. All logic
lives in `src/job_radar/`:

- `models.Job`: canonical job across sources. `fingerprint` (sha256 of company + normalized title,
  title-only when company is empty) is the dedup identity. **Changing the fingerprint rule requires
  running `scripts/migrate_fingerprints.py`**, or already-sent jobs come back as new.
- `sources/`: one connector per source, each returning `list[Job]`. Network fetch and parsing are
  split (`parse_*` / `listing_from_page` are pure and tested against recorded fixtures; `fetch_*`
  does I/O). Solides is special: the listing has no description, so `collect.py` passes a `keep`
  predicate (hard filters with `min_skill_hits=0`) and only fetches detail pages for survivors.
  ATS connectors (`greenhouse`, `lever`, `ashby`) hit public JSON board APIs (one slug per company,
  no term search); country gate keeps Brazil/LATAM-relevant jobs only.
- `http.py` / `robots.py`: shared GET with User-Agent, robots.txt gate (RFC 9309), retry on
  429/5xx/network, and per-host pacing (min 1s or Crawl-delay).
- `health.py`: per-source `SourceHealth` (ok / vazia / sem_resposta / degradada). `collect.py`
  writes `fontes` into `last_run.json` and a failure streak into `data/source_health.json`.
- `boards.py`: default ATS slugs + `ATS_BOARDS` env override (replaces defaults when set).
- `geo.py`: Brazil country gate + `Cidade, UF` location normalization for international boards.
- `filters.py`: binary hard cuts in `passes_hard_filters`, cheap first, skill matching last. Returns
  `(passed, reason)`; the reason prefix (before `(`) is aggregated as funnel stats.
- `scoring.py`: deterministic 0-100 score used only for ordering (skills up to 45, title family,
  seniority, remote/hybrid, foreign-stack penalty). Filters decide eligibility; score never does.
- `profile.py`: skills come from the owner's CV markdown, from the `## Stack técnica` table, plus
  synonym expansion. There is no separate skills list by design.
- `settings.py`: per-owner config read from env on every call (`MIN_SALARY_PJ/CLT`,
  `COMMUTE_CITIES`). Defaults are deliberately neutral: unset means "do not filter".
- `targets.py`: search terms per role target (`ai`, `fullstack`, `techlead`, `dados`) for sources
  with term search (Gupy).
- `store.py`: SQLite `seen` table; `is_new` uses a 45-day resend window.
- `report.py` / `runstats.py`: Discord embeds (chunked to Discord limits) and the funnel stats.
  `--notify-empty` posts the funnel when nothing passed, so silence means "did not run". Empty-run
  embeds also list unhealthy sources from `fontes`.

## Conventions that bite

- Profile path mismatch: `run.sh` uses `profile/perfil.md`; the scripts' default and
  `.env.example` use `profile/profile.md` (`PROFILE_PATH` overrides). `profile/` is not in the repo.
- `pyproject.toml` declares `job-radar = "job_radar.cli:main"`, but `src/job_radar/cli.py` does
  not exist. Entry points are the scripts in `scripts/`.
- Connector tests must use **real recorded responses** in `tests/fixtures/`, never a fixture
  written from the imagined API shape. `tests/fixtures/perfil.md` is regenerated by
  `tests/test_ingest.py` at import time.
- Shell scripts use `set -eo pipefail` without `-u` on purpose (the environment's shell snapshot
  references unset variables).
- New sources must respect `robots.txt`, send an identifying User-Agent and sleep between requests.
  Discord's Cloudflare rejects the default `Python-urllib` UA with 403.
- `docs/specs/` (RPI state) is gitignored internal process.
