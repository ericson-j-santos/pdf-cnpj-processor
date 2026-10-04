#!/usr/bin/env bash
set -Eeuo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin"
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENGINE="$BASE_DIR/rotina_pdfs_cnpj.sh"; PDF_ENV_FILE="${PDF_ENV_FILE:-/etc/pdfs-cnpj.env}"
[[ -r "$PDF_ENV_FILE" ]] && source "$PDF_ENV_FILE"
PDF_ROOT="${PDF_ROOT:?configure PDF_ROOT}"; PDF_OUT="${PDF_OUT:-$PDF_ROOT/resultado_pdfs_cnpj}"; PDF_WORK="${PDF_WORK:-$PDF_ROOT/.rotina_pdfs_cron}"; PDF_MAX_OUTPUT_MB="${PDF_MAX_OUTPUT_MB:-45}"; PDF_TIMEOUT="${PDF_TIMEOUT:-23h}"
mkdir -p "$PDF_OUT" "$PDF_WORK/logs"; exec 9>"$PDF_WORK/cron.lock"; flock -n 9 || exit 0
exec > >(tee -a "$PDF_WORK/logs/$(date -u +%Y%m%d).log") 2>&1
timeout --signal=TERM --kill-after=2m "$PDF_TIMEOUT" "$ENGINE" --root "$PDF_ROOT" --all --out "$PDF_OUT" --work "$PDF_WORK/run" --max-output-mb "$PDF_MAX_OUTPUT_MB"
