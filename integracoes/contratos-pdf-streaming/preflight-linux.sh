#!/usr/bin/env bash
# Somente leitura: capacidade basica Linux para o PILOTO, nao libera HML/PROD.
set -Eeuo pipefail
umask 077
export LC_ALL=C

bloquear() {
  printf 'BLOQUEADO: %s\n' "$1" >&2
  exit 78
}

[[ "$(uname -s)" == Linux ]] || bloquear 'host nao Linux'

volume=''
minimo='5'
while (($#)); do
  case "$1" in
    --volume)
      (($# >= 2)) || bloquear 'valor de --volume ausente'
      volume="$2"; shift 2 ;;
    --minimo-gib)
      (($# >= 2)) || bloquear 'valor de --minimo-gib ausente'
      minimo="$2"; shift 2 ;;
    *) bloquear 'argumento nao permitido' ;;
  esac
done

[[ -n "$volume" && -d "$volume" ]] || bloquear 'volume local nao informado ou inacessivel'
[[ "$minimo" =~ ^[1-9][0-9]{0,3}$ ]] || bloquear 'limite de disco deve ser numero inteiro de 1 a 1024'
((10#$minimo <= 1024)) || bloquear 'limite de disco acima de 1024 GiB'
[[ -r /proc/meminfo && -r /proc/loadavg ]] || bloquear 'telemetria basica do Linux indisponivel'
for bin in python3 awk getconf df; do
  command -v "$bin" >/dev/null 2>&1 || bloquear "comando obrigatorio ausente: $bin"
done

# Medidas pontuais: NAO equivalem a controle de recursos por cgroup ou systemd.
cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null)" || bloquear 'numero de CPUs indisponivel'
[[ "$cores" =~ ^[1-9][0-9]*$ ]] || bloquear 'contagem de CPUs invalida'
mem_avail="$(awk '$1 == "MemAvailable:" { print $2; n++ } END { if (n != 1) exit 1 }' /proc/meminfo)" || bloquear 'memoria disponivel nao medida'
[[ "$mem_avail" =~ ^[0-9]+$ ]] || bloquear 'memoria disponivel invalida'
read -r carga_1min _ < /proc/loadavg || bloquear 'carga do host indisponivel'
[[ "$carga_1min" =~ ^[0-9]+([.][0-9]+)?$ ]] || bloquear 'carga de 1 minuto invalida'

base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
[[ -f "$base/preflight_hml.py" ]] || bloquear 'preflight Python ausente'

# Nao mostra caminho interno, credenciais nem nomes de arquivos da empresa.
printf 'OBSERVACAO_LINUX: cpus=%s mem_disponivel_kib=%s carga_1min=%s (nao equivale a %%CPU)\n' \
  "$cores" "$mem_avail" "$carga_1min"
python3 -B "$base/preflight_hml.py" --volume "$volume" --minimo-gib "$minimo"
