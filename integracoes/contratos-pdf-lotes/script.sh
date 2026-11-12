#!/usr/bin/env bash
# Processa ate LOTE documentos ja validados no servidor interno.
# Nao execute em ambiente real sem adaptar e homologar os contratos das APIs.
set -Eeuo pipefail
umask 077

: "${API_INTERNA_URL:?Informe a URL HTTPS do servidor interno}"
: "${API_DESTINO_URL:?Informe a URL HTTPS do sistema de destino}"
: "${TOKEN_INTERNO:?Token interno deve vir de um cofre/ambiente protegido}"
: "${TOKEN_DESTINO:?Token de destino deve vir de um cofre/ambiente protegido}"
: "${CUSTO_ZERO_VALIDADO:?Custo da operacao deve ser confirmado antes de executar}"
[[ "$CUSTO_ZERO_VALIDADO" == "SIM" ]] || { echo 'BLOQUEADO: custo incremental nao validado como zero' >&2; exit 2; }
for url in "$API_INTERNA_URL" "$API_DESTINO_URL"; do
  [[ "$url" == https://* ]] || { echo 'BLOQUEADO: endpoint remoto deve usar HTTPS' >&2; exit 2; }
done

LOTE="${LOTE:-250}"
MODO="${MODO:-ENVIAR}" # ENVIAR ou RECONCILIAR (somente consulta)
[[ "$LOTE" =~ ^[1-9][0-9]*$ ]] && (( LOTE <= 1000 )) || { echo 'LOTE deve estar entre 1 e 1000' >&2; exit 2; }
[[ "$MODO" == ENVIAR || "$MODO" == RECONCILIAR ]] || { echo 'MODO invalido' >&2; exit 2; }
MANIFESTO="${MANIFESTO:-./manifesto.tsv}"
ESTADO_DIR="${ESTADO_DIR:-./estado}"
[[ -f "$MANIFESTO" ]] || { echo 'Manifesto TSV inexistente' >&2; exit 2; }
for cmd in curl jq awk flock sha256sum; do
  command -v "$cmd" >/dev/null || { echo "Dependencia ausente: $cmd" >&2; exit 2; }
done
mkdir -p "$ESTADO_DIR"
exec 9>"$ESTADO_DIR/execucao.lock"
flock -n 9 || { echo 'Existe outra execucao em curso' >&2; exit 2; }
JORNAL="$ESTADO_DIR/estado.tsv"
touch "$JORNAL"
# Esquema fixo: contrato_id TAB documento_id TAB sha256. Uma linha por documento.
awk -F '\t' '
  NR == 1 { if ($1 != "contrato_id" || $2 != "documento_id" || $3 != "sha256") exit 2; next }
  NF != 3 || $1 !~ /^[A-Za-z0-9_-]+$/ || $2 !~ /^[A-Za-z0-9_-]+$/ ||
  length($3) != 64 || $3 ~ /[^a-fA-F0-9]/ { exit 2 }
  { k = $1 FS $2 FS tolower($3); if (visto[k]++) exit 2 }
  END { if (NR < 2) exit 2 }
' "$MANIFESTO" || { echo 'Manifesto invalido ou com linhas duplicadas' >&2; exit 2; }
SELECAO="$(mktemp "$ESTADO_DIR/selecao.XXXXXX")"
RESPOSTA="$(mktemp "$ESTADO_DIR/resposta.XXXXXX")"
trap 'rm -f "$SELECAO" "$RESPOSTA"' EXIT

# Le o ultimo estado de cada contrato; 110 mil linhas cabem em uma passagem.
awk -F '\t' -v limite="$LOTE" -v modo="$MODO" '
  FILENAME == ARGV[1] { estado[$1 FS $2 FS $3]=$4; next }
  FNR == 1 { next }
  {
    k = $1 FS $2 FS tolower($3)
    escolhido = (modo == "ENVIAR" && estado[k] != "CONFIRMADO" && estado[k] != "INCERTO" && estado[k] != "BLOQUEADO") ||
               (modo == "RECONCILIAR" && estado[k] == "INCERTO")
    if (escolhido) { print; if (++n >= limite) exit }
  }
' "$JORNAL" "$MANIFESTO" > "$SELECAO"

registrar() {
  local id="$1" status="$2" documento="$3" sha="$4"
  printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$documento" "$sha" "$status" "$(date -u +%FT%TZ)" >> "$JORNAL"
  printf 'contrato=%s estado=%s\n' "$id" "$status"
}

# Exemplos de endpoints; adaptar ao contrato das APIs antes da homologacao.
http_get() {
  local url="$1" token="$2"
  curl --proto '=https' --tlsv1.2 --silent --show-error \
    --connect-timeout 10 --max-time 30 --output "$RESPOSTA" --write-out '%{http_code}' \
    --header "Authorization: Bearer $token" --header 'Cache-Control: no-cache' "$url"
}
http_post() {
  local url="$1" token="$2" corpo="$3" chave="$4"
  curl --proto '=https' --tlsv1.2 --silent --show-error \
    --connect-timeout 10 --max-time 60 --output "$RESPOSTA" --write-out '%{http_code}' \
    --header "Authorization: Bearer $token" --header 'Content-Type: application/json' \
    --header "Idempotency-Key: $chave" --request POST --data "$corpo" "$url"
}

confirmar_destino() {
  local id="$1" doc="$2" sha="$3" codigo
  if ! codigo="$(http_get "${API_DESTINO_URL%/}/contratos/$id/documentos/$doc" "$TOKEN_DESTINO")"; then
    return 2 # nao foi possivel consultar; nao repetir POST cegamente
  fi
  if [[ "$codigo" == 404 ]]; then return 4; fi
  [[ "$codigo" != 401 && "$codigo" != 403 ]] || return 6
  [[ "$codigo" != 429 && "$codigo" != 503 ]] || return 7
  [[ "$codigo" == 200 ]] || return 2
  jq -e --arg id "$id" --arg doc "$doc" --arg sha "$sha" \
    '(.contrato_id|tostring)==$id and .documento_id==$doc and .sha256==$sha and .estado=="ASSOCIADO"' \
    "$RESPOSTA" >/dev/null || return 5
}

processar() {
  local id="$1" doc="$2" sha="$3" codigo corpo chave tentativa rc
  # Manifesto inteiramente validado antes do primeiro POST.
  sha="${sha,,}"
  if confirmar_destino "$id" "$doc" "$sha"; then
    registrar "$id" CONFIRMADO "$doc" "$sha"; return 0
  else rc=$?; fi
  if [[ "$MODO" == RECONCILIAR ]]; then
    # Em duvida, apenas consulta. NUNCA repete POST nesta modalidade.
    printf 'contrato=%s continua=INCERTO consulta=%s\n' "$id" "$rc"
    return 0
  fi
  if (( rc == 5 || rc == 6 )); then
    registrar "$id" BLOQUEADO "$doc" "$sha"; return 0
  fi
  if (( rc == 7 )); then
    registrar "$id" TRANSITORIO "$doc" "$sha"; return 3
  fi
  if (( rc != 4 )); then
    registrar "$id" TRANSITORIO "$doc" "$sha"; return 0
  fi

  if ! codigo="$(http_get "${API_INTERNA_URL%/}/documentos/$doc" "$TOKEN_INTERNO")"; then
    registrar "$id" TRANSITORIO "$doc" "$sha"; return 0
  fi
  if [[ "$codigo" != 200 ]]; then
    registrar "$id" TRANSITORIO "$doc" "$sha"
    [[ "$codigo" != 429 && "$codigo" != 503 ]] || return 3
    return 0
  fi
  if ! jq -e --arg id "$id" --arg doc "$doc" --arg sha "$sha" \
       '(.contrato_id|tostring)==$id and .documento_id==$doc and .sha256==$sha and .estado=="VALIDADO"' \
       "$RESPOSTA" >/dev/null; then
    registrar "$id" BLOQUEADO "$doc" "$sha"; return 0
  fi

  corpo="$(jq -nc --arg doc "$doc" --arg sha "$sha" '{documento_id:$doc,sha256:$sha}')"
  chave="$(printf 'associar-documento-v1|%s|%s|%s' "$id" "$doc" "$sha" | sha256sum | awk '{print $1}')"
  if ! codigo="$(http_post "${API_DESTINO_URL%/}/contratos/$id/documentos" "$TOKEN_DESTINO" "$corpo" "$chave")"; then
    registrar "$id" INCERTO "$doc" "$sha"; return 0
  fi
  if [[ "$codigo" =~ ^2[0-9][0-9]$ || "$codigo" == 409 ]]; then
    for tentativa in 1 2 3; do
      if confirmar_destino "$id" "$doc" "$sha"; then
        registrar "$id" CONFIRMADO "$doc" "$sha"; return 0
      fi
      if (( tentativa < 3 )); then sleep 2; fi
    done
    registrar "$id" INCERTO "$doc" "$sha"
  elif [[ "$codigo" == 400 || "$codigo" == 401 || "$codigo" == 403 || "$codigo" == 422 ]]; then
    registrar "$id" BLOQUEADO "$doc" "$sha"
  else
    registrar "$id" INCERTO "$doc" "$sha"
    [[ "$codigo" != 429 && "$codigo" != 503 ]] || return 3
  fi
}

if [[ ! -s "$SELECAO" ]]; then
  echo 'Nenhum contrato elegivel no lote atual.'
  exit 0
fi
while IFS=$'\t' read -r id doc sha resto; do
  if ! processar "$id" "$doc" "$sha"; then
    echo "Lote interrompido por indisponibilidade ou limite da API; nenhum reenvio incerto foi feito." >&2
    exit 3
  fi
done < "$SELECAO"
