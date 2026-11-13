#!/usr/bin/env bash
# Executar diagnostico somente leitura; nunca processa ou publica PDFs.
set -Eeuo pipefail
umask 077
export LC_ALL=C
[[ "$(uname -s)" == Linux ]] || { echo 'BLOQUEADO: host nao Linux' >&2; exit 78; }
command -v python3 >/dev/null 2>&1 || { echo 'BLOQUEADO: Python ausente' >&2; exit 78; }
base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$base/auditar_linux.py" "$@"
