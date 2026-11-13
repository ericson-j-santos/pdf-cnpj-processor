"""Plano HML offline com controles positivos/negativos e sem rede externa."""
import contextlib
import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import planejar_hml as p

BASE = Path(__file__).resolve().parent


def exemplo():
    return json.loads((BASE / 'manifesto-hml-exemplo.json').read_text())


def auditoria_ok(*args, **kwargs):
    assert kwargs == {"max_cpu": 60., "max_mem": 75., "minimo_gib": 5}
    return {"aptidao_tecnica_local": "APTO_APENAS_PARA_TESTE_LOCAL",
            "aptidao_corporativa": "NAO_HOMOLOGADO",
            "post_autorizado": False, "download_corporativo_autorizado": False}


class PlanejamentoHML(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.m = self.raiz / 'manifesto.json'
        self.m.write_text(json.dumps(exemplo()))

    def guardar(self, obj):
        self.m.write_text(json.dumps(obj))

    def obter_plano(self, **kwargs):
        return p.planejar(manifesto=self.m, volume=self.raiz, max_documentos=10,
                          auditor=auditoria_ok, **kwargs)

    def test_plano_local_valido_nao_autoriza_hml(self):
        plano = self.obter_plano(premissa_hml=True)
        self.assertEqual(plano['plano']['documentos'], 2)
        self.assertEqual(plano['plano']['lotes'], 1)
        self.assertEqual(len(plano['plano']['chaves_idempotencia']), 2)
        self.assertFalse(plano['homologacao_corporativa_comprovada'])
        self.assertEqual(plano['aprovacoes_hml_comprovadas'], 0)
        self.assertTrue(plano['premissa_hml_declarada'])
        self.assertFalse(plano['transferencia_autorizada'])
        self.assertFalse(plano['publicacao_autorizada'])
        self.assertFalse(plano['rede_consultada'])
        self.assertEqual(plano['plano']['hashes_documentos'], 'DECLARADOS_NAO_CONFERIDOS')

    def test_repeticao_tem_mesmas_chaves_sem_efeito(self):
        a = self.obter_plano()['plano']
        b = self.obter_plano()['plano']
        self.assertEqual(a, b)
        self.assertEqual(list(self.raiz.iterdir()), [self.m])

    def test_mesmo_documento_duplicado_rejeitado(self):
        m = exemplo()
        m['lotes'][0]['documentos'].append(copy.deepcopy(m['lotes'][0]['documentos'][0]))
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'duplicado'):
            p.analisar_manifesto(self.m)

    def test_contrato_em_dois_lotes_rejeitado(self):
        m = exemplo()
        m['lotes'].append({'lote_id': 'LOTE_FICTICIO_002', 'documentos': [
            dict(m['lotes'][0]['documentos'][0], documento_id='PDF_NOVO')
        ]})
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'dois lotes'):
            p.analisar_manifesto(self.m)

    def test_lote_duplicado_rejeitado(self):
        m = exemplo()
        m['lotes'].append(copy.deepcopy(m['lotes'][0]))
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'lote'):
            p.analisar_manifesto(self.m)

    def test_hash_ausente_rejeitado(self):
        m = exemplo()
        m['lotes'][0]['documentos'][0]['sha256'] = '123'
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'Hash'):
            p.analisar_manifesto(self.m)

    def test_tamanho_booleano_rejeitado(self):
        m = exemplo()
        m['lotes'][0]['documentos'][0]['bytes'] = True
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'Documento excede'):
            p.analisar_manifesto(self.m)

    def test_tamanho_acima_8mib_rejeitado(self):
        m = exemplo()
        m['lotes'][0]['documentos'][0]['bytes'] = 9*1024**2
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'limite'):
            p.analisar_manifesto(self.m)

    def test_limite_total_documentos(self):
        with self.assertRaisesRegex(p.PlanoBloqueado, 'lote invalida'):
            p.analisar_manifesto(self.m, max_documentos=1)

    def test_campos_desconhecidos_bloqueiam_url_token(self):
        m = exemplo()
        m['lotes'][0]['documentos'][0]['url'] = 'https://privado.exemplo.org'
        self.guardar(m)
        with self.assertRaisesRegex(p.PlanoBloqueado, 'campos'):
            p.analisar_manifesto(self.m)

    def test_chaves_json_duplicadas_rejeitadas(self):
        self.m.write_text('{"schema_version":1,"schema_version":1,"lotes":[]}')
        with self.assertRaises(p.PlanoBloqueado):
            p.analisar_manifesto(self.m)

    def test_manifesto_grande_bloqueado(self):
        self.m.write_bytes(b' '*(p.LIMITE_MANIFESTO+1))
        with self.assertRaisesRegex(p.PlanoBloqueado, 'grande'):
            p.analisar_manifesto(self.m)

    def test_auditoria_nao_apta_bloqueia(self):
        with self.assertRaisesRegex(p.PlanoBloqueado, 'bloqueada'):
            p.planejar(manifesto=self.m, volume=self.raiz, max_documentos=10,
                      auditor=lambda *args, **kw: dict(auditoria_ok(*args, **kw), aptidao_tecnica_local='BLOQUEADO'))

    def test_auditoria_alega_post_autorizado_bloqueia(self):
        with self.assertRaisesRegex(p.PlanoBloqueado, 'inconsistente'):
            p.planejar(manifesto=self.m, volume=self.raiz, max_documentos=10,
                      auditor=lambda *args, **kw: dict(auditoria_ok(*args, **kw), post_autorizado=True))

    def test_falha_do_sensor_bloqueia(self):
        def falhar(*args, **kw):
            raise OSError('nao expor detalhes internos')
        with self.assertRaisesRegex(p.PlanoBloqueado, 'capacidade'):
            p.planejar(manifesto=self.m, volume=self.raiz, max_documentos=10, auditor=falhar)

    def test_sem_manifesto_nao_execucao(self):
        self.m.unlink()
        with self.assertRaises(p.PlanoBloqueado):
            self.obter_plano()

    def test_cli_positivo_com_auditoria_simulada(self):
        s = io.StringIO()
        with patch.object(p.auditar_linux, 'auditar', side_effect=auditoria_ok):
            with contextlib.redirect_stdout(s):
                status = p.main(['--manifesto', str(self.m), '--volume', str(self.raiz),
                                 '--premissa-hml-declarada'])
        self.assertEqual(status, 0)
        d = json.loads(s.getvalue())
        self.assertEqual(d['estado'], 'PLANEJADO_APENAS_SEM_EXECUCAO')
        self.assertFalse(d['publicacao_autorizada'])

    def test_shell_nao_aceita_post(self):
        for acao in ('post', 'enviar', 'publicar', 'transferir'):
            proc = subprocess.run(['bash', str(BASE / 'script-linux.sh'), acao],
                                  capture_output=True, text=True, timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('BLOQUEADO', proc.stderr)

    def test_shell_planejar_requer_manifesto(self):
        proc = subprocess.run(['bash', str(BASE / 'script-linux.sh'), 'planejar-hml',
                               '--volume', str(self.raiz)],
                              capture_output=True, text=True, timeout=5)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('required', proc.stderr)

    def test_rede_fica_desativada_mesmo_com_premissa(self):
        def sem_rede(*args, **kw):
            raise AssertionError('qualquer rede proibida')
        with patch('socket.create_connection', side_effect=sem_rede):
            plano = self.obter_plano(premissa_hml=True)
        self.assertFalse(plano['rede_consultada'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
