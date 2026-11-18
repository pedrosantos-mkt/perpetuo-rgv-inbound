#!/usr/bin/env bash
# Coleta tudo de novo (Meta e HubSpot) e gera index.html + site/index.html
set -euo pipefail
cd "$(dirname "$0")"
export TZ=America/Sao_Paulo
for s in meta base hs vendas crm build gerar; do
  echo "== $s"; python3 -u "$s.py"
done
