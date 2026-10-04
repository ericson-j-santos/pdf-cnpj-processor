#!/usr/bin/env bash
set -Eeuxo pipefail
ROOT=$(mktemp -d); trap 'rm -rf "$ROOT"' EXIT
ENGINE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/rotina_pdfs_cnpj.sh"
mkpdf(){ mkdir -p "$(dirname "$1")"; gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -sOutputFile="$1" -c '/Helvetica findfont 12 scalefont setfont 72 720 moveto (test) show showpage'; }
for p in 11111111000111/TIPO_A/202608/a.pdf 11111111000111/TIPO_A/202609/b.pdf 11111111000111/TIPO_B/202607/c.pdf 11111111000111/TIPO_B/202610/d.pdf 22222222000122/TIPO_A/202605/e.pdf 22222222000122/TIPO_A/202608/f.pdf; do mkpdf "$ROOT/in/$p"; done
bash -x "$ENGINE" --root "$ROOT/in" --all --out "$ROOT/out" --work "$ROOT/work"
test -f "$ROOT/out/11111111000111/TIPO_A/202609/11111111000111_TIPO_A_202609_parte_001.pdf"
test ! -e "$ROOT/out/11111111000111/TIPO_A/202608"
test -f "$ROOT/out/11111111000111/TIPO_B/202610/11111111000111_TIPO_B_202610_parte_001.pdf"
test -f "$ROOT/out/22222222000122/TIPO_A/202608/22222222000122_TIPO_A_202608_parte_001.pdf"
test ! -e "$ROOT/out/22222222000122/TIPO_A/202605"
grep -q $'11111111000111\tTIPO_A\t202609' "$ROOT/work/manifesto_partes.tsv"
grep -q $'22222222000122\tTIPO_A\t202608' "$ROOT/work/manifesto_partes.tsv"
! grep -q $'11111111000111\tTIPO_A\t202608' "$ROOT/work/manifesto_partes.tsv"
echo E2E_OK
