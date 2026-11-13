#!/usr/bin/env bash
# Consulta SOMENTE LEITURA a uma fila de testes SQLite local Linux.
set -Eeuo pipefail
umask 077
export LC_ALL=C
[[ "$(uname -s)" == Linux ]] || { echo 'BLOQUEADO: exige Linux' >&2; exit 78; }
[[ "${1:-}" == '--status' && "${2:-}" == '--banco' && -n "${3:-}" && $# -eq 3 ]] || {
  echo 'BLOQUEADO: uso: bash fila-linux.sh --status --banco CAMINHO-TESTE' >&2; exit 78; }
base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$base/fila_local.py" --banco "$3" --status
