"""Testes HTTP reais SOMENTE em 127.0.0.1, nenhum sistema externo."""
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from piloto_streaming import Bloqueado, Diario, chave_documento, evento, ler_ndjson, processar_local


class EstadoHTTP:
    def __init__(self):
        self.pdf = b"%PDF-1.4\n" + b"A" * (240 * 1024) + b"\n%%EOF\n"
        self.destino = {}
        self.puts = 0
        self.gets = 0
        self.status_put = 201
        self.gravar_antes_do_erro = False
        self.mudar_readback = False


def iniciar_servidor(estado):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/origem/pdf":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(estado.pdf)))
                self.end_headers()
                # A origem entrega vários blocos pequenos.
                for inicio in range(0, len(estado.pdf), 8192):
                    self.wfile.write(estado.pdf[inicio:inicio + 8192])
            elif self.path.startswith("/objetos/"):
                estado.gets += 1
                chave = self.path.removeprefix("/objetos/")
                dados = estado.destino.get(chave)
                if dados is None:
                    self.send_error(404)
                    return
                resultado = {"sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados)}
                if estado.mudar_readback:
                    resultado["sha256"] = "0" * 64
                bruto = json.dumps(resultado).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(bruto)))
                self.end_headers()
                self.wfile.write(bruto)
            else:
                self.send_error(404)

        def do_PUT(self):
            if not self.path.startswith("/objetos/"):
                self.send_error(404)
                return
            estado.puts += 1
            tamanho = int(self.headers.get("Content-Length", "0"))
            dado = self.rfile.read(tamanho)
            chave = self.path.removeprefix("/objetos/")
            if (len(dado) != tamanho or len(chave) != 64 or
                    self.headers.get("Idempotency-Key") != chave or
                    self.headers.get("X-Content-SHA256") != hashlib.sha256(dado).hexdigest()):
                self.send_error(422)
                return
            if estado.status_put == 201 or estado.gravar_antes_do_erro:
                estado.destino.setdefault(chave, dado)
            self.send_response(estado.status_put)
            self.send_header("Content-Length", "0")
            self.end_headers()

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor, thread


class PilotoHTTPReal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.estado = EstadoHTTP()
        self.servidor, self.thread = iniciar_servidor(self.estado)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.base = "http://127.0.0.1:" + str(self.servidor.server_port)
        self.chave = chave_documento("CONTRATO001", "PDF001", "V1")
        self.origem = self.base + "/origem/pdf"
        self.destino = self.base + "/objetos/" + self.chave
        self.sha = hashlib.sha256(self.estado.pdf).hexdigest()
        self.banco = self.raiz / "diario.db"
        self.diario = Diario(self.banco)
        self.addCleanup(self.diario.fechar)

    def processar(self, sha=None, limite=1024*1024):
        return processar_local(self.diario, self.raiz / "arquivos", self.origem,
                               self.destino, "CONTRATO001", "PDF001", "V1",
                               sha or self.sha, limite)

    def test_end_to_end_download_put_readback_real_http(self):
        self.assertEqual(self.processar(), "CONFIRMADO")
        self.assertEqual(self.estado.puts, 1)
        self.assertEqual(self.estado.destino[self.chave], self.estado.pdf)
        self.assertEqual(self.diario.ler(self.chave)[1], "CONFIRMADO")
        self.assertGreater(self.estado.gets, 0)
        self.assertEqual((self.raiz / "arquivos" / (self.chave + ".pdf")).read_bytes(), self.estado.pdf)

    def test_replay_reabre_banco_sem_duplicacao(self):
        self.assertEqual(self.processar(), "CONFIRMADO")
        novo = Diario(self.banco)
        try:
            self.assertEqual(processar_local(novo, self.raiz / "arquivos", self.origem,
                self.destino, "CONTRATO001", "PDF001", "V1", self.sha), "CONFIRMADO_SEM_REENVIO")
        finally:
            novo.fechar()
        self.assertEqual(self.estado.puts, 1)

    def test_hash_incorreto_bloqueia_antes_do_upload(self):
        with self.assertRaisesRegex(Bloqueado, "SHA-256"):
            self.processar(sha="0"*64)
        self.assertEqual(self.estado.puts, 0)
        self.assertEqual(self.diario.ler(self.chave)[1], "BLOQUEADO")
        self.assertEqual(list((self.raiz / "arquivos").glob("*.pdf")), [])

    def test_pdf_invalido_bloqueia(self):
        self.estado.pdf = b"not pdf %%EOF"
        self.sha = hashlib.sha256(self.estado.pdf).hexdigest()
        with self.assertRaisesRegex(Bloqueado, "PDF"):
            self.processar()
        self.assertEqual(self.estado.puts, 0)

    def test_limite_tamanho_bloqueia(self):
        with self.assertRaisesRegex(Bloqueado, "limite"):
            self.processar(limite=10)
        self.assertEqual(self.estado.puts, 0)

    def test_resposta_503_apos_armazenar_nao_reenvia(self):
        self.estado.status_put = 503
        self.estado.gravar_antes_do_erro = True
        with self.assertRaisesRegex(Bloqueado, "Upload"):
            self.processar()
        self.assertEqual(self.diario.ler(self.chave)[1], "INCERTO")
        self.estado.status_put = 201
        self.assertEqual(self.processar(), "CONFIRMADO_SEM_REENVIO")
        self.assertEqual(self.estado.puts, 1)

    def test_resposta_503_sem_armazenar_bloqueia_reenvio(self):
        self.estado.status_put = 503
        with self.assertRaises(Bloqueado):
            self.processar()
        self.estado.status_put = 201
        with self.assertRaisesRegex(Bloqueado, "proibido reenviar"):
            self.processar()
        self.assertEqual(self.estado.puts, 1)

    def test_readback_adulterado_nao_confirma(self):
        self.estado.mudar_readback = True
        with self.assertRaisesRegex(Bloqueado, "Readback"):
            self.processar()
        self.assertEqual(self.diario.ler(self.chave)[1], "INCERTO")
        self.assertEqual(self.estado.puts, 1)

    def test_concorrencia_segundo_executor_nao_assume(self):
        self.diario.iniciar(self.chave, self.sha)
        self.diario.reservar_exclusivamente(self.chave)
        segundo = Diario(self.banco)
        try:
            with self.assertRaisesRegex(Bloqueado, "reservado"):
                segundo.reservar_exclusivamente(self.chave)
            with self.assertRaisesRegex(Bloqueado, "liberacao governada"):
                processar_local(segundo, self.raiz / "arquivos", self.origem,
                    self.destino, "CONTRATO001", "PDF001", "V1", self.sha)
        finally:
            segundo.fechar()
        self.assertEqual(self.estado.puts, 0)

    def test_hash_manifesto_conflitante_bloqueia(self):
        self.diario.iniciar(self.chave, self.sha)
        with self.assertRaisesRegex(Bloqueado, "conflitante"):
            self.diario.iniciar(self.chave, "a" * 64)
        self.assertEqual(self.estado.puts, 0)

    def test_bloqueio_rede_nao_local(self):
        with self.assertRaisesRegex(Bloqueado, "127.0.0.1"):
            processar_local(self.diario, self.raiz / "arquivos", "https://servidor.empresa.exemplo/pdf",
                self.destino, "CONTRATO001", "PDF001", "V1", self.sha)
        self.assertEqual(self.estado.puts, 0)

    def test_evento_ndjson_validado(self):
        linha = evento("download", "conferido", "CORR001", 123)
        self.assertTrue(linha.endswith("\n"))
        self.assertEqual(json.loads(linha)["bytes"], 123)
        with self.assertRaises(Bloqueado):
            evento("download", "conferido", "linha\nquebrada")

    def test_ndjson_fragmentado_e_linhas_agregadas(self):
        linha1 = evento("download", "confirmado", "C001", 100).encode()
        linha2 = evento("upload", "confirmado", "C001", 200).encode()
        partes = [linha1[:7], linha1[7:] + linha2[:13], linha2[13:]]
        self.assertEqual([e["bytes"] for e in ler_ndjson(partes)], [100, 200])

    def test_ndjson_truncado_e_duplicado_falham(self):
        with self.assertRaisesRegex(Bloqueado, "incompleto"):
            list(ler_ndjson([b'{"evento":1}']))
        with self.assertRaisesRegex(Bloqueado, "malformado"):
            list(ler_ndjson([b'{"evento":1,"evento":2}\n']))

    def test_pdfs_nao_sao_publicados_no_fluxo_de_negocio(self):
        self.processar()
        self.assertEqual(self.estado.puts, 1)
        self.assertNotIn("/lotes/", self.destino)
        self.assertEqual(self.diario.ler(self.chave)[1], "CONFIRMADO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
