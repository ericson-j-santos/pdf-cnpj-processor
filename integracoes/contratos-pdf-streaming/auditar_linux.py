#!/usr/bin/env python3
"""Auditoria segura de prontidao LOCAL em Linux, com sonda TLS opcional.

NUNCA libera operacao corporativa, processamento de PDFs ou POST.
Usa apenas biblioteca padrao. Sem instalacao, sem Docker, sem segredos.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shutil
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SERVICOS = {"origem", "upload", "publicacao"}
HOST_RE = re.compile(r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\Z")


class EntradaInvalida(ValueError):
    pass


def ler_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="ascii")


def _porcentagem(partes: tuple[int, int]) -> float:
    total, ocupado = partes
    if total <= 0 or ocupado < 0 or ocupado > total:
        raise EntradaInvalida("Medicao de capacidade invalida")
    return round(100 * ocupado / total, 2)


def cpu_percentual(*, caminho: Path = Path("/proc/stat"), dormir=time.sleep) -> float:
    """Delta de jiffies da CPU; nao confundir com load average."""
    def amostra() -> tuple[int, int]:
        linha = ler_texto(caminho).splitlines()[0].split()
        if not linha or linha[0] != "cpu" or len(linha) < 8:
            raise EntradaInvalida("Amostra CPU invalida")
        valores = [int(v) for v in linha[1:9]]
        if any(v < 0 for v in valores):
            raise EntradaInvalida("Contadores CPU invalidos")
        # idle + iowait, evitando inflar o uso ao aguardar I/O.
        inativo = valores[3] + valores[4]
        return sum(valores), inativo
    total1, idle1 = amostra()
    dormir(0.12)
    total2, idle2 = amostra()
    dt, di = total2 - total1, idle2 - idle1
    if dt <= 0 or di < 0 or di > dt:
        raise EntradaInvalida("Delta CPU invalido")
    return round(100 * (dt - di) / dt, 2)


def memoria(*, caminho: Path = Path("/proc/meminfo")) -> tuple[float, int]:
    dados: dict[str, int] = {}
    for linha in ler_texto(caminho).splitlines():
        partes = linha.split()
        if len(partes) >= 2 and partes[0] in ("MemTotal:", "MemAvailable:"):
            dados[partes[0]] = int(partes[1]) * 1024
    total, livre = dados["MemTotal:"], dados["MemAvailable:"]
    if not (0 <= livre <= total):
        raise EntradaInvalida("Memoria fora dos limites")
    return _porcentagem((total, total-livre)), livre


def limites_cgroup(*, raiz: Path = Path("/sys/fs/cgroup")) -> dict:
    """Registra SOMENTE os limites do cgroup do processo auditador.

    Nao atesta os limites de um futuro worker/servico systemd.
    """
    result = {"contexto": "raiz_cgroup_v2_nao_worker", "cpu": "NAO_COMPROVADO",
              "memoria": "NAO_COMPROVADO", "pids": "NAO_COMPROVADO"}
    try:
        if not (raiz / "cgroup.controllers").exists():
            return result
        # Nao construi caminhos com entrada externa nem percorre cgroups alheios.
        # A raiz reflete o cgroup global de controle, nao necessariamente o filho.
        for campo, nome in (("cpu", "cpu.max"), ("memoria", "memory.max"), ("pids", "pids.max")):
            valor = (raiz / nome).read_text(encoding="ascii").strip()
            if valor and not valor.startswith("max"):
                result[campo] = "LIMITE_NA_RAIZ_OBSERVADO"
            elif valor:
                result[campo] = "SEM_LIMITE_NA_RAIZ"
    except (OSError, ValueError, UnicodeDecodeError):
        # A ausencia de evidencia nao vira aprovacao.
        return result
    return result


def validar_alvos(caminho: Path) -> list[tuple[str, str, int]]:
    """Contrato estrito sem segredos: lista 1..3, nomes oficiais, hostname e porta 443."""
    try:
        bruto = caminho.read_text(encoding="utf-8")
        if len(bruto) > 8192:
            raise EntradaInvalida("Politica de rede excedeu tamanho permitido")
        def unico(pares):
            d = {}
            for k,v in pares:
                if k in d:
                    raise EntradaInvalida("Chaves de rede duplicadas")
                d[k] = v
            return d
        obj = json.loads(bruto, object_pairs_hook=unico)
    except (OSError, ValueError, UnicodeError) as exc:
        raise EntradaInvalida("Politica de rede ausente ou malformada") from exc
    if not isinstance(obj, dict) or set(obj) != {"servicos"} or not isinstance(obj["servicos"], list):
        raise EntradaInvalida("Estrutura de rede invalida")
    if not (1 <= len(obj["servicos"]) <= 3):
        raise EntradaInvalida("Sao permitidos de 1 a 3 servicos")
    r, vistos = [], set()
    for item in obj["servicos"]:
        if not isinstance(item, dict) or set(item) != {"nome", "hostname", "porta"}:
            raise EntradaInvalida("Servico de rede invalido")
        nome, host, porta = item["nome"], item["hostname"], item["porta"]
        if (not isinstance(nome, str) or nome not in SERVICOS or nome in vistos or not isinstance(host, str)
                or not HOST_RE.fullmatch(host) or all(v.isdigit() for v in host.split("."))
                or type(porta) is not int or porta != 443):
            raise EntradaInvalida("Alvo TLS nao permitido")
        vistos.add(nome)
        r.append((nome, host, porta))
    return r


def verificar_tls(nome: str, host: str, porta: int, *, timeout: float = 2.0) -> str:
    """Apenas conexao TLS verificando certificado; NAO faz GET, POST ou autenticacao."""
    try:
        contexto = ssl.create_default_context()
        with socket.create_connection((host, porta), timeout=timeout) as s:
            s.settimeout(timeout)
            with contexto.wrap_socket(s, server_hostname=host) as tls:
                if tls.version() is None:
                    return "BLOQUEADO_TLS"
        return "TLS_VALIDO_SEM_VALIDAR_API"
    except (OSError, ssl.SSLError, ValueError):
        return "INACESSIVEL_OU_CERTIFICADO_INVALIDO"


def avaliar(*, cpu: float, memoria_pct: float, disco_livre: int,
            disco_total: int, python_ok: bool, cpu_limite: float,
            memoria_limite: float, disco_minimo: int) -> tuple[str, list[str]]:
    campos = (cpu, memoria_pct, cpu_limite, memoria_limite)
    if (any(type(v) not in (float,int) or not math.isfinite(v) for v in campos)
            or not (0 <= cpu <= 100 and 0 <= memoria_pct <= 100)
            or not (0 < cpu_limite < 100 and 0 < memoria_limite < 100)
            or type(disco_livre) is not int or type(disco_total) is not int
            or not 0 <= disco_livre <= disco_total or type(disco_minimo) is not int
            or disco_minimo <= 0 or type(python_ok) is not bool):
        return "BLOQUEADO", ["MEDICOES_INVALIDAS"]
    motivos = []
    if not python_ok: motivos.append("PYTHON_INFERIOR_3_10")
    if cpu > cpu_limite: motivos.append("CPU_ALTA")
    if memoria_pct > memoria_limite: motivos.append("MEMORIA_ALTA")
    if disco_livre < disco_minimo: motivos.append("DISCO_INSUFICIENTE")
    return ("APTO_APENAS_PARA_TESTE_LOCAL" if not motivos else "BLOQUEADO"), motivos


def auditar(volume: Path, *, max_cpu: float, max_mem: float,
            minimo_gib: int, alvos: Path | None = None,
            autorizar_sonda: bool = False) -> dict:
    if (platform.system() != "Linux" or type(minimo_gib) is not int
            or not 1 <= minimo_gib <= 1024 or not volume.is_dir()):
        raise EntradaInvalida("Linux, volume existente e minimo-gib entre 1 e 1024 obrigatorios")
    if (type(max_cpu) not in (float, int) or not math.isfinite(max_cpu) or
            type(max_mem) not in (float, int) or not math.isfinite(max_mem) or
            not 0 < max_cpu < 100 or not 0 < max_mem < 100):
        raise EntradaInvalida("Limites CPU/memoria invalidos")
    if alvos is not None and not autorizar_sonda:
        raise EntradaInvalida("Sondagem TLS so com autorizacao explicita")
    if autorizar_sonda and alvos is None:
        raise EntradaInvalida("Informe politica allowlist antes de sondar rede")
    # Validar a allowlist antes de QUALQUER tentativa de rede.
    lista = validar_alvos(alvos) if alvos else []
    try:
        ocupacao_cpu = cpu_percentual()
        ocupacao_mem, memoria_livre = memoria()
        disco = shutil.disk_usage(volume)
    except (OSError, KeyError, IndexError, ValueError, ZeroDivisionError) as exc:
        raise EntradaInvalida("Nao foi possivel medir CPU, memoria ou disco") from exc
    estado, motivos = avaliar(cpu=ocupacao_cpu, memoria_pct=ocupacao_mem,
                             disco_livre=disco.free, disco_total=disco.total,
                             python_ok=sys.version_info >= (3,10),
                             cpu_limite=max_cpu, memoria_limite=max_mem,
                             disco_minimo=minimo_gib * 1024**3)
    # Se o host ja esta sobrecarregado, nao criar nem sondas TLS opcionais.
    rede = ({nome: verificar_tls(nome, host, porta) for nome, host, porta in lista}
            if estado == "APTO_APENAS_PARA_TESTE_LOCAL" else "NAO_EXECUTADO_HOST_SOBRECARGA")
    # A leitura TLS, inclusive de sucesso, nao prova permissao na API ou autorizacao de custo.
    return {
        "em_utc": datetime.now(timezone.utc).isoformat(),
        "fase": "DIAGNOSTICO_SOMENTE_LEITURA",
        "ambiente_comprovado": "HOST_EM_EXECUCAO_SEM_IDENTIDADE_CORPORATIVA",
        "aptidao_tecnica_local": estado,
        "bloqueios_locais": motivos,
        "python": ".".join(str(v) for v in sys.version_info[:3]),
        "cpu_percentual_amostra": ocupacao_cpu,
        "limite_cpu_percentual_proposto": max_cpu,
        "memoria_percentual": ocupacao_mem,
        "limite_memoria_percentual_proposto": max_mem,
        "memoria_disponivel_mib": memoria_livre // (1024**2),
        "disco_livre_gib": round(disco.free / 1024**3, 2),
        "disco_total_gib": round(disco.total / 1024**3, 2),
        "cgroup_raiz": limites_cgroup(),
        "systemd_detectado": Path("/run/systemd/system").is_dir(),
        "teste_rede_tls": rede if rede else "NAO_EXECUTADO_SEM_AUTORIZACAO",
        "permissao_api": "NAO_VERIFICADA",
        "sql_server_fila_compartilhada": "NAO_VERIFICADO",
        "custo_incremental_zero": "NAO_COMPROVADO",
        "autorizacao_corporativa": "NAO_COMPROVADA",
        "aprovacoes_hml": 0,
        "criterios_hml": 8,
        "aptidao_corporativa": "NAO_HOMOLOGADO",
        "download_corporativo_autorizado": False,
        "post_autorizado": False,
        "proxima_acao": "TI homologar host, cgroups do worker, APIs, fila, custo e seguranca",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Auditoria Linux sem transferir contratos")
    p.add_argument("--volume", type=Path, required=True)
    p.add_argument("--minimo-gib", type=int, default=5)
    p.add_argument("--max-cpu", type=float, default=60.0)
    p.add_argument("--max-memoria", type=float, default=75.0)
    p.add_argument("--alvos", type=Path)
    p.add_argument("--autorizar-sonda-tls", action="store_true")
    p.add_argument("--json", action="store_true", help="Somente JSON para integracoes de leitura")
    a = p.parse_args(argv)
    try:
        r = auditar(a.volume, max_cpu=a.max_cpu,max_mem=a.max_memoria,
                    minimo_gib=a.minimo_gib,alvos=a.alvos,
                    autorizar_sonda=a.autorizar_sonda_tls)
        if not a.json:
            print("RESULTADO LOCAL: " + r["aptidao_tecnica_local"])
            print("RESULTADO CORPORATIVO: NAO_HOMOLOGADO (0/8 aprovados)")
            print("AUTORIZADO PARA BAIXAR/PUBLICAR: NAO")
            print("BLOQUEIOS LOCAIS: " + (", ".join(r["bloqueios_locais"]) or "nenhum na amostra pontual"))
            print("REDE: " + ("NAO_TESTADA" if isinstance(r["teste_rede_tls"], str) else "TLS TESTADO SEM PROVAR ACESSO A API"))
            print("PROXIMA ACAO: " + r["proxima_acao"])
        print(json.dumps(r, ensure_ascii=False, sort_keys=True))
        return 0 if r["aptidao_tecnica_local"]=="APTO_APENAS_PARA_TESTE_LOCAL" and (
            not isinstance(r["teste_rede_tls"],dict) or
            all(v=="TLS_VALIDO_SEM_VALIDAR_API" for v in r["teste_rede_tls"].values())) else 2
    except EntradaInvalida as exc:
        print(json.dumps({"aptidao_tecnica_local":"BLOQUEADO", "aptidao_corporativa":"NAO_HOMOLOGADO",
                          "download_corporativo_autorizado":False, "post_autorizado":False,
                          "causa": str(exc)}, ensure_ascii=False))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
