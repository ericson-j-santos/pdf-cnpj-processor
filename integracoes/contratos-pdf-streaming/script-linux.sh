#!/usr/bin/env bash
# Entrada unica para preflight e testes LOCAIS do piloto de contratos.
# Nao habilita acesso corporativo, transferencias externas ou POST de negocio.
set -Eeuo pipefail
umask 077
export LC_ALL=C

base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

bloquear() {
  printf 'BLOQUEADO: %s\n' "$1" >&2
  exit 78
}

if [[ "$(uname -s)" != 'Linux' ]]; then
  bloquear 'este script exige servidor Linux'
fi

case "${1:-}" in
  --ajuda|-h|--help)
    printf '%s\n' 'Uso:' \
      '  bash script-linux.sh preflight --volume DIRETORIO --minimo-gib N' \
      '  bash script-linux.sh teste-local --confirmar-loopback' \
      '  bash script-linux.sh auditoria --volume DIRETORIO [--json]' \
      '  bash script-linux.sh planejar-hml --manifesto ARQUIVO --volume DIRETORIO --premissa-hml-declarada' \
      '  transferir, enviar e publicar: BLOQUEADOS ate homologacao corporativa'
    ;;
  auditoria)
    shift
    exec bash "$base/auditar-linux.sh" "$@"
    ;;
  planejar-hml)
    shift
    exec bash "$base/planejar-hml.sh" "$@"
    ;;
  preflight)
    shift
    exec bash "$base/preflight-linux.sh" "$@"
    ;;
  teste-local)
    shift
    if [[ "$#" -ne 1 || "$1" != '--confirmar-loopback' ]]; then
      bloquear 'teste-local exige --confirmar-loopback; nunca usar em producao'
    fi
    for bin in python3 timeout; do
      command -v "$bin" >/dev/null 2>&1 || bloquear "comando ausente: $bin"
    done
    python3 -B -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || bloquear 'Python 3.10+ obrigatorio'
    cd -- "$base"
    # Nao usa docker, sudo, apt, pip, chamadas externas nem interpretacao de manifestos.
    # A suite possui servidor ficticio em 127.0.0.1 e banco SQLite temporario.
    exec timeout --signal=TERM --kill-after=5s 120s python3 -B -m unittest -v \
      test_piloto_streaming test_preflight_hml test_controle_carga
    ;;
  '')
    bloquear 'informe preflight, teste-local ou --ajuda'
    ;;
  *)
    bloquear 'acao nao homologada; transferencia externa, POST e publicacao proibidos'
    ;;
esac
