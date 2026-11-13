#!/usr/bin/env python3
"""Fila local demonstrativa e transacional, SEM acesso corporativo.

SQLite somente neste Linux em arquivos de teste; NAO e backend multi-host.
Regras: uma reserva por vez; posse por token + geracao + lease;
INCERTO exige prova via GET do stub loopback; nao existe reenvio automatico.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
HASH = re.compile(r"[a-fA-F0-9]{64}\Z")
MAX_BYTES = 8 * 1024 * 1024


class FilaBloqueada(RuntimeError):
    pass


def _ident(valor: str) -> bool:
    return isinstance(valor, str) and bool(IDENT.fullmatch(valor))


def _agora() -> int:
    # Monotonicidade de tempo de banco em HML sera fornecida por SYSUTCDATETIME().
    return int(datetime.now(timezone.utc).timestamp())


class FilaLocal:
    """SQLite para testes de exclusao mutua NUM UNICO host, nao producao."""

    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(caminho), timeout=3, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=3000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS fila (
            chave TEXT PRIMARY KEY, lote_id TEXT NOT NULL,
            contrato_id TEXT NOT NULL, documento_id TEXT NOT NULL,
            versao TEXT NOT NULL, sha256 TEXT NOT NULL,
            bytes_esperados INTEGER NOT NULL CHECK (bytes_esperados > 0),
            estado TEXT NOT NULL CHECK (estado IN (
              'PENDENTE','RESERVADO','INCERTO_UPLOAD','CONFIRMADO_UPLOAD','BLOQUEADO')),
            geracao INTEGER NOT NULL DEFAULT 0,
            token TEXT, lease_ate INTEGER, recibo TEXT,
            UNIQUE(contrato_id,documento_id,versao))""")

    def fechar(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    def _inicio(self):
        self.db.execute("BEGIN IMMEDIATE")

    def enfileirar(self, *, lote_id: str, contrato_id: str, documento_id: str,
                   versao: str, sha256: str, bytes_esperados: int) -> str:
        if not all(_ident(v) for v in (lote_id, contrato_id, documento_id, versao)):
            raise FilaBloqueada("Identificador invalido")
        if not isinstance(sha256, str) or not HASH.fullmatch(sha256):
            raise FilaBloqueada("Hash nao confiavel")
        if type(bytes_esperados) is not int or not 0 < bytes_esperados <= MAX_BYTES:
            raise FilaBloqueada("Tamanho fora do piloto")
        sha256 = sha256.lower()
        chave = hashlib.sha256(("contratos-pdf-piloto-v1|" + "|".join(
            (lote_id, contrato_id, documento_id, versao))).encode("ascii")).hexdigest()
        self._inicio()
        try:
            anterior = self.db.execute("SELECT lote_id,sha256,bytes_esperados FROM fila WHERE chave=?", (chave,)).fetchone()
            # A mesma identidade nao pode ser movida de lote em outra chave.
            outra = self.db.execute("SELECT chave FROM fila WHERE contrato_id=? AND documento_id=? AND versao=?",
                                    (contrato_id, documento_id, versao)).fetchone()
            if outra and outra[0] != chave:
                raise FilaBloqueada("Documento ja pertence a outro lote")
            if anterior:
                if anterior != (lote_id, sha256, bytes_esperados):
                    raise FilaBloqueada("Manifesto mudou para chave ja registrada")
            else:
                self.db.execute("""INSERT INTO fila(chave,lote_id,contrato_id,documento_id,
                    versao,sha256,bytes_esperados,estado) VALUES(?,?,?,?,?,?,?,'PENDENTE')""",
                    (chave,lote_id,contrato_id,documento_id,versao,sha256,bytes_esperados))
            self.db.execute("COMMIT")
            return chave
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def obter(self, chave: str) -> dict | None:
        self.db.row_factory = sqlite3.Row
        try:
            linha = self.db.execute("SELECT * FROM fila WHERE chave=?", (chave,)).fetchone()
            return dict(linha) if linha else None
        finally:
            self.db.row_factory = None

    def reservar(self, *, executor: str, segundos: int = 60, agora: int | None = None) -> dict:
        if not _ident(executor) or type(segundos) is not int or not 30 <= segundos <= 300:
            raise FilaBloqueada("Executor ou duracao de lease invalido")
        now = _agora() if agora is None else agora
        if type(now) is not int or now < 1:
            raise FilaBloqueada("Horario invalido")
        self._inicio()
        try:
            if self.db.execute("SELECT 1 FROM fila WHERE estado IN ('RESERVADO','INCERTO_UPLOAD') LIMIT 1").fetchone():
                raise FilaBloqueada("Outra reserva ativa ou upload incerto; reconciliar primeiro")
            row = self.db.execute("SELECT chave FROM fila WHERE estado='PENDENTE' ORDER BY chave LIMIT 1").fetchone()
            if not row:
                raise FilaBloqueada("Fila vazia ou sem itens liberados")
            chave = row[0]
            token = secrets.token_hex(16)
            self.db.execute("""UPDATE fila SET estado='RESERVADO', geracao=geracao+1, token=?,
                lease_ate=? WHERE chave=? AND estado='PENDENTE'""",(token,now+segundos,chave))
            linha = self.db.execute("SELECT geracao FROM fila WHERE chave=?",(chave,)).fetchone()
            self.db.execute("COMMIT")
            return {"chave": chave, "token": token, "geracao": linha[0],
                    "lease_ate": now + segundos, "executor": executor,
                    "operacao_autorizada": False}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def marcar_incerto(self, *, chave: str, token: str, geracao: int, agora: int | None = None) -> None:
        self._transicao(chave,token,geracao,'RESERVADO','INCERTO_UPLOAD',agora=agora)

    def _transicao(self, chave, token, geracao, origem, destino, *, agora=None, recibo=None):
        now = _agora() if agora is None else agora
        if not _ident(chave) or not _ident(token) or type(geracao) is not int or geracao < 1 or type(now) is not int:
            raise FilaBloqueada("Posse ou horario invalido")
        self._inicio()
        try:
            cursor = self.db.execute("""UPDATE fila SET estado=?, recibo=? WHERE chave=? AND token=?
                AND geracao=? AND estado=? AND lease_ate>?""",
                (destino, recibo, chave, token, geracao, origem, now))
            if cursor.rowcount != 1:
                raise FilaBloqueada("Lease expirado, posse perdida ou estado incompativel")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def confirmar_loopback(self, *, chave: str, token: str, geracao: int, url_consulta: str,
                           agora: int | None = None) -> None:
        """Readback REAL por HTTP somente 127.0.0.1 do destino ficticio.

        Nao permite que o chamador confirme apenas alegando hash ou HTTP 2xx.
        """
        from piloto_streaming import consultar_destino
        anterior = self.obter(chave)
        if not anterior or anterior["estado"] != "INCERTO_UPLOAD":
            raise FilaBloqueada("Nao existe upload incerto")
        try:
            provado = consultar_destino(url_consulta, anterior["sha256"], anterior["bytes_esperados"])
        except Exception as exc:
            raise FilaBloqueada("Readback externo falhou") from exc
        if not provado:
            raise FilaBloqueada("Readback ausente: nao confirmar, nem reenviar")
        self._transicao(chave,token,geracao,'INCERTO_UPLOAD','CONFIRMADO_UPLOAD',agora=agora,
                        recibo='GET_LOOPBACK_SHA256_BYTES_CONFERIDOS')

    def resumo(self) -> dict:
        contagens = dict(self.db.execute("SELECT estado,COUNT(*) FROM fila GROUP BY estado"))
        return {"ambiente": "SQLITE_LOCAL_TESTES_NAO_MULTIHOST",
                "contagens": contagens, "total": sum(contagens.values()),
                "post_autorizado": False, "download_corporativo_autorizado": False}


def resumo_somente_leitura(banco: Path) -> dict:
    """Consulta via SQLite mode=ro sem migracao, CREATE ou alteracao de journal."""
    if not banco.is_file():
        raise FilaBloqueada("Banco local de teste ausente")
    try:
        with sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            contagens = dict(db.execute("SELECT estado, COUNT(*) FROM fila GROUP BY estado"))
    except sqlite3.Error as exc:
        raise FilaBloqueada("Consulta local indisponivel") from exc
    return {"ambiente": "SQLITE_LOCAL_TESTES_NAO_MULTIHOST", "contagens": contagens,
            "total": sum(contagens.values()), "post_autorizado": False,
            "download_corporativo_autorizado": False}


def main(argv=None):
    """Comando unico APENAS status. Nao aceita escrita fora dos testes Python."""
    import argparse
    p = argparse.ArgumentParser(description="Fila local demonstrativa; somente status, sem POST")
    p.add_argument("--banco", type=Path, required=True)
    p.add_argument("--status", action="store_true", required=True)
    a = p.parse_args(argv)
    try:
        resultado = resumo_somente_leitura(a.banco)
    except FilaBloqueada:
        print(json.dumps({"estado": "BLOQUEADO", "motivo": "Banco local nao acessivel"}))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
