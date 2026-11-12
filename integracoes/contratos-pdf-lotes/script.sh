#!/usr/bin/env bash
# Entrada de lotes pelo processo de negocio 214/181/501/fn_g1865.
# Somente leitura por padrao. O adaptador da API precisa ser homologado.
set -Eeuo pipefail
umask 077
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$BASE/fluxo_lotes.py" "$@"
