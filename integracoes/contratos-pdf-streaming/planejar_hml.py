#!/usr/bin/env python3
"""Plano offline de lotes HML: SEM download, upload, POST ou acesso SQL.

A declaracao de homologacao do solicitante habilita somente a preparacao
tecnica de um plano; nao serve como recibo de TI, seguranca ou negocio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import auditar_linux

IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
LIMITE_MANIFESTO = 128 * 1024
LIMITE_DOC_PILOTO = 8 * 1024 * 1024
LIMITE_TOTAL_PILOTO = 40 * 1024 * 1024


class PlanoBloqueado(ValueError):
    pass


def _pares_unicos(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise PlanoBloqueado("JSON com campo duplicado")
        d[k] = v
    return d


def _ident(valor):
    return type(valor) is str and IDENT.fullmatch(valor) is not None


def _exigir(condicao, mensagem):
    if not condicao:
        raise PlanoBloqueado(mensagem)


def analisar_manifesto(caminho: Path, *, max_documentos: int = 10) -> dict:
    """Valida dados declarados. SHA-256 informado NAO e manifesto autenticado."""
    _exigir(type(max_documentos) is int and 1 <= max_documentos <= 10,
            "Limite do piloto deve ser inteiro entre 1 e 10")
    try:
        with caminho.open("rb") as arquivo:
            bruto = arquivo.read(LIMITE_MANIFESTO + 1)
        _exigir(0 < len(bruto) <= LIMITE_MANIFESTO, "Manifesto ausente ou grande demais")
        obj = json.loads(bruto.decode("utf-8"), object_pairs_hook=_pares_unicos,
                         parse_constant=lambda _: (_ for _ in ()).throw(PlanoBloqueado("Numero JSON invalido")))
    except PlanoBloqueado:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise PlanoBloqueado("Manifesto nao pode ser validado") from exc
    _exigir(type(obj) is dict and set(obj) == {"schema_version", "lotes"}, "Esquema do manifesto invalido")
    _exigir(type(obj["schema_version"]) is int and obj["schema_version"] == 1,
            "Versao de manifesto nao homologada")
    lotes = obj["lotes"]
    _exigir(type(lotes) is list and 1 <= len(lotes) <= 3, "Piloto exige de 1 a 3 lotes")
    vistos_lote = set()
    vistos_documento = set()
    vistos_contrato = {}
    chaves = []
    total_bytes = 0
    contagem = 0
    for lote in lotes:
        _exigir(type(lote) is dict and set(lote) == {"lote_id", "documentos"}, "Lote invalido")
        lote_id = lote["lote_id"]
        _exigir(_ident(lote_id) and lote_id not in vistos_lote, "ID de lote ausente ou duplicado")
        vistos_lote.add(lote_id)
        docs = lote["documentos"]
        _exigir(type(docs) is list and 1 <= len(docs) <= max_documentos,
                "Quantidade de documentos do lote invalida")
        for doc in docs:
            _exigir(type(doc) is dict and set(doc) == {"contrato_id", "documento_id", "versao", "sha256", "bytes"},
                    "Documento tem campos ausentes ou excedentes")
            contrato, documento, versao, sha, tamanho = (doc[k] for k in
                ("contrato_id", "documento_id", "versao", "sha256", "bytes"))
            _exigir(all(_ident(k) for k in (contrato, documento, versao)), "Identificador invalido")
            _exigir(type(sha) is str and SHA256.fullmatch(sha) is not None,
                    "Hash declarado invalido")
            _exigir(type(tamanho) is int and 0 < tamanho <= LIMITE_DOC_PILOTO,
                    "Documento excede limite do piloto")
            chave_doc = (contrato, documento, versao)
            _exigir(chave_doc not in vistos_documento,
                    "Documento duplicado ou ambiguo entre lotes")
            _exigir(contrato not in vistos_contrato or vistos_contrato[contrato] == lote_id,
                    "Contrato associado a dois lotes no mesmo piloto")
            vistos_contrato[contrato] = lote_id
            vistos_documento.add(chave_doc)
            contagem += 1
            _exigir(contagem <= max_documentos, "Total de documentos ultrapassa piloto")
            total_bytes += tamanho
            _exigir(total_bytes <= LIMITE_TOTAL_PILOTO, "Tamanho total ultrapassa piloto")
            chaves.append(hashlib.sha256(("contratos-pdf-piloto-v1|" + "|".join(
                (lote_id, contrato, documento, versao))).encode("ascii")).hexdigest())
    return {
        "lotes": len(lotes), "documentos": contagem,
        "bytes_declarados": total_bytes,
        "sha256_manifesto_declarado": hashlib.sha256(bruto).hexdigest(),
        "chaves_idempotencia": sorted(chaves),
        "hashes_documentos": "DECLARADOS_NAO_CONFERIDOS",
    }


def planejar(*, manifesto: Path, volume: Path, max_documentos: int,
             premissa_hml: bool = False, auditor=None) -> dict:
    """A auditoria e executada SEM alvos/sondas; nunca cria operacao de negocio."""
    dados = analisar_manifesto(manifesto, max_documentos=max_documentos)
    obter_auditoria = auditor if auditor is not None else auditar_linux.auditar
    try:
        observacao = obter_auditoria(volume, max_cpu=60., max_mem=75., minimo_gib=5)
    except (OSError, ValueError, RuntimeError) as exc:
        raise PlanoBloqueado("Nao foi possivel comprovar capacidade local") from exc
    if (not isinstance(observacao, dict) or
            observacao.get("aptidao_tecnica_local") != "APTO_APENAS_PARA_TESTE_LOCAL" or
            observacao.get("aptidao_corporativa") != "NAO_HOMOLOGADO" or
            observacao.get("post_autorizado") is not False or
            observacao.get("download_corporativo_autorizado") is not False):
        raise PlanoBloqueado("Auditoria local inconsistente ou bloqueada")
    return {
        "estado": "PLANEJADO_APENAS_SEM_EXECUCAO",
        "fase": "PLANEJAMENTO_HML_ISOLADO",
        "premissa_hml_declarada": premissa_hml is True,
        "homologacao_corporativa_comprovada": False,
        "aprovacoes_hml_comprovadas": 0,
        "criterios_hml": 8,
        "transferencia_autorizada": False,
        "publicacao_autorizada": False,
        "rede_consultada": False,
        "banco_sql_consultado": False,
        "regras_lote_homologadas": False,
        "plano": dados,
        "proxima_acao": "TI e negocio fornecerem recibos verificaveis de API, host e regras por lote_id",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Planejar um lote HML ficticio sem rede e sem publicar contratos")
    p.add_argument("--manifesto", type=Path, required=True)
    p.add_argument("--volume", type=Path, required=True)
    p.add_argument("--max-documentos", type=int, default=10)
    p.add_argument("--premissa-hml-declarada", action="store_true")
    args = p.parse_args(argv)
    try:
        resultado = planejar(manifesto=args.manifesto, volume=args.volume,
                            max_documentos=args.max_documentos,
                            premissa_hml=args.premissa_hml_declarada)
    except (PlanoBloqueado, auditar_linux.EntradaInvalida):
        print(json.dumps({"estado": "BLOQUEADO", "homologacao_corporativa_comprovada": False,
                          "transferencia_autorizada": False, "publicacao_autorizada": False,
                          "proxima_acao": "Rever manifesto e auditoria local com a TI"}))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
