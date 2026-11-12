#!/usr/bin/env python3
"""Piloto de transporte de PDF em streaming SOMENTE em HTTP loopback.

Nao conecta a servidores corporativos nem implementa POST de publicacao.
O estado INCERTO exige readback de destino antes de confirmar; nao retransmite.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

TAMANHO_BLOCO = 64 * 1024
LIMITE_MAXIMO = 256 * 1024 * 1024
# Reserva conservadora para ambiente de teste: nao dimensiona o legado corporativo.
RESERVA_DISCO_PILOTO = 1024 * 1024 * 1024
IDENTIFICADOR = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
HASH = re.compile(r"[a-fA-F0-9]{64}\Z")


class Bloqueado(RuntimeError):
    pass


def _url_local(url: str):
    partes = urlsplit(url)
    if (partes.scheme != "http" or partes.hostname != "127.0.0.1" or
            partes.username or partes.password or partes.query or partes.fragment or
            not partes.path.startswith("/") or "//" in partes.path or ".." in partes.path):
        raise Bloqueado("Piloto so admite HTTP local 127.0.0.1, sem redirecionamentos")
    try:
        porta = partes.port
    except ValueError as exc:
        raise Bloqueado("Porta invalida") from exc
    if not porta or not (1 <= porta <= 65535):
        raise Bloqueado("Porta local explicita obrigatoria")
    return partes.hostname, porta, partes.path


def _conexao(url: str):
    host, porta, caminho = _url_local(url)
    return http.client.HTTPConnection(host, port=porta, timeout=3), caminho


def evento(fase: str, estado: str, correlacao: str, quantidade: int = 0) -> str:
    """NDJSON contem progresso tecnico, nunca dados pessoais ou PDF."""
    if not all(isinstance(v, str) and IDENTIFICADOR.fullmatch(v) for v in (fase, estado, correlacao)):
        raise Bloqueado("Identificador de evento invalido")
    if type(quantidade) is not int or quantidade < 0:
        raise Bloqueado("Contador de bytes invalido")
    return json.dumps({"em": datetime.now(timezone.utc).isoformat(),
                       "fase": fase, "estado": estado,
                       "correlation_id": correlacao, "bytes": quantidade},
                      separators=(",", ":"), ensure_ascii=False) + "\n"


def ler_ndjson(fragmentos):
    """Processa linhas conforme chegam; limita a LINHA, nao o lote de rede.

    Um fragmento HTTP pode conter milhares de linhas NDJSON validas.
    O buffer retido entre eventos nunca ultrapassa 16 KiB.
    """
    pendente = bytearray()
    for fragmento in fragmentos:
        if not isinstance(fragmento, bytes):
            raise Bloqueado("Fragmento NDJSON deve ser bytes")
        inicio = 0
        while inicio < len(fragmento):
            fim = fragmento.find(b"\n", inicio)
            if fim < 0:
                if len(pendente) + (len(fragmento) - inicio) > 16 * 1024:
                    raise Bloqueado("Linha NDJSON muito longa")
                pendente.extend(memoryview(fragmento)[inicio:])
                break
            if len(pendente) + (fim - inicio) > 16 * 1024:
                raise Bloqueado("Linha NDJSON vazia ou muito longa")
            pendente.extend(memoryview(fragmento)[inicio:fim])
            if not pendente:
                raise Bloqueado("Linha NDJSON vazia ou muito longa")
            try:
                pares = json.loads(pendente.decode("utf-8"), object_pairs_hook=_pares_unicos)
            except (UnicodeDecodeError, ValueError, TypeError) as exc:
                raise Bloqueado("Evento NDJSON malformado") from exc
            if not isinstance(pares, dict):
                raise Bloqueado("Evento NDJSON deve ser objeto")
            yield pares
            pendente.clear()
            inicio = fim + 1
    if pendente:
        raise Bloqueado("Evento NDJSON incompleto no final do fluxo")


def _pares_unicos(pares):
    dados = {}
    for chave, valor in pares:
        if chave in dados:
            raise ValueError("Chave JSON repetida")
        dados[chave] = valor
    return dados


class Diario:
    """Diario local: demonstracao de restart, NAO substitui SQL Server compartilhado."""
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(caminho, timeout=4, isolation_level=None)
        self.conexao.execute("PRAGMA journal_mode=WAL")
        self.conexao.execute("PRAGMA synchronous=FULL")
        self.conexao.execute("""CREATE TABLE IF NOT EXISTS documentos (
            chave TEXT PRIMARY KEY, hash_esperado TEXT NOT NULL,
            estado TEXT NOT NULL, hash_observado TEXT, bytes INTEGER)""")

    def fechar(self):
        self.conexao.close()

    def ler(self, chave: str):
        return self.conexao.execute(
            "SELECT hash_esperado,estado,hash_observado,bytes FROM documentos WHERE chave=?", (chave,)
        ).fetchone()

    def iniciar(self, chave: str, sha: str):
        self.conexao.execute("BEGIN IMMEDIATE")
        try:
            anterior = self.ler(chave)
            if anterior is None:
                self.conexao.execute(
                    "INSERT INTO documentos (chave,hash_esperado,estado) VALUES (?,?,?)",
                    (chave, sha, "NOVO"))
            elif anterior[0] != sha:
                raise Bloqueado("Mesmo documento/versao com hash esperado conflitante")
            self.conexao.execute("COMMIT")
        except BaseException:
            self.conexao.execute("ROLLBACK")
            raise

    def reservar_exclusivamente(self, chave: str):
        """Reserva transacional: segundo executor nao consegue usar a mesma chave."""
        self.conexao.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.conexao.execute(
                "UPDATE documentos SET estado='EM_EXECUCAO' WHERE chave=? AND estado='NOVO'", (chave,))
            if cursor.rowcount != 1:
                raise Bloqueado("Documento reservado, interrompido ou bloqueado; nao assumir posse")
            self.conexao.execute("COMMIT")
        except BaseException:
            self.conexao.execute("ROLLBACK")
            raise

    def mudar(self, chave: str, estado: str, sha: str | None = None, tamanho: int | None = None):
        if estado not in {"NOVO", "EM_EXECUCAO", "INCERTO", "CONFIRMADO", "BLOQUEADO"}:
            raise Bloqueado("Estado nao permitido")
        self.conexao.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.conexao.execute(
                "UPDATE documentos SET estado=?, hash_observado=COALESCE(?,hash_observado),"
                " bytes=COALESCE(?,bytes) WHERE chave=?", (estado, sha, tamanho, chave))
            if cursor.rowcount != 1:
                raise Bloqueado("Checkpoint inexistente")
            self.conexao.execute("COMMIT")
        except BaseException:
            self.conexao.execute("ROLLBACK")
            raise


def chave_documento(contrato: str, documento: str, versao: str) -> str:
    if not all(isinstance(v, str) and IDENTIFICADOR.fullmatch(v)
               for v in (contrato, documento, versao)):
        raise Bloqueado("IDs devem ser alfanumericos seguros")
    return hashlib.sha256(f"{contrato}|{documento}|{versao}".encode()).hexdigest()


def _verificar_reserva_disco(diretorio: Path, proxima_gravacao: int) -> None:
    """Falha fechada se o volume nao preservar a reserva local do piloto.

    Apenas medicao instantanea: concorrentes e outros servicos podem consumir
    espaco depois da consulta. Producao exige quotas de SO e reserva central.
    """
    if type(proxima_gravacao) is not int or proxima_gravacao < 0:
        raise Bloqueado("Reserva de disco invalida")
    try:
        livre = shutil.disk_usage(diretorio).free
    except OSError as exc:
        raise Bloqueado("Nao foi possivel conferir espaco de disco") from exc
    if type(livre) is not int or livre < RESERVA_DISCO_PILOTO + proxima_gravacao:
        raise Bloqueado("Espaco de disco insuficiente para preservar reserva do piloto")


def baixar_pdf(url: str, destino: Path, sha_esperado: str, limite: int) -> int:
    if not isinstance(sha_esperado, str) or not HASH.fullmatch(sha_esperado):
        raise Bloqueado("SHA-256 esperado e obrigatorio e deve vir de fonte confiavel")
    if type(limite) is not int or not 0 < limite <= LIMITE_MAXIMO:
        raise Bloqueado("Limite de tamanho invalido")
    conexao, caminho = _conexao(url)
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _verificar_reserva_disco(destino.parent, limite)
    fd, tmp = tempfile.mkstemp(prefix=".pdf-parcial-", dir=destino.parent)
    quantidade = 0
    digest = hashlib.sha256()
    inicio = b""
    final = b""
    try:
        with os.fdopen(fd, "wb") as arquivo:
            conexao.request("GET", caminho, headers={"Accept-Encoding": "identity"})
            resposta = conexao.getresponse()
            if resposta.status != 200:
                raise Bloqueado("Download nao confirmado pela origem local")
            while True:
                bloco = resposta.read(TAMANHO_BLOCO)
                if not bloco:
                    break
                quantidade += len(bloco)
                if quantidade > limite:
                    raise Bloqueado("PDF ultrapassa limite permitido")
                _verificar_reserva_disco(destino.parent, len(bloco))
                if len(inicio) < 5:
                    inicio = (inicio + bloco)[:5]
                final = (final + bloco)[-2048:]
                digest.update(bloco)
                arquivo.write(bloco)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if quantidade == 0 or not inicio.startswith(b"%PDF-") or b"%%EOF" not in final:
            raise Bloqueado("PDF sem marcadores minimos (nao substitui parser PDF)")
        if digest.hexdigest() != sha_esperado.lower():
            raise Bloqueado("SHA-256 diferente do manifesto confiavel")
        os.replace(tmp, destino)
        return quantidade
    finally:
        conexao.close()
        if os.path.exists(tmp):
            os.unlink(tmp)


def consultar_destino(url: str, sha: str, tamanho: int) -> bool:
    conexao, caminho = _conexao(url)
    try:
        conexao.request("GET", caminho, headers={"Accept": "application/json"})
        resposta = conexao.getresponse()
        if resposta.status != 200:
            return False
        bruto = resposta.read(16 * 1024 + 1)
        if len(bruto) > 16 * 1024:
            return False
        dados = json.loads(bruto)
        return (isinstance(dados, dict) and dados.get("sha256") == sha and
                type(dados.get("bytes")) is int and dados["bytes"] == tamanho)
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        conexao.close()


def upload_local(url: str, caminho_pdf: Path, sha: str, quantidade: int, chave: str) -> None:
    """PUT binario apenas para stub localhost; nenhum POST de negocio."""
    conexao, caminho = _conexao(url)
    try:
        conexao.putrequest("PUT", caminho)
        conexao.putheader("Content-Type", "application/pdf")
        conexao.putheader("Content-Length", str(quantidade))
        conexao.putheader("Idempotency-Key", chave)
        conexao.putheader("X-Content-SHA256", sha)
        conexao.endheaders()
        digest = hashlib.sha256()
        enviado = 0
        with caminho_pdf.open("rb") as arquivo:
            while True:
                bloco = arquivo.read(TAMANHO_BLOCO)
                if not bloco:
                    break
                enviado += len(bloco)
                digest.update(bloco)
                conexao.send(bloco)
        if enviado != quantidade or digest.hexdigest() != sha:
            raise Bloqueado("Arquivo local mudou durante transferencia")
        resposta = conexao.getresponse()
        resposta.read(16 * 1024)
        if resposta.status not in (200, 201, 204):
            raise Bloqueado("Upload nao confirmado (estado remoto pode ser incerto)")
    finally:
        conexao.close()


def processar_local(diario: Diario, pasta: Path, url_origem: str, url_destino: str,
                     contrato: str, documento: str, versao: str, sha_esperado: str,
                     limite: int = 8 * 1024 * 1024):
    """Fluxo local de teste: baixar -> hash -> PUT -> GET readback. Nunca publica."""
    chave = chave_documento(contrato, documento, versao)
    _url_local(url_origem)
    _url_local(url_destino)
    if not isinstance(sha_esperado, str) or not HASH.fullmatch(sha_esperado):
        raise Bloqueado("Hash esperado invalido")
    sha_esperado = sha_esperado.lower()
    diario.iniciar(chave, sha_esperado)
    anterior = diario.ler(chave)
    if anterior[1] in ("INCERTO", "CONFIRMADO"):
        if consultar_destino(url_destino, sha_esperado, anterior[3] or -1):
            diario.mudar(chave, "CONFIRMADO")
            return "CONFIRMADO_SEM_REENVIO"
        raise Bloqueado("Estado incerto ou confirmacao desapareceu: proibido reenviar")
    if anterior[1] != "NOVO":
        raise Bloqueado("Estado anterior exige reconciliacao ou liberacao governada")
    diario.reservar_exclusivamente(chave)
    arquivo = pasta / (chave + ".pdf")
    try:
        tamanho = baixar_pdf(url_origem, arquivo, sha_esperado, limite)
    except Bloqueado:
        diario.mudar(chave, "BLOQUEADO")
        raise
    # Grave INCERTO ANTES de transmitir; queda depois disso proibe repeticao cega.
    diario.mudar(chave, "INCERTO", sha_esperado, tamanho)
    upload_local(url_destino, arquivo, sha_esperado, tamanho, chave)
    if not consultar_destino(url_destino, sha_esperado, tamanho):
        raise Bloqueado("Readback independente ausente; permanece INCERTO")
    diario.mudar(chave, "CONFIRMADO")
    return "CONFIRMADO"
