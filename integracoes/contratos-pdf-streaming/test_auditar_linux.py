"""Testes do preflight Linux; nunca fazem rede fora do mock."""
import contextlib
import io
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auditar_linux as a

BASE = Path(__file__).resolve().parent


class DiagnosticoLinux(unittest.TestCase):
    def test_aptidao_tecnica_nao_autoriza_corporativo(self):
        estado, motivos = a.avaliar(cpu=24., memoria_pct=45., disco_livre=10*1024**3,
                                   disco_total=30*1024**3, python_ok=True,
                                   cpu_limite=60., memoria_limite=75., disco_minimo=5*1024**3)
        self.assertEqual((estado, motivos), ("APTO_APENAS_PARA_TESTE_LOCAL", []))

    def test_cpu_alta_bloqueia(self):
        self.assertIn("CPU_ALTA", a.avaliar(cpu=91., memoria_pct=45., disco_livre=10*1024**3,
           disco_total=30*1024**3, python_ok=True,cpu_limite=60.,memoria_limite=75.,disco_minimo=5*1024**3)[1])

    def test_memoria_alta_bloqueia(self):
        estado, motivos = a.avaliar(cpu=20.,memoria_pct=89.,disco_livre=10*1024**3,
            disco_total=30*1024**3,python_ok=True,cpu_limite=60.,memoria_limite=75.,disco_minimo=5*1024**3)
        self.assertEqual(estado,"BLOQUEADO"); self.assertIn("MEMORIA_ALTA", motivos)

    def test_disco_e_python_invalido(self):
        status, motivos=a.avaliar(cpu=20.,memoria_pct=20.,disco_livre=1*1024**3,
           disco_total=20*1024**3,python_ok=False,cpu_limite=60.,memoria_limite=75.,disco_minimo=5*1024**3)
        self.assertEqual(status,"BLOQUEADO")
        self.assertEqual(set(motivos),{"DISCO_INSUFICIENTE","PYTHON_INFERIOR_3_10"})

    def test_nan_booleanos_invalidos(self):
        for cpu in (float('nan'), True, -1, 101):
            self.assertEqual(a.avaliar(cpu=cpu,memoria_pct=20.,disco_livre=10*1024**3,
             disco_total=20*1024**3,python_ok=True,cpu_limite=60.,memoria_limite=75.,
             disco_minimo=5*1024**3)[0],"BLOQUEADO")

    def test_cpu_delta_amostras_controladas(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'stat'
            samples=iter(['cpu  100 0 100 800 0 0 0 0 0 0\n',
                          'cpu  150 0 150 900 0 0 0 0 0 0\n'])
            with patch.object(a,'ler_texto',side_effect=lambda _:next(samples)):
                self.assertEqual(a.cpu_percentual(caminho=path,dormir=lambda _:None),50.)

    def test_memoria_procmeminfo(self):
        with patch.object(a,'ler_texto',return_value='MemTotal: 100000 kB\nMemAvailable: 75000 kB\n'):
            self.assertEqual(a.memoria(),(25.,75000*1024))

    def test_rede_nao_ativa_por_padrao(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(a,'verificar_tls',side_effect=AssertionError("nao deve chamar")):
                result=a.auditar(Path(d),max_cpu=60,max_mem=75,minimo_gib=1)
        self.assertEqual(result['aptidao_corporativa'],'NAO_HOMOLOGADO')
        self.assertFalse(result['download_corporativo_autorizado'])
        self.assertEqual(result['teste_rede_tls'],'NAO_EXECUTADO_SEM_AUTORIZACAO')
        self.assertEqual(result['aprovacoes_hml'],0)

    def test_rede_requer_autorizacao_explicita(self):
        with tempfile.TemporaryDirectory() as d:
            policy=Path(d)/'alvos.json'
            policy.write_text(json.dumps({'servicos':[{'nome':'origem','hostname':'origem.example.org','porta':443}]}))
            with patch.object(a,'verificar_tls',side_effect=AssertionError('nao sondar')):
                with self.assertRaisesRegex(a.EntradaInvalida,'autorizacao'):
                    a.auditar(Path(d),max_cpu=60,max_mem=75,minimo_gib=1,alvos=policy)

    def test_sondagem_tls_autorizada_usa_alias_sem_host(self):
        with tempfile.TemporaryDirectory() as d:
            policy=Path(d)/'alvos.json'
            policy.write_text(json.dumps({'servicos':[{'nome':'origem','hostname':'origem.example.org','porta':443}]}))
            with patch.object(a,'verificar_tls',return_value='TLS_VALIDO_SEM_VALIDAR_API') as called:
                result=a.auditar(Path(d),max_cpu=60,max_mem=75,minimo_gib=1,alvos=policy,autorizar_sonda=True)
            called.assert_called_once_with('origem','origem.example.org',443)
            self.assertNotIn('origem.example.org',json.dumps(result))
            self.assertEqual(result['permissao_api'],'NAO_VERIFICADA')
            self.assertFalse(result['post_autorizado'])

    def test_politica_alvos_dup_nome_host_numerico_invalidos(self):
        invalidos=[
          {'servicos':[{'nome':'origem','hostname':'localhost','porta':443}]},
          {'servicos':[{'nome':'origem','hostname':'127.0.0.1','porta':80}]},
          {'servicos':[{'nome':'origem','hostname':'ok.example.org','porta':True}]},
          {'servicos':[{'nome':'origem','hostname':'ok.example.org','porta':443},
                       {'nome':'origem','hostname':'ok2.example.org','porta':443}]},
          {'servicos':[{'nome':['nome'],'hostname':'ok.example.org','porta':443}]},
          {'servicos':[{'nome':'origem','hostname':'ok.example.org','porta':443,'token':'segredo'}]},
        ]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'lista.json'
            for item in invalidos:
                with self.subTest(item=item):
                    path.write_text(json.dumps(item))
                    with self.assertRaises(a.EntradaInvalida):a.validar_alvos(path)
            path.write_text('{"servicos":[],"servicos":[]}')
            with self.assertRaises(a.EntradaInvalida):a.validar_alvos(path)

    def test_dispatcher_linux_integra_auditoria_sem_liberar_post(self):
        with tempfile.TemporaryDirectory() as d:
            proc=subprocess.run(['bash',str(BASE/'script-linux.sh'),'auditoria','--volume',d,
                                 '--minimo-gib','1','--json'],capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        obj=json.loads(proc.stdout)
        self.assertEqual(obj['aptidao_corporativa'],'NAO_HOMOLOGADO')
        self.assertFalse(obj['post_autorizado'])

    def test_dispatcher_nao_ativa_operacao_real(self):
        for acao in ('enviar','publicar','transferir'):
            with self.subTest(acao=acao):
                proc=subprocess.run(['bash',str(BASE/'script-linux.sh'),acao],capture_output=True,text=True,timeout=7)
                self.assertNotEqual(proc.returncode,0)
                self.assertIn('BLOQUEADO',proc.stderr)

    def test_arquivo_exemplo_rede_sem_dados_reais(self):
        alvos=a.validar_alvos(BASE/'alvos-exemplo.json')
        self.assertEqual([x[0] for x in alvos],['origem','upload','publicacao'])
        self.assertTrue(all(host.endswith('.exemplo.org') for _,host,_ in alvos))

    def test_rede_nao_consultada_se_cpu_sobrecarga(self):
        with tempfile.TemporaryDirectory() as d:
            policy=Path(d)/'alvos.json'
            policy.write_text(json.dumps({'servicos':[{'nome':'origem','hostname':'origem.example.org','porta':443}]}))
            with patch.object(a,'cpu_percentual',return_value=99.0):
                with patch.object(a,'verificar_tls',side_effect=AssertionError('NAO SONDAR')):
                    report=a.auditar(Path(d),max_cpu=60,max_mem=75,minimo_gib=1,
                                   alvos=policy,autorizar_sonda=True)
            self.assertEqual(report['teste_rede_tls'],'NAO_EXECUTADO_HOST_SOBRECARGA')
            self.assertEqual(report['aptidao_tecnica_local'],'BLOQUEADO')

    def test_limite_cpu_nan_falha_com_json_valido(self):
        with tempfile.TemporaryDirectory() as d:
            proc=subprocess.run(['bash',str(BASE/'auditar-linux.sh'),'--volume',d,
                                 '--minimo-gib','1','--max-cpu','nan','--json'],
                                 capture_output=True,text=True,timeout=8)
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual(json.loads(proc.stdout)['aptidao_corporativa'],'NAO_HOMOLOGADO')

    def test_script_shell_sem_argumentos_bloqueia(self):
        p=subprocess.run(['bash',str(BASE/'auditar-linux.sh')],capture_output=True,text=True,timeout=8)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('required',p.stderr)

    def test_script_shell_saida_local_sem_homologacao(self):
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run(['bash',str(BASE/'auditar-linux.sh'),'--volume',d,
                             '--minimo-gib','1','--json'],capture_output=True,text=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stderr)
        obj=json.loads(p.stdout)
        self.assertEqual(obj['aptidao_corporativa'],'NAO_HOMOLOGADO')
        self.assertFalse(obj['download_corporativo_autorizado'])
        self.assertEqual(obj['aprovacoes_hml'],0)
        self.assertNotIn(d,p.stdout)

    def test_script_modo_texto_resumo(self):
        with tempfile.TemporaryDirectory() as d:
            p=subprocess.run(['bash',str(BASE/'auditar-linux.sh'),'--volume',d,'--minimo-gib','1'],
                capture_output=True,text=True,timeout=8)
        self.assertIn('RESULTADO CORPORATIVO: NAO_HOMOLOGADO',p.stdout)
        self.assertIn('AUTORIZADO PARA BAIXAR/PUBLICAR: NAO',p.stdout)

    def test_sistema_timer_onseshot_sem_rede(self):
        service=(BASE/'contratos-auditoria.service').read_text()
        timer=(BASE/'contratos-auditoria.timer').read_text()
        self.assertIn('PrivateNetwork=yes',service)
        self.assertIn('Type=oneshot',service)
        self.assertIn('NoNewPrivileges=yes',service)
        self.assertIn('MemoryMax=256M',service)
        self.assertIn('CPUQuota=20%',service)
        self.assertNotIn('--autorizar-sonda-tls',service)
        self.assertIn('Persistent=false',timer)
        self.assertIn('OnCalendar=',timer)
        self.assertNotIn('ExecStart=',timer)

    def test_invalid_volume_bloqueia(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(a.EntradaInvalida):
                a.auditar(Path(d)/'inexistente',max_cpu=60,max_mem=75,minimo_gib=5)

    def test_teste_de_redirecionamentos_ausente(self):
        # TLS e TCP sem HTTP nem cabecalhos que possam enviar credenciais.
        import inspect
        txt=inspect.getsource(a.verificar_tls)
        self.assertNotIn('HTTPConnection',txt)
        self.assertNotIn('POST',txt.split('    try:',1)[-1])
        self.assertNotIn('request(',txt)


if __name__=='__main__': unittest.main(verbosity=2)
