#!/usr/bin/env python3
"""Orquestrador seguro por ID de lote, integrado por API (contrato ilustrativo)."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

ASSOCIACAO = 214
WORKFLOW = 181
ORIGEM = 501
FUNCAO = "fn_g1865"  # grafia transcrita da imagem; confirmar no sistema real
IDENTIFICADOR = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
ESTADOS = {"APTO", "CONFIRMADO", "TRANSITORIO", "INCERTO", "BLOQUEADO"}
MODOS = {"VALIDAR", "ENVIAR", "RECONCILIAR"}


class FalhaConfiguracao(Exception):
    pass


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def ambiente():
    modo = os.getenv("MODO", "VALIDAR").upper()
    if modo not in MODOS:
        raise FalhaConfiguracao("MODO deve ser VALIDAR, ENVIAR ou RECONCILIAR")
    bruto = os.getenv("LIMITE_LOTES", "250")
    if not re.fullmatch(r"[1-9][0-9]{0,3}", bruto) or int(bruto) > 1000:
        raise FalhaConfiguracao("LIMITE_LOTES deve estar entre 1 e 1000")
    url = os.getenv("API_NEGOCIO_URL", "").rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise FalhaConfiguracao("API_NEGOCIO_URL deve ser HTTPS, sem credenciais nem parametros")
    token = os.getenv("TOKEN_NEGOCIO", "")
    if not token or "\n" in token or "\r" in token:
        raise FalhaConfiguracao("TOKEN_NEGOCIO deve vir de um cofre ou ambiente protegido")
    if modo == "ENVIAR":
        for flag in ("AUTORIZACAO_POST", "CONTRATO_API_HOMOLOGADO", "CUSTO_ZERO_VALIDADO"):
            if os.getenv(flag) != "SIM":
                raise FalhaConfiguracao(f"POST bloqueado: {flag}=SIM nao comprovado")
    return modo, int(bruto), url, token


def ler_manifesto(caminho: Path):
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise FalhaConfiguracao("Manifesto nao pode ser lido") from exc
    if not linhas or linhas[0] != "lote_id" or len(linhas) < 2:
        raise FalhaConfiguracao("Manifesto precisa de cabecalho lote_id e ao menos um lote")
    vistos = set()
    for identificador in linhas[1:]:
        if not IDENTIFICADOR.fullmatch(identificador) or identificador in vistos:
            raise FalhaConfiguracao("Manifesto contem lote invalido ou repetido")
        vistos.add(identificador)
    return linhas[1:]


def ler_jornal(caminho: Path):
    estado = {}
    if not caminho.exists():
        return estado
    with caminho.open("r", encoding="utf-8") as arq:
        for linha in arq:
            try:
                item = json.loads(linha)
                identificador = item["lote_id"]
                situacao = item["estado"]
                if not isinstance(identificador, str) or not IDENTIFICADOR.fullmatch(identificador) or situacao not in ESTADOS:
                    raise ValueError("registro invalido")
            except (ValueError, KeyError, TypeError) as exc:
                raise FalhaConfiguracao("Jornal invalido: parada segura sem sobrescrever historico") from exc
            estado[identificador] = situacao
    return estado


def registrar(jornal: Path, identificador: str, situacao: str):
    item = {"lote_id": identificador, "estado": situacao,
            "ocorrido_em": datetime.now(timezone.utc).isoformat()}
    with jornal.open("a", encoding="utf-8") as arq:
        arq.write(json.dumps(item, separators=(",", ":"), ensure_ascii=False) + "\n")
        arq.flush()
        os.fsync(arq.fileno())
    print(f"lote={identificador} estado={situacao}", flush=True)


def chamar_api(metodo: str, url: str, token: str, corpo=None, chave=None):
    """Contrato hipotetico. Redirecionamentos bloqueados para proteger credenciais."""
    cabecalhos = {"Authorization": f"Bearer {token}", "Cache-Control": "no-store",
                  "Accept": "application/json"}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cabecalhos["Content-Type"] = "application/json"
    if chave:
        cabecalhos["Idempotency-Key"] = chave
    requisicao = Request(url, data=dados, headers=cabecalhos, method=metodo)
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), SemRedirecionamento())
    try:
        with opener.open(requisicao, timeout=30) as resposta:
            codigo, bruto = resposta.status, resposta.read(1024 * 1024)
    except HTTPError as exc:
        codigo, bruto = exc.code, exc.read(1024 * 1024)
    except (URLError, TimeoutError, OSError) as exc:
        raise ConnectionError("Acesso ao sistema indisponivel") from exc
    try:
        return codigo, json.loads(bruto) if bruto else {}
    except (ValueError, UnicodeDecodeError):
        return codigo, None


def inteiro_exato(valor, esperado):
    return type(valor) is int and valor == esperado


def comprovacao_aplicada(dados, lote):
    return (isinstance(dados, dict) and dados.get("lote_id") == lote
            and dados.get("estado") == "APLICADA"
            and inteiro_exato(dados.get("associacao_id"), ASSOCIACAO)
            and inteiro_exato(dados.get("workflow_id"), WORKFLOW)
            and inteiro_exato(dados.get("etapa_origem_id"), ORIGEM)
            and dados.get("funcao_nome") == FUNCAO
            and dados.get("funcao_executada") is True
            and type(dados.get("etapa_destino_id")) is int
            and dados["etapa_destino_id"] > 0
            and dados["etapa_destino_id"] != ORIGEM
            and isinstance(dados.get("registro_id"), str)
            and bool(dados["registro_id"].strip()))


def comprovacao_contexto(dados, lote):
    if not isinstance(dados, dict) or dados.get("lote_id") != lote:
        return False
    tabela = dados.get("conte_lote")
    return (isinstance(tabela, dict) and tabela.get("encontrado") is True
            and tabela.get("valido") is True
            and type(tabela.get("quantidade_contratos")) is int
            and tabela["quantidade_contratos"] > 0
            and inteiro_exato(dados.get("associacao_id"), ASSOCIACAO)
            and inteiro_exato(dados.get("workflow_id"), WORKFLOW)
            and inteiro_exato(dados.get("etapa_atual_id"), ORIGEM)
            and dados.get("funcao_nome") == FUNCAO
            and dados.get("funcao_habilitada") is True)


def consulta(metodo, base, lote, token, sufixo, corpo=None, chave=None):
    return chamar_api(metodo, f"{base}/lotes/{lote}/{sufixo}", token, corpo, chave)


def processar(lote, modo, base, token, jornal):
    # Consulta independente primeiro: nao repetir transicao ja concluida.
    try:
        codigo, dados = consulta("GET", base, lote, token, "transicao")
    except ConnectionError:
        registrar(jornal, lote, "TRANSITORIO" if modo != "RECONCILIAR" else "INCERTO")
        return "PARAR"
    if codigo in (429, 503):
        registrar(jornal, lote, "INCERTO" if modo == "RECONCILIAR" else "TRANSITORIO")
        return "PARAR"
    if codigo in (401, 403):
        registrar(jornal, lote, "BLOQUEADO")
        return "PARAR"
    if codigo != 200 or not isinstance(dados, dict) or dados.get("lote_id") != lote:
        registrar(jornal, lote, "BLOQUEADO")
        return "PARAR"  # erro de contrato; nao varrer 110 mil lotes
    if dados.get("estado") == "APLICADA":
        registrar(jornal, lote, "CONFIRMADO" if comprovacao_aplicada(dados, lote) else "BLOQUEADO")
        return "OK" if comprovacao_aplicada(dados, lote) else "PARAR"
    if dados.get("estado") != "NAO_APLICADA":
        registrar(jornal, lote, "BLOQUEADO")
        return "PARAR"
    if modo == "RECONCILIAR":
        registrar(jornal, lote, "INCERTO")
        return "OK"  # nunca reenviar a partir desta consulta

    try:
        codigo, contexto = consulta("GET", base, lote, token, "contexto")
    except ConnectionError:
        registrar(jornal, lote, "TRANSITORIO")
        return "PARAR"
    if codigo in (401, 403, 429, 503) or codigo != 200:
        registrar(jornal, lote, "TRANSITORIO" if codigo in (429, 503) else "BLOQUEADO")
        return "PARAR"
    if not comprovacao_contexto(contexto, lote):
        registrar(jornal, lote, "BLOQUEADO")
        return "OK"  # dados deste lote invalidos; os demais podem prosseguir
    if modo == "VALIDAR":
        registrar(jornal, lote, "APTO")
        return "OK"

    # O backend oficial devera executar fn_g1865 na transacao da mudanca
    # de etapa. NAO se tenta chamar SQL arbitrario diretamente pelo shell.
    corpo = {"lote_id": lote, "associacao_id": ASSOCIACAO, "workflow_id": WORKFLOW,
             "etapa_origem_id": ORIGEM, "funcao_nome": FUNCAO}
    chave = hashlib.sha256(f"transicao-lote-v1|{lote}|{ASSOCIACAO}|{WORKFLOW}|{ORIGEM}|{FUNCAO}".encode()).hexdigest()
    try:
        codigo, _ = consulta("POST", base, lote, token, "transicao", corpo, chave)
    except ConnectionError:
        registrar(jornal, lote, "INCERTO")
        return "OK"
    if codigo in (400, 401, 403, 422):
        registrar(jornal, lote, "BLOQUEADO")
        return "PARAR" if codigo in (401, 403) else "OK"
    if codigo not in (200, 201, 202, 204, 409):
        registrar(jornal, lote, "INCERTO")
        return "PARAR" if codigo in (429, 503) else "OK"
    # Mesmo HTTP 2xx/409 NAO confirma transicao. Exige leitura posterior.
    try:
        codigo, prova = consulta("GET", base, lote, token, "transicao")
    except ConnectionError:
        registrar(jornal, lote, "INCERTO")
        return "PARAR"
    if codigo == 200 and comprovacao_aplicada(prova, lote):
        registrar(jornal, lote, "CONFIRMADO")
        return "OK"
    registrar(jornal, lote, "INCERTO")
    return "PARAR" if codigo in (401, 403, 429, 503) else "OK"


def executar():
    modo, limite, url, token = ambiente()
    manifesto = Path(os.getenv("MANIFESTO_LOTES", "./lotes.tsv"))
    estado_dir = Path(os.getenv("ESTADO_DIR", "./estado-lotes"))
    lotes = ler_manifesto(manifesto)  # valida tudo ANTES de qualquer POST
    estado_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (estado_dir / "execucao.lock").open("a+") as trava:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FalhaConfiguracao("Outra execucao possui a trava deste executor") from exc
        jornal = estado_dir / "estado.jsonl"
        status = ler_jornal(jornal)
        if modo == "ENVIAR":
            elegiveis = [lote for lote in lotes if status.get(lote) not in ("CONFIRMADO", "INCERTO", "BLOQUEADO")]
        elif modo == "RECONCILIAR":
            elegiveis = [lote for lote in lotes if status.get(lote) == "INCERTO"]
        else:
            elegiveis = [lote for lote in lotes if status.get(lote) != "CONFIRMADO"]
        selecionados = elegiveis[:limite]
        print(f"modo={modo} lotes_selecionados={len(selecionados)}")
        for lote in selecionados:
            if processar(lote, modo, url, token, jornal) == "PARAR":
                print("BLOQUEADO: processamento interrompido; consultar o jornal", file=sys.stderr)
                return 3
    return 0


def main():
    try:
        return executar()
    except (FalhaConfiguracao, OSError) as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
