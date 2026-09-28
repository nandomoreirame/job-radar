#!/usr/bin/env bash
# Prepara o ambiente de testes do job-radar e roda a suíte.
#
# Sem "set -u": o snapshot de shell deste ambiente referencia variáveis não
# definidas e derrubaria o script antes de ele começar.
set -eo pipefail

cd "$(dirname "$0")/.."
VENV=".venv"

# O venv precisa pertencer ao usuário que roda a suíte. Criado como root, ele
# fica inescrevível depois e o próximo "pytest -p no:cacheprovider" quebra.
if [ "$(id -u)" -eq 0 ]; then
  echo "ERRO: não rode este script com sudo." >&2
  echo "Ele pede sudo sozinho, e só se precisar instalar pacote do sistema." >&2
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> criando virtualenv em $(pwd)/$VENV"
  if ! python3 -m venv "$VENV" 2>/dev/null; then
    # Só chega aqui se o Python do sistema vier sem o módulo venv. É o único
    # ponto que exige privilégio, então o sudo fica contido nele.
    echo "==> venv indisponível; instalando python3-venv (pede sudo)"
    sudo apt-get update -qq
    sudo apt-get install -y python3-venv
    python3 -m venv "$VENV"
  fi
fi

echo "==> instalando pytest"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet pytest

echo "==> $("$VENV/bin/python" -V), $("$VENV/bin/python" -m pytest --version 2>&1 | head -1)"
echo "==> rodando a suíte"
"$VENV/bin/python" -m pytest tests/ -q

echo
echo "Pronto. Para rodar a suíte de novo:"
echo "  cd ~/job-radar && .venv/bin/python -m pytest tests/ -q"
