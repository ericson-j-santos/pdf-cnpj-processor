#!/usr/bin/env bash
# Planejamento estritamente offline; nao baixa, envia ou publica contratos.
set -Eeuo pipefail
umask 077
export LC_ALL=C
if [[ "$(uname -s)" != Linux ]]; then
  printf 'BLOQUEADO: host nao Linux\n' >&2; exit 78
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'BLOQUEADO: Python 3 ausente\n' >&2; exit 78
fi
base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$base/planejar_hml.py" "$@"
