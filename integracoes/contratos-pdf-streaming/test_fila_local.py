"""Testes reais de SQLite de teste e HTTP 127.0.0.1; nenhum banco corporativo."""
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from fila_local import FilaLocal, FilaBloqueada
from piloto_streaming import chave_documento
from test_piloto_streaming import EstadoHTTP, iniciar_servidor

BASE = Path(__file__).resolve().parent


class FilaTransacional(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.banco = Path(self.tmp.name)/"fila.db"
        self.fila = FilaLocal(self.banco)
        self.addCleanup(self.fila.fechar)
        self.args = dict(lote_id="LOTE1",contrato_id="CT1",documento_id="DOC1",
                         versao="V1",sha256="a"*64,bytes_esperados=100)

    def enfileirar(self, **kw):
        return self.fila.enfileirar(**dict(self.args, **kw))

    def test_inclusao_idempotente_mesma_chave(self):
        chave=self.enfileirar()
        self.assertEqual(self.enfileirar(),chave)
        self.assertEqual(self.fila.resumo()["total"],1)
        self.assertEqual(self.fila.obter(chave)["estado"],"PENDENTE")

    def test_manifesto_divergente_bloqueia_sem_alterar(self):
        chave=self.enfileirar()
        with self.assertRaisesRegex(FilaBloqueada,"Manifesto"):
            self.enfileirar(sha256="b"*64)
        self.assertEqual(self.fila.obter(chave)["sha256"],"a"*64)

    def test_mesmo_documento_em_outro_lote_bloqueia(self):
        self.enfileirar()
        with self.assertRaisesRegex(FilaBloqueada,"outro lote"):
            self.enfileirar(lote_id="LOTE2")
        self.assertEqual(self.fila.resumo()["total"],1)

    def test_identificador_invalido_bloqueia(self):
        for invalido in ("", "../../etc/passwd", "contrato com espaco", "x"*65):
            with self.subTest(invalido=invalido):
                with self.assertRaises(FilaBloqueada):
                    self.enfileirar(contrato_id=invalido)

    def test_tamanho_e_hash_invalidos_bloqueiam(self):
        for n in (0,-1,True,8388609):
            with self.subTest(n=n):
                with self.assertRaises(FilaBloqueada):self.enfileirar(bytes_esperados=n)
        with self.assertRaises(FilaBloqueada):self.enfileirar(sha256="x"*64)

    def test_duas_conexoes_nao_reservam_ao_mesmo_tempo(self):
        self.enfileirar()
        segunda=FilaLocal(self.banco)
        self.addCleanup(segunda.fechar)
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        with self.assertRaisesRegex(FilaBloqueada,"reserva"):
            segunda.reservar(executor="WORKER2",agora=1001)
        self.assertEqual(self.fila.obter(a["chave"])["geracao"],1)

    def test_token_incorreto_nao_altera(self):
        self.enfileirar()
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        with self.assertRaisesRegex(FilaBloqueada,"posse"):
            self.fila.marcar_incerto(chave=a["chave"],token="f"*32,geracao=1,agora=1001)
        self.assertEqual(self.fila.obter(a["chave"])["estado"],"RESERVADO")

    def test_geracao_incorreta_nao_altera(self):
        self.enfileirar()
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        with self.assertRaises(FilaBloqueada):
            self.fila.marcar_incerto(chave=a["chave"],token=a["token"],geracao=99,agora=1001)
        self.assertEqual(self.fila.obter(a["chave"])["estado"],"RESERVADO")

    def test_lease_expirado_nao_reassume_sem_readback(self):
        self.enfileirar()
        a=self.fila.reservar(executor="WORKER1",segundos=30,agora=1000)
        with self.assertRaises(FilaBloqueada):
            self.fila.marcar_incerto(chave=a["chave"],token=a["token"],geracao=1,agora=1030)
        with self.assertRaises(FilaBloqueada):
            self.fila.reservar(executor="WORKER2",agora=1100)
        self.assertEqual(self.fila.obter(a["chave"])["estado"],"RESERVADO")

    def test_crash_reabrir_preserva_incerto_sem_replay(self):
        self.enfileirar()
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        self.fila.marcar_incerto(chave=a["chave"],token=a["token"],geracao=1,agora=1001)
        with FilaLocal(self.banco) as reiniciado:
            self.assertEqual(reiniciado.obter(a["chave"])["estado"],"INCERTO_UPLOAD")
            with self.assertRaises(FilaBloqueada):reiniciado.reservar(executor="WORKER2",agora=1002)

    def test_confirma_sem_readback_impossivel(self):
        self.enfileirar()
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        self.fila.marcar_incerto(chave=a["chave"],token=a["token"],geracao=1,agora=1001)
        with self.assertRaises(FilaBloqueada):
            self.fila.confirmar_loopback(chave=a["chave"],token=a["token"],geracao=1,
                url_consulta="https://exemplo.org/objeto",agora=1002)
        self.assertEqual(self.fila.obter(a["chave"])["estado"],"INCERTO_UPLOAD")

    def test_readback_http_real_confirma_apos_put_ficticio(self):
        estado=EstadoHTTP()
        servidor,thread=iniciar_servidor(estado)
        self.addCleanup(thread.join,2)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        data=estado.pdf
        ch=self.fila.enfileirar(lote_id="LOTE1",contrato_id="CT1",documento_id="DOC1",
            versao="V1",sha256=hashlib.sha256(data).hexdigest(),bytes_esperados=len(data))
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        self.fila.marcar_incerto(chave=ch,token=a["token"],geracao=1,agora=1001)
        # Somente populacao de objeto em stub de destino em loopback; sem rede externa.
        estado.destino[ch]=data
        url=f"http://127.0.0.1:{servidor.server_port}/objetos/{ch}"
        self.fila.confirmar_loopback(chave=ch,token=a["token"],geracao=1,
                                   url_consulta=url,agora=1002)
        self.assertEqual(self.fila.obter(ch)["estado"],"CONFIRMADO_UPLOAD")
        self.assertEqual(estado.puts,0)
        self.assertGreater(estado.gets,0)

    def test_readback_adulterado_preserva_incerto(self):
        estado=EstadoHTTP()
        servidor,thread=iniciar_servidor(estado)
        self.addCleanup(thread.join,2)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        data=estado.pdf
        ch=self.fila.enfileirar(lote_id="LOTE1",contrato_id="CT1",documento_id="DOC1",
            versao="V1",sha256=hashlib.sha256(data).hexdigest(),bytes_esperados=len(data))
        a=self.fila.reservar(executor="WORKER1",agora=1000)
        self.fila.marcar_incerto(chave=ch,token=a["token"],geracao=1,agora=1001)
        estado.destino[ch]=data
        estado.mudar_readback=True
        url=f"http://127.0.0.1:{servidor.server_port}/objetos/{ch}"
        with self.assertRaisesRegex(FilaBloqueada,"Readback ausente"):
            self.fila.confirmar_loopback(chave=ch,token=a["token"],geracao=1,
                                       url_consulta=url,agora=1002)
        self.assertEqual(self.fila.obter(ch)["estado"],"INCERTO_UPLOAD")

    def test_nao_confirma_se_lease_expirou(self):
        estado=EstadoHTTP()
        servidor,thread=iniciar_servidor(estado)
        self.addCleanup(thread.join,2)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        data=estado.pdf
        ch=self.fila.enfileirar(lote_id="LOTE1",contrato_id="CT1",documento_id="DOC1",
            versao="V1",sha256=hashlib.sha256(data).hexdigest(),bytes_esperados=len(data))
        a=self.fila.reservar(executor="WORKER1",segundos=30,agora=1000)
        self.fila.marcar_incerto(chave=ch,token=a["token"],geracao=1,agora=1001)
        estado.destino[ch]=data
        url=f"http://127.0.0.1:{servidor.server_port}/objetos/{ch}"
        with self.assertRaisesRegex(FilaBloqueada,"Lease"):
            self.fila.confirmar_loopback(chave=ch,token=a["token"],geracao=1,
                                       url_consulta=url,agora=1030)
        self.assertEqual(self.fila.obter(ch)["estado"],"INCERTO_UPLOAD")

    def test_status_bash_restrito(self):
        chave=self.enfileirar()
        p=subprocess.run(['bash',str(BASE/'script-linux.sh'),'fila-status','--banco',str(self.banco)],
                         capture_output=True,text=True,timeout=7)
        self.assertEqual(p.returncode,0,p.stderr)
        d=json.loads(p.stdout)
        self.assertEqual(d['total'],1)
        self.assertFalse(d['post_autorizado'])
        self.assertEqual(self.fila.obter(chave)['estado'],'PENDENTE')

    def test_status_somente_leitura_nao_muda_dados_ou_arquivo(self):
        chave=self.enfileirar()
        before=self.banco.read_bytes()
        p=subprocess.run(['bash',str(BASE/'script-linux.sh'),'fila-status','--banco',str(self.banco)],
                         capture_output=True,text=True,timeout=7)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.banco.read_bytes(),before)
        self.assertEqual(self.fila.obter(chave)['estado'],'PENDENTE')

    def test_nao_cria_banco_quando_inexistente(self):
        caminho=Path(self.tmp.name)/'inexistente.db'
        p=subprocess.run(['bash',str(BASE/'script-linux.sh'),'fila-status','--banco',str(caminho)],
                         capture_output=True,text=True,timeout=7)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(caminho.exists())

    def test_sqlserver_modelo_posse_e_transacao(self):
        sql=(BASE/'fila_sqlserver.sql').read_text()
        for fragmento in ('UPDLOCK', 'HOLDLOCK', 'sp_getapplock', 'BEGIN TRANSACTION',
                          'XACT_ABORT ON', 'Geracao', 'Token', 'LeaseAteUtc',
                          'INCERTO_UPLOAD','SYSUTCDATETIME()', 'UNIQUE (ContratoId, DocumentoId, Versao)',
                          'fila_pdf_hml_confirmar_readback'):
            with self.subTest(fragmento=fragmento):self.assertIn(fragmento,sql)
        self.assertNotIn('GRANT CONTROL',sql)
        self.assertNotIn('DROP TABLE',sql)

    def test_sqlserver_nao_prova_execucao_real(self):
        texto=(BASE/'FILA-TRANSACIONAL-LINUX.md').read_text()
        self.assertIn('SQL Server corporativo não foi acessado',texto)
        self.assertIn('0/8',texto)


if __name__ == '__main__':unittest.main(verbosity=2)
