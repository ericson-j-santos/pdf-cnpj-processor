#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(mktemp -d); trap 'rm -rf "$ROOT"' EXIT
ENGINE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/rotina_pdfs_cnpj.sh"
mkpdf(){ mkdir -p "$(dirname "$1")"; gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -sOutputFile="$1" -c '/Helvetica findfont 12 scalefont setfont 72 720 moveto (test) show showpage'; }
# Estrutura real: competencia/CNPJ/nome-numerico.pdf. Para o E2E, o grupo capturado (0003/0006) simula a tipologia.
for p in 20260801/11111111000111/0001000100030021.pdf 20260910/11111111000111/0001000100030022.pdf 20260701/11111111000111/0001000100060008.pdf 20261001/11111111000111/0001000100060011.pdf 20260501/22222222000122/0001000100030031.pdf 20260815/22222222000122/0001000100030032.pdf; do mkpdf "$ROOT/in/$p"; done
REGEX='^[0-9]{8}([0-9]{4})[0-9]{4}$'
bash "$ENGINE" --root "$ROOT/in" --all --out "$ROOT/out" --work "$ROOT/work" --typology-regex "$REGEX"
test -f "$ROOT/out/11111111000111/0003/20260910/11111111000111_0003_20260910_parte_001.pdf"
test ! -e "$ROOT/out/11111111000111/0003/20260801"
test -f "$ROOT/out/11111111000111/0006/20261001/11111111000111_0006_20261001_parte_001.pdf"
test -f "$ROOT/out/22222222000122/0003/20260815/22222222000122_0003_20260815_parte_001.pdf"
grep -q $'11111111000111\t0003\t20260910' "$ROOT/work/manifesto_partes.tsv"
! grep -q $'11111111000111\t0003\t20260801' "$ROOT/work/manifesto_partes.tsv"

# Controle fail-closed: sem regra de tipologia, nenhum PDF pode ser processado.
rm -rf "$ROOT/out-blocked" "$ROOT/work-blocked"
if bash "$ENGINE" --root "$ROOT/in" --all --out "$ROOT/out-blocked" --work "$ROOT/work-blocked"; then
  echo "ERRO: execução sem classificador deveria falhar" >&2; exit 1
fi
test ! -s "$ROOT/work-blocked/manifesto_partes.tsv" || test "$(wc -l < "$ROOT/work-blocked/manifesto_partes.tsv")" -eq 1
grep -q 'tipologia não classificada' "$ROOT/work-blocked/falhas.tsv"

# Notificações: mocks locais provam envio sem depender de Teams/SMTP externos.
MOCK="$ROOT/mock"; mkdir -p "$MOCK"
cat >"$MOCK/curl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$MOCK_CURL_LOG"
exit "${MOCK_CURL_RC:-0}"
EOF
cat >"$MOCK/sendmail" <<'EOF'
#!/usr/bin/env bash
cat >>"$MOCK_MAIL_LOG"
exit "${MOCK_MAIL_RC:-0}"
EOF
chmod +x "$MOCK/curl" "$MOCK/sendmail"
export MOCK_CURL_LOG="$ROOT/curl.log" MOCK_MAIL_LOG="$ROOT/mail.log"
export PDF_ROOT="$ROOT/in" PDF_OUT="$ROOT/notify-out" PDF_WORK="$ROOT/notify-work"
export TIPOLOGY_REGEX="$REGEX" TEAMS_WEBHOOK_URL="https://example.invalid/teams"
export EMAIL_TO="ops@example.invalid" EMAIL_FROM="pdf@example.invalid" SENDMAIL_BIN="$MOCK/sendmail"
PATH="$MOCK:$PATH" bash "$(dirname "$ENGINE")/processar_pdfs_cron.sh"
test "$(grep -c -- '--data-binary' "$MOCK_CURL_LOG")" -eq 1
test "$(grep -c '^Subject: PDF CNPJ' "$MOCK_MAIL_LOG")" -eq 1
test -s "$PDF_WORK/run/resumo.txt"

# Falhas de notificação não podem transformar processamento válido em falha.
: >"$MOCK_CURL_LOG"; : >"$MOCK_MAIL_LOG"
MOCK_CURL_RC=22 MOCK_MAIL_RC=75 PATH="$MOCK:$PATH" bash "$(dirname "$ENGINE")/processar_pdfs_cron.sh"
test "$(grep -c -- '--data-binary' "$MOCK_CURL_LOG")" -eq 1
test "$(grep -c '^Subject: PDF CNPJ' "$MOCK_MAIL_LOG")" -eq 1

echo E2E_OK
