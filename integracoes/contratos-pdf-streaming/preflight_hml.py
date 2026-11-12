#!/usr/bin/env python3
"""Coleta tecnica somente leitura para HML; nao executa transferencia ou publicacao.

Saida deliberadamente NAO_HOMOLOGADO: configuracao local nunca prova API,
permissoes corporativas, SQL Server, custo ou efeito de negocio.
"""
from __future__ import annotations

import argparse
import json
import shutil
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path


class PreflightBloqueado(ValueError):
    """Entrada insegura ou impossibilidade de colher a informacao local."""


def avaliar_medicoes(*, versao_python: tuple[int, int], tls_valido: bool,
                     livre_bytes: int, minimo_gib: int) -> dict:
    """Avaliacao pura, sem IO, independente do host real."""
    if (type(minimo_gib) is not int or not 1 <= minimo_gib <= 1024 or
            type(livre_bytes) is not int or livre_bytes < 0 or
            not isinstance(versao_python, tuple) or len(versao_python) != 2 or
            any(type(x) is not int for x in versao_python) or
            type(tls_valido) is not bool):
        raise PreflightBloqueado("Parametros de avaliacao invalidos")
    checks = {
        "python_3_10_ou_superior": versao_python >= (3, 10),
        "tls_validacao_certificado_ativa": tls_valido,
        "volume_minimo_livre_para_piloto": livre_bytes >= minimo_gib * (1024 ** 3),
    }
    return {
        "tipo": "OBSERVACAO_LOCAL_SOMENTE_LEITURA",
        "status": "NAO_HOMOLOGADO",
        "checks_locais": checks,
        "checks_locais_aceitos": sum(checks.values()),
        "checks_locais_previstos": len(checks),
        "limiar_disco_gib_piloto": minimo_gib,
        "limite_nao_e_dimensionamento_110mil": True,
        "aprovacoes_corporativas": 0,
        "aprovacoes_corporativas_previstas": 8,
        "transferencia_autorizada": False,
        "publicacao_autorizada": False,
        "pendencias": [
            "inventario_origem_e_manifesto_autenticado",
            "identidade_rede_tls_e_segredos_por_ti",
            "sql_server_compartilhado_e_backup",
            "pdf_parser_e_antivirus_homologados",
            "upload_idempotente_e_readback_independente",
            "regras_de_lote_e_post_oficial_homologados",
            "dois_hosts_e_replay_e2e",
            "homologacao_seguranca_lgpd_custo_e_autorizacao",
        ],
    }


def observar(volume: Path, minimo_gib: int) -> dict:
    if type(minimo_gib) is not int or not 1 <= minimo_gib <= 1024:
        raise PreflightBloqueado("Limiar minimo deve ser inteiro entre 1 e 1024 GiB")
    if not volume.is_dir():
        raise PreflightBloqueado("Volume informado nao e diretorio acessivel")
    try:
        uso = shutil.disk_usage(volume)
        contexto = ssl.create_default_context()
    except (OSError, ssl.SSLError) as exc:
        raise PreflightBloqueado("Nao foi possivel ler disco ou configuracao TLS") from exc
    resultado = avaliar_medicoes(
        versao_python=(sys.version_info.major, sys.version_info.minor),
        tls_valido=(contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname),
        livre_bytes=uso.free,
        minimo_gib=minimo_gib,
    )
    resultado["data_utc"] = datetime.now(timezone.utc).isoformat()
    return resultado


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preflight HML sem rede, sem upload ou POST")
    parser.add_argument("--volume", type=Path, required=True,
                        help="Diretorio local/volume autorizado apenas para consulta do espaco livre")
    parser.add_argument("--minimo-gib", type=int, default=5,
                        help="Limiar para PILOTO, nao dimensionamento do legado (1..1024)")
    args = parser.parse_args(argv)
    try:
        resultado = observar(args.volume, args.minimo_gib)
    except PreflightBloqueado as exc:
        print(json.dumps({"status": "BLOQUEADO", "causa": str(exc),
                          "transferencia_autorizada": False, "publicacao_autorizada": False},
                         ensure_ascii=False))
        return 2
    print(json.dumps(resultado, sort_keys=True, ensure_ascii=False))
    return 0 if all(resultado["checks_locais"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
