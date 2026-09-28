#!/usr/bin/env bash
# Varredura automática do radar de vagas.
# Sem "set -u": o snapshot de shell do ambiente referencia variáveis não definidas
# e derrubaria o script antes de ele começar.
set -eo pipefail

cd "$(dirname "$0")"
echo "=== $(date -Is) ==="

# A Sólides para de paginar sozinha ao sair da janela de 45 dias, então o teto
# de 50 páginas é só uma trava; na prática ela encerra por volta da 16a.
python3 scripts/collect.py \
  --profile profile/perfil.md \
  --sources gupy,github,programathor,solides \
  --solides-pages 50 \
  --out data/candidates.json \
  --db data/seen.db

# Corte alto no modo automático: ninguém revisa antes de publicar, então é
# preferível perder uma vaga mediana a encher o canal e o dono parar de ler.
python3 scripts/triage.py \
  --input data/candidates.json \
  --profile profile/perfil.md \
  --min-score 70 \
  --top 8 \
  --out-all data/to_send.json \
  --out-manual data/apply_manual.json \
  --out-email data/apply_email.json

# --notify-empty: silêncio no canal deve significar "a automação não rodou",
# nunca "rodou e não achou nada". O aviso leva o funil junto.
python3 scripts/notify.py \
  --input data/to_send.json \
  --db data/seen.db \
  --stats data/last_run.json \
  --notify-empty \
  --delay 45

echo "=== fim $(date -Is) ==="
