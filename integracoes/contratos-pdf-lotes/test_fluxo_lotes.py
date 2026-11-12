import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fluxo_lotes as alvo


class APIEmMemoria:
    def __init__(self):
        self.aplicados = set()
        self.posts = []
        self.contexto_alterado = {}
        self.falha_get = None
        self.falha_post_depois_de_aplicar = False
        self.prova_invalida = False
        self.status_post = 201

    def __call__(self, metodo, url, token, corpo=None, chave=None):
        assert url.startswith('https://negocio.test/api/lotes/')
        assert token == 'token-ficticio'
        lote = url.split('/lotes/', 1)[1].split('/', 1)[0]
        sufixo = url.rsplit('/', 1)[-1]
        if metodo == 'GET' and self.falha_get:
            return self.falha_get, {}
        if metodo == 'GET' and sufixo == 'transicao':
            if lote not in self.aplicados:
                return 200, {'lote_id': lote, 'estado': 'NAO_APLICADA'}
            prova = {'lote_id': lote, 'estado': 'APLICADA',
                     'associacao_id': 214, 'workflow_id': 181,
                     'etapa_origem_id': 501, 'funcao_nome': 'fn_g1865',
                     'funcao_executada': True, 'etapa_destino_id': 777,
                     'registro_id': f'recibo-{lote}'}
            if self.prova_invalida:
                prova['workflow_id'] = 999
            return 200, prova
        if metodo == 'GET' and sufixo == 'contexto':
            contexto = {'lote_id': lote,
                        'conte_lote': {'encontrado': True, 'valido': True, 'quantidade_contratos': 2},
                        'associacao_id': 214, 'workflow_id': 181,
                        'etapa_atual_id': 501, 'funcao_nome': 'fn_g1865',
                        'funcao_habilitada': True}
            contexto.update(self.contexto_alterado)
            return 200, contexto
        if metodo == 'POST' and sufixo == 'transicao':
            assert isinstance(chave, str) and len(chave) == 64
            assert corpo['lote_id'] == lote and corpo['funcao_nome'] == 'fn_g1865'
            self.posts.append((lote, chave))
            self.aplicados.add(lote)
            if self.falha_post_depois_de_aplicar:
                raise ConnectionError('simulacao: perda da resposta apos processamento')
            return self.status_post, {'recebido': True}
        raise AssertionError(f'Chamada inesperada {metodo} {url}')


class TesteFluxoPorLote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.manifesto = self.raiz / 'lotes.tsv'
        self.manifesto.write_text('lote_id\nL001\nL002\n', encoding='utf-8')
        self.api = APIEmMemoria()
        self.env = {
            'MODO': 'VALIDAR', 'LIMITE_LOTES': '10',
            'API_NEGOCIO_URL': 'https://negocio.test/api',
            'TOKEN_NEGOCIO': 'token-ficticio',
            'MANIFESTO_LOTES': str(self.manifesto),
            'ESTADO_DIR': str(self.raiz / 'estado'),
            'AUTORIZACAO_POST': 'SIM', 'CONTRATO_API_HOMOLOGADO': 'SIM',
            'CUSTO_ZERO_VALIDADO': 'SIM',
        }

    def rodar(self, **env):
        buffer = io.StringIO()
        with patch.dict(os.environ, self.env | env, clear=True), patch.object(alvo, 'chamar_api', self.api), contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            codigo = alvo.main()
        return codigo, buffer.getvalue()

    def estados(self):
        p = self.raiz / 'estado' / 'estado.jsonl'
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def test_validar_somente_leitura_sem_post(self):
        codigo, texto = self.rodar()
        self.assertEqual(codigo, 0, texto)
        self.assertEqual(self.api.posts, [])
        self.assertEqual([x['estado'] for x in self.estados()], ['APTO', 'APTO'])

    def test_enviar_dois_lotes_e_repetir_sem_duplicar(self):
        self.assertEqual(self.rodar(MODO='ENVIAR')[0], 0)
        self.assertEqual(len(self.api.posts), 2)
        self.assertEqual(self.rodar(MODO='ENVIAR')[0], 0)
        self.assertEqual(len(self.api.posts), 2)
        self.assertEqual([x['estado'] for x in self.estados()], ['CONFIRMADO', 'CONFIRMADO'])

    def test_limite_um_por_execucao_e_retomada(self):
        self.assertEqual(self.rodar(MODO='ENVIAR', LIMITE_LOTES='1')[0], 0)
        self.assertEqual([x[0] for x in self.api.posts], ['L001'])
        self.assertEqual(self.rodar(MODO='ENVIAR', LIMITE_LOTES='1')[0], 0)
        self.assertEqual([x[0] for x in self.api.posts], ['L001', 'L002'])

    def test_lote_inexistente_bloqueia_so_este_lote(self):
        self.api.contexto_alterado['conte_lote'] = {'encontrado': False, 'valido': True, 'quantidade_contratos': 2}
        codigo, _ = self.rodar(MODO='ENVIAR')
        self.assertEqual(codigo, 0)
        self.assertFalse(self.api.posts)
        self.assertEqual([x['estado'] for x in self.estados()], ['BLOQUEADO', 'BLOQUEADO'])

    def test_desvios_214_181_501_funcao_bloqueiam_post(self):
        for campo, valor in [('associacao_id', 999), ('workflow_id', 999),
                              ('etapa_atual_id', 999), ('funcao_nome', 'outra_funcao'),
                              ('funcao_habilitada', False)]:
            with self.subTest(campo=campo):
                self.api.contexto_alterado = {campo: valor}
                estado = self.raiz / 'estado' / 'estado.jsonl'
                if estado.exists():
                    estado.unlink()
                codigo, _ = self.rodar(MODO='ENVIAR')
                self.assertEqual(codigo, 0)
                self.assertEqual(self.api.posts, [])

    def test_post_aceito_sem_comprovacao_nao_confirma(self):
        self.api.prova_invalida = True
        codigo, _ = self.rodar(MODO='ENVIAR', LIMITE_LOTES='1')
        self.assertEqual(codigo, 0)
        self.assertEqual(len(self.api.posts), 1)
        self.assertEqual(self.estados()[-1]['estado'], 'INCERTO')
        self.assertEqual(self.rodar(MODO='ENVIAR', LIMITE_LOTES='1')[0], 0)
        self.assertEqual(len(self.api.posts), 2)
        self.assertEqual([x[0] for x in self.api.posts], ['L001', 'L002'])

    def test_queda_apos_post_nao_reenvia_incerto(self):
        self.api.falha_post_depois_de_aplicar = True
        codigo, _ = self.rodar(MODO='ENVIAR', LIMITE_LOTES='1')
        self.assertEqual(codigo, 0)
        self.assertEqual(self.estados()[-1]['estado'], 'INCERTO')
        self.api.falha_post_depois_de_aplicar = False
        self.assertEqual(self.rodar(MODO='RECONCILIAR')[0], 0)
        self.assertEqual(self.estados()[-1]['estado'], 'CONFIRMADO')
        self.assertEqual([x[0] for x in self.api.posts], ['L001'])

    def test_servidor_indisponivel_interrompe_sem_post(self):
        self.api.falha_get = 503
        codigo, _ = self.rodar(MODO='ENVIAR')
        self.assertEqual(codigo, 3)
        self.assertEqual(len(self.api.posts), 0)
        self.assertEqual(self.estados()[-1]['estado'], 'TRANSITORIO')

    def test_manifesto_repetido_bloqueado_antes_de_consulta(self):
        self.manifesto.write_text('lote_id\nL001\nL001\n')
        codigo, _ = self.rodar(MODO='ENVIAR')
        self.assertEqual(codigo, 2)
        self.assertFalse(self.api.posts)

    def test_ausencia_autorizacao_bloqueia(self):
        codigo, _ = self.rodar(MODO='ENVIAR', AUTORIZACAO_POST='NAO')
        self.assertEqual(codigo, 2)
        self.assertFalse(self.api.posts)

    def test_custo_desconhecido_bloqueia(self):
        codigo, _ = self.rodar(MODO='ENVIAR', CUSTO_ZERO_VALIDADO='')
        self.assertEqual(codigo, 2)
        self.assertFalse(self.api.posts)

    def test_reconciliacao_sem_post_quando_nao_aplicada(self):
        estado = self.raiz / 'estado'
        estado.mkdir()
        (estado / 'estado.jsonl').write_text('{"lote_id":"L001","estado":"INCERTO"}\n')
        codigo, _ = self.rodar(MODO='RECONCILIAR')
        self.assertEqual(codigo, 0)
        self.assertEqual(self.estados()[-1]['estado'], 'INCERTO')
        self.assertFalse(self.api.posts)

    def test_ja_aplicado_com_prova_invalida_bloqueia(self):
        self.api.aplicados.add('L001')
        self.api.prova_invalida = True
        codigo, _ = self.rodar(MODO='ENVIAR')
        self.assertEqual(codigo, 3)
        self.assertFalse(self.api.posts)
        self.assertEqual(self.estados()[-1]['estado'], 'BLOQUEADO')

    def test_jornal_truncado_bloqueia(self):
        estado = self.raiz / 'estado'
        estado.mkdir()
        (estado / 'estado.jsonl').write_text('{"lote_id":"L001"')
        codigo, _ = self.rodar(MODO='ENVIAR')
        self.assertEqual(codigo, 2)
        self.assertFalse(self.api.posts)

    def test_url_http_insegura_bloqueia(self):
        codigo, _ = self.rodar(API_NEGOCIO_URL='http://negocio.test/api')
        self.assertEqual(codigo, 2)
        self.assertFalse(self.api.posts)


if __name__ == '__main__':
    unittest.main(verbosity=2)
