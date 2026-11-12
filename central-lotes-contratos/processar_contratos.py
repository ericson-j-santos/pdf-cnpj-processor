#!/usr/bin/env python3
"""Preflight local de contratos. NÃO executa download, upload ou publicação."""
import argparse
import json
from pathlib import Path

CAMPOS = {"limite", "paralelismo", "retry", "backoff", "teto", "modo", "publicacao", "dlq"}


def _sem_chaves_repetidas(pares):
    resultado = {}
    for nome, valor in pares:
        if nome in resultado:
            raise ValueError(f"Chave repetida na configuração: {nome}")
        resultado[nome] = valor
    return resultado


def _numero_inteiro(config, nome, minimo, maximo):
    valor = config.get(nome)
    if type(valor) is not int or not minimo <= valor <= maximo:
        raise ValueError(f"Parâmetro {nome} fora dos limites de segurança")
    return valor


def verificar(arquivo: Path) -> dict:
    """Valida de forma explícita mesmo com Python -O; nunca abre conexão."""
    config = json.loads(
        arquivo.read_text(encoding="utf-8"),
        object_pairs_hook=_sem_chaves_repetidas,
        parse_constant=lambda valor: (_ for _ in ()).throw(ValueError("Constante JSON inválida")),
    )
    if not isinstance(config, dict) or set(config) != CAMPOS:
        raise ValueError("Configuração incompleta ou com campos não autorizados")
    if config["modo"] != "DRY_RUN":
        raise ValueError("Modo inseguro bloqueado: somente DRY_RUN")
    if config["publicacao"] != "BLOQUEADA":
        raise ValueError("Publicação deve permanecer bloqueada")
    if config["dlq"] is not True:
        raise ValueError("Fila de quarentena (DLQ) precisa estar habilitada")
    _numero_inteiro(config, "limite", 1, 1000)
    _numero_inteiro(config, "paralelismo", 1, 4)
    _numero_inteiro(config, "retry", 0, 8)
    backoff = _numero_inteiro(config, "backoff", 1, 300)
    _numero_inteiro(config, "teto", backoff, 3600)
    return config


def main() -> None:
    p = argparse.ArgumentParser(description="Preflight somente leitura, sem transferência")
    p.add_argument("--config", required=True)
    p.add_argument("--preflight", action="store_true")
    args = p.parse_args()
    if not args.preflight:
        p.error("Somente preflight é permitido; transferência e publicação estão bloqueadas")
    try:
        config = verificar(Path(args.config))
    except (ValueError, json.JSONDecodeError, OSError) as erro:
        p.error(f"Preflight bloqueado: {erro}")
    print(json.dumps({"estado": "PREFLIGHT_LOCAL", "limite": config["limite"],
                      "sem_transferencia": True, "publicacao": "BLOQUEADA"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
