"""Testes do entrypoint Bash em Linux. Nenhum servidor corporativo envolvido."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCRIPT = BASE / 'script-linux.sh'
PREFLIGHT = BASE / 'preflight-linux.sh'


class TesteScriptsLinux(unittest.TestCase):
    def rodar(self, *args, env=None):
        e = dict(os.environ)
        if env:
            e.update(env)
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=12, env=e)

    def test_sintaxe_shell(self):
        for path in (SCRIPT, PREFLIGHT):
            p = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_ajuda_nao_executa_nada(self):
        p = self.rodar('--ajuda')
        self.assertEqual(p.returncode, 0)
        self.assertIn('preflight', p.stdout)
        self.assertIn('BLOQUEADOS', p.stdout)

    def test_sem_comando_falha_fechado(self):
        p = self.rodar()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('BLOQUEADO', p.stderr)

    def test_todas_as_acoes_externas_bloqueadas(self):
        for action in ('processar', 'enviar', 'publicar', 'prod', 'upload', 'POST'):
            with self.subTest(action=action):
                p = self.rodar(action, env={
                    'AUTORIZACAO_POST': 'SIM', 'CONTRATO_API_HOMOLOGADO': 'SIM',
                    'CUSTO_ZERO_VALIDADO': 'SIM', 'MODO': 'ENVIAR'})
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('BLOQUEADO', p.stderr)

    def test_piloto_loopback_sem_confirmacao_bloqueado(self):
        p = self.rodar('teste-local')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('BLOQUEADO', p.stderr)

    def test_preflight_favoravel_nao_homologa(self):
        with tempfile.TemporaryDirectory() as volume:
            arquivos_antes = set(Path(volume).iterdir())
            p = self.rodar('preflight', '--volume', volume, '--minimo-gib', '1')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('OBSERVACAO_LINUX', p.stdout)
            dados = json.loads(p.stdout.splitlines()[-1])
            self.assertEqual(dados['status'], 'NAO_HOMOLOGADO')
            self.assertFalse(dados['transferencia_autorizada'])
            self.assertFalse(dados['publicacao_autorizada'])
            self.assertEqual(dados['aprovacoes_corporativas'], 0)
            self.assertEqual(set(Path(volume).iterdir()), arquivos_antes)
            self.assertNotIn(volume, p.stdout)

    def test_preflight_repetido_sem_escrita(self):
        with tempfile.TemporaryDirectory() as volume:
            for _ in range(2):
                p = self.rodar('preflight', '--volume', volume, '--minimo-gib', '1')
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout.splitlines()[-1])['status'], 'NAO_HOMOLOGADO')
            self.assertEqual(list(Path(volume).iterdir()), [])

    def test_preflight_volume_ausente_falha(self):
        p = self.rodar('preflight', '--minimo-gib', '1')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('BLOQUEADO', p.stderr)

    def test_preflight_limite_invalido_falha(self):
        with tempfile.TemporaryDirectory() as volume:
            for val in ('0', '9999', '1.5', '-1', '0001', 'abc'):
                with self.subTest(val=val):
                    p = self.rodar('preflight', '--volume', volume, '--minimo-gib', val)
                    self.assertNotEqual(p.returncode, 0)

    def test_preflight_parametro_desconhecido_bloqueia(self):
        with tempfile.TemporaryDirectory() as volume:
            p = self.rodar('preflight', '--volume', volume, '--executar-post')
            self.assertNotEqual(p.returncode, 0)

    def test_preflight_caminho_inexistente_bloqueia(self):
        with tempfile.TemporaryDirectory() as volume:
            p = self.rodar('preflight', '--volume', str(Path(volume) / 'inexistente'))
            self.assertNotEqual(p.returncode, 0)

    def test_preflight_so_leitura_independente_de_modo(self):
        with tempfile.TemporaryDirectory() as volume:
            p = self.rodar('preflight', '--volume', volume, '--minimo-gib', '1',
                           env={'MODO':'ENVIAR', 'AUTORIZACAO_POST':'SIM'})
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(json.loads(p.stdout.splitlines()[-1])['publicacao_autorizada'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
