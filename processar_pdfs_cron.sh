#!/usr/bin/env bash
set -Eeuo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin"
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENGINE="$BASE_DIR/rotina_pdfs_cnpj.sh"; PDF_ENV_FILE="${PDF_ENV_FILE:-/etc/pdfs-cnpj.env}"
[[ -r "$PDF_ENV_FILE" ]] && source "$PDF_ENV_FILE"
PDF_ROOT="${PDF_ROOT:?configure PDF_ROOT}"; PDF_OUT="${PDF_OUT:-$PDF_ROOT/resultado_pdfs_cnpj}"; PDF_WORK="${PDF_WORK:-$PDF_ROOT/.rotina_pdfs_cron}"; PDF_MAX_OUTPUT_MB="${PDF_MAX_OUTPUT_MB:-45}"; PDF_TIMEOUT="${PDF_TIMEOUT:-23h}"
TIPOLOGY_REGEX="${TIPOLOGY_REGEX:-}"; TEAMS_WEBHOOK_URL="${TEAMS_WEBHOOK_URL:-}"; EMAIL_TO="${EMAIL_TO:-}"; EMAIL_FROM="${EMAIL_FROM:-pdf-cnpj@localhost}"; SENDMAIL_BIN="${SENDMAIL_BIN:-}"
mkdir -p "$PDF_OUT" "$PDF_WORK/logs"; exec 9>"$PDF_WORK/cron.lock"; flock -n 9 || exit 0
exec > >(tee -a "$PDF_WORK/logs/$(date -u +%Y%m%d).log") 2>&1
RUN_ID="pdf-$(date -u +%Y%m%dT%H%M%SZ)-$"; START=$(date +%s); RUN_WORK="$PDF_WORK/run"; rm -rf "$RUN_WORK"; mkdir -p "$RUN_WORK"
set +e
args=(--root "$PDF_ROOT" --all --out "$PDF_OUT" --work "$RUN_WORK" --max-output-mb "$PDF_MAX_OUTPUT_MB")
[[ -n "$TIPOLOGY_REGEX" ]] && args+=(--typology-regex "$TIPOLOGY_REGEX")
timeout --signal=TERM --kill-after=2m "$PDF_TIMEOUT" bash "$ENGINE" "${args[@]}"
rc=$?
set -e
END=$(date +%s); DURATION=$((END-START)); STATUS=OK; ((rc==0)) || STATUS=FALHA
INV="$RUN_WORK/inventario.tsv"; MAN="$RUN_WORK/manifesto_partes.tsv"; FAIL="$RUN_WORK/falhas.tsv"
rows(){ [[ -s "$1" ]] && awk 'END{print (NR>0?NR-1:0)}' "$1" || echo 0; }
PDFS=$(rows "$INV"); OUTPUTS=$(rows "$MAN"); FAILURES=$(rows "$FAIL")
((FAILURES==0)) || [[ "$STATUS" == FALHA ]] || STATUS=PENDENCIAS
SUMMARY="$RUN_WORK/resumo.txt"
printf 'Processamento de PDFs por CNPJ\nEstado: %s\nExecução: %s\nData UTC: %s\nDuração: %ss\nPDFs classificados: %s\nArquivos finais gerados: %s\nFalhas/não classificados: %s\nExit code: %s\n' "$STATUS" "$RUN_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$DURATION" "$PDFS" "$OUTPUTS" "$FAILURES" "$rc" >"$SUMMARY"
if [[ -n "$TEAMS_WEBHOOK_URL" ]]; then
  PAYLOAD=$(python3 -c 'import json,sys; print(json.dumps({"text":sys.stdin.read()},ensure_ascii=False))' <"$SUMMARY")
  curl --silent --show-error --fail-with-body --retry 3 --retry-all-errors --max-time 30 -H 'Content-Type: application/json' --data-binary "$PAYLOAD" "$TEAMS_WEBHOOK_URL" >/dev/null || echo "AVISO: falha ao notificar Teams; processamento preservado" >&2
fi
if [[ -n "$EMAIL_TO" ]]; then
  if [[ -n "$SENDMAIL_BIN" && -x "$SENDMAIL_BIN" ]]; then
    { printf 'From: %s\nTo: %s\nSubject: PDF CNPJ - %s - %s\nContent-Type: text/plain; charset=UTF-8\n\n' "$EMAIL_FROM" "$EMAIL_TO" "$STATUS" "$RUN_ID"; cat "$SUMMARY"; } | "$SENDMAIL_BIN" -t || echo "AVISO: falha ao enviar e-mail; processamento preservado" >&2
  else echo "AVISO: EMAIL_TO definido, mas SENDMAIL_BIN não está configurado" >&2; fi
fi
exit "$rc"
