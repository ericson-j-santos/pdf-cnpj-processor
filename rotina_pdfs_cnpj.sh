#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="."; OUT="./resultado_pdfs_cnpj"; WORK="./.rotina_pdfs_cnpj"; MODE="inventory"; PILOT_CNPJ=""; MAX_OUTPUT_MB=45
while (($#)); do case "$1" in
  --root) ROOT=$2; shift 2;; --out) OUT=$2; shift 2;; --work) WORK=$2; shift 2;;
  --max-output-mb) MAX_OUTPUT_MB=$2; shift 2;; --inventory) MODE=inventory; shift;;
  --pilot) MODE=pilot; PILOT_CNPJ=$2; shift 2;; --all) MODE=all; shift;; *) echo "opção inválida: $1" >&2; exit 2;; esac; done
[[ -d "$ROOT" ]] || { echo "origem inexistente: $ROOT" >&2; exit 2; }
[[ -z "$PILOT_CNPJ" || "$PILOT_CNPJ" =~ ^[0-9]{14}$ ]] || { echo "CNPJ inválido" >&2; exit 2; }
for c in gs pdfinfo sha256sum find sort stat; do command -v "$c" >/dev/null || { echo "$c ausente" >&2; exit 2; }; done
MAX_OUTPUT_BYTES=$((MAX_OUTPUT_MB*1024*1024)); mkdir -p "$OUT" "$WORK"
INV="$WORK/inventario.tsv"; MAN="$WORK/manifesto_partes.tsv"; FAIL="$WORK/falhas.tsv"
printf "cnpj\ttipologia\tcompetencia\tarquivo\ttamanho_bytes\n" >"$INV"
printf "cnpj\ttipologia\tcompetencia\tparte\tarquivo\tpaginas\ttamanho_bytes\tsha256\tstatus\n" >"$MAN"
printf "cnpj\tarquivo\tmotivo\n" >"$FAIL"

group_info(){ local f=$1 p d c="" k="" t=""; p=$(dirname "$f"); while [[ "$p" != "/" && "$p" != "." ]]; do d=$(basename "$p"); [[ -z "$c" && "$d" =~ ^[0-9]{14}$ ]] && c=$d; if [[ -z "$k" && "$d" =~ ^[0-9]{6}([0-9]{2})?$ ]]; then k=$d; t=$(basename "$(dirname "$p")"); fi; p=$(dirname "$p"); done; [[ -n "$c" && -n "$t" && -n "$k" ]] || return 1; printf "%s\t%s\t%s\n" "$c" "$t" "$k"; }
valid_pdf(){ [[ -s "$1" ]] && pdfinfo "$1" >/dev/null 2>&1 && gs -q -dBATCH -dNOPAUSE -sDEVICE=nullpage "$1" >/dev/null 2>&1; }

while IFS= read -r -d "" f; do [[ "$f" == "$OUT"/* || "$f" == "$WORK"/* ]] && continue; i=$(group_info "$f" || true); if [[ -z "$i" ]]; then printf "SEM_GRUPO\t%s\testrutura inválida\n" "$f" >>"$FAIL"; continue; fi; IFS=$"\t" read -r c t k <<<"$i"; printf "%s\t%s\t%s\t%s\t%s\n" "$c" "$t" "$k" "$f" "$(stat -c %s "$f")" >>"$INV"; done < <(find "$ROOT" -type f -iname "*.pdf" -print0 | sort -z)
[[ "$MODE" == inventory ]] && exit 0

selected(){ awk -F "\t" -v only="$1" 'NR>1&&(only==""||$1==only){x=$1 SUBSEP $2;if(!(x in m)||$3>m[x])m[x]=$3} END{for(x in m){split(x,a,SUBSEP);print a[1]"\t"a[2]"\t"m[x]}}' "$INV" | sort; }
merge(){ local d=$1; shift; local x="$d.part"; rm -f "$x"; if command -v qpdf >/dev/null; then qpdf --empty --pages "$@" -- "$x" >/dev/null; else gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -sOutputFile="$x" "$@"; fi; valid_pdf "$x" || { rm -f "$x"; return 1; }; mv "$x" "$d"; }

process(){ local c=$1 t=$2 k=$3 safe dir f d size pages sha part=1 fit i cand; safe=$(printf %s "$t"|tr -c "[:alnum:]_.-" "_"); dir="$OUT/$c/$safe/$k"; mkdir -p "$dir"; local -a a=(); while IFS= read -r -d "" f; do valid_pdf "$f" && a+=("$f") || printf "%s\t%s\tPDF inválido\n" "$c" "$f" >>"$FAIL"; done < <(awk -F "\t" -v c="$c" -v t="$t" -v k="$k" 'NR>1&&$1==c&&$2==t&&$3==k{printf "%s%c",$4,0}' "$INV"); ((${#a[@]})) || return 1; while ((${#a[@]})); do fit=0; cand="$WORK/candidate_$$.pdf"; for ((i=1;i<=${#a[@]};i++)); do if merge "$cand" "${a[@]:0:i}" && (( $(stat -c %s "$cand") <= MAX_OUTPUT_BYTES )); then fit=$i; else break; fi; done; rm -f "$cand"; ((fit)) || { printf "%s\t%s\titem acima do limite\n" "$c" "${a[0]}" >>"$FAIL"; return 1; }; d=$(printf "%s/%s_%s_%s_parte_%03d.pdf" "$dir" "$c" "$safe" "$k" "$part"); merge "$d" "${a[@]:0:fit}"; size=$(stat -c %s "$d"); pages=$(pdfinfo "$d"|awk '/^Pages:/{print $2}'); sha=$(sha256sum "$d"|awk '{print $1}'); printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tok\n" "$c" "$t" "$k" "$part" "$d" "$pages" "$size" "$sha" >>"$MAN"; a=("${a[@]:fit}"); part=$((part+1)); done; }
only=""; [[ "$MODE" == pilot ]] && only=$PILOT_CNPJ; overall=0
while IFS=$"\t" read -r c t k; do process "$c" "$t" "$k" || overall=1; done < <(selected "$only")
exit "$overall"
