"""Protecao de sobrecarga com metricas simuladas, sem servidor corporativo."""
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from controle_carga import (CargaBloqueada, MedicaoCarga, PoliticaCarga,
                           avaliar_carga, coletar_carga_local, executar_com_admissao)
from piloto_streaming import Diario, chave_documento, processar_local
from test_piloto_streaming import EstadoHTTP, iniciar_servidor


class ControleCarga(unittest.TestCase):
    def setUp(self):
        self.politica = PoliticaCarga(65.0, 75.0, 85.0, 2*1024**3, 1, 5.0)
        self.agora = time.monotonic()

    def medicao(self, **novos):
        dados = dict(cpu_percent=20.0, memoria_percent=30.0, disco_percent=40.0,
                     disco_livre_bytes=4*1024**3, executores_ativos=0,
                     coletado_monotonico=self.agora)
        dados.update(novos)
        return MedicaoCarga(**dados)

    def avaliar(self, **novos):
        return avaliar_carga(self.medicao(**novos), self.politica, agora=self.agora)

    def test_pode_iniciar_so_com_metricas_dentro_dos_limites(self):
        d=self.avaliar()
        self.assertTrue(d.nova_tarefa_permitida)
        self.assertFalse(d.publicacao_autorizada)
        self.assertFalse(d.hml_homologado)

    def test_cpu_alto_bloqueia(self):
        self.assertEqual(self.avaliar(cpu_percent=80).motivos, ("cpu_acima_do_limite",))

    def test_memoria_alta_bloqueia(self):
        self.assertEqual(self.avaliar(memoria_percent=95).motivos, ("memoria_acima_do_limite",))

    def test_disco_cheio_bloqueia(self):
        d=self.avaliar(disco_percent=92, disco_livre_bytes=100)
        self.assertEqual(d.motivos, ("disco_acima_do_limite", "disco_livre_abaixo_do_minimo"))

    def test_execucao_concorrente_bloqueia(self):
        self.assertEqual(self.avaliar(executores_ativos=1).motivos,("limite_de_executores_atingido",))

    def test_amostra_antiga_bloqueia(self):
        self.assertEqual(self.avaliar(coletado_monotonico=self.agora-10).motivos,("telemetria_desatualizada",))

    def test_amostra_do_futuro_bloqueia(self):
        self.assertEqual(self.avaliar(coletado_monotonico=self.agora+1).motivos,("telemetria_desatualizada",))

    def test_valores_invalidos_nan_bool_bloqueiam(self):
        self.assertFalse(self.avaliar(cpu_percent=float("nan")).nova_tarefa_permitida)
        self.assertFalse(self.avaliar(cpu_percent=True).nova_tarefa_permitida)
        self.assertFalse(self.avaliar(disco_livre_bytes=True).nova_tarefa_permitida)
        with self.assertRaises(CargaBloqueada):
            PoliticaCarga(True,75,85,1024,1,5)

    def test_sem_telemetria_bloqueia_antes_da_execucao(self):
        a=[]
        with self.assertRaises(CargaBloqueada):
            executar_com_admissao(politica=self.politica,medidor=lambda:None,executar=lambda:a.append(1))
        self.assertEqual(a,[])

    def test_falha_do_sensor_bloqueia_antes_da_execucao(self):
        a=[]
        def falha(): raise OSError('falha controlada')
        with self.assertRaisesRegex(CargaBloqueada,'telemetria'):
            executar_com_admissao(politica=self.politica,medidor=falha,executar=lambda:a.append(1))
        self.assertEqual(a,[])

    def test_sem_politica_bloqueia(self):
        with self.assertRaises(CargaBloqueada):
            executar_com_admissao(politica=None,medidor=lambda:self.medicao(),executar=lambda:1)

    def test_aprovacao_so_executa_uma_vez(self):
        a=[]
        resultado=executar_com_admissao(politica=self.politica,medidor=lambda:self.medicao(),executar=lambda:a.append(1) or 42)
        self.assertEqual(resultado,42)
        self.assertEqual(a,[1])

    def test_medidor_local_volume_ausente_bloqueia(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(CargaBloqueada):
                coletar_carga_local(Path(pasta)/'nao-existe',executores_ativos=0)

    def test_e2e_local_carga_alta_nao_faz_download_upload(self):
        estado=EstadoHTTP()
        servidor, thread=iniciar_servidor(estado)
        self.addCleanup(thread.join,2)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        url=f'http://127.0.0.1:{servidor.server_port}'
        chave=chave_documento('CONTRATO001','PDF001','V1')
        with tempfile.TemporaryDirectory() as pasta:
            raiz=Path(pasta)
            diario=Diario(raiz/'diario.db')
            try:
                def executar():
                    return processar_local(diario,raiz/'pdfs',url+'/origem/pdf',url+'/objetos/'+chave,
                        'CONTRATO001','PDF001','V1',hashlib.sha256(estado.pdf).hexdigest())
                with self.assertRaisesRegex(CargaBloqueada,'cpu_acima_do_limite'):
                    executar_com_admissao(politica=self.politica,medidor=lambda:self.medicao(cpu_percent=99),executar=executar)
                self.assertEqual(estado.puts,0)
                self.assertIsNone(diario.ler(chave))
            finally: diario.fechar()

    def test_e2e_local_carga_aceitavel_exige_readback(self):
        estado=EstadoHTTP()
        servidor,thread=iniciar_servidor(estado)
        self.addCleanup(thread.join,2)
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        url=f'http://127.0.0.1:{servidor.server_port}'
        chave=chave_documento('CONTRATO001','PDF001','V1')
        with tempfile.TemporaryDirectory() as pasta:
            raiz=Path(pasta)
            diario=Diario(raiz/'diario.db')
            try:
                def executar():
                    return processar_local(diario,raiz/'pdfs',url+'/origem/pdf',url+'/objetos/'+chave,
                        'CONTRATO001','PDF001','V1',hashlib.sha256(estado.pdf).hexdigest())
                resp=executar_com_admissao(politica=self.politica,medidor=lambda:self.medicao(),executar=executar)
                self.assertEqual(resp,'CONFIRMADO')
                self.assertEqual(estado.puts,1)
                self.assertGreater(estado.gets,0)
            finally: diario.fechar()


if __name__=='__main__': unittest.main(verbosity=2)
