"""Testes negativos para impedir execução indevida, inclusive sob Python -O."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from processar_contratos import verificar

RAIZ = Path(__file__).resolve().parent
VALIDO = json.loads((RAIZ / "config.exemplo.json").read_text(encoding="utf-8"))


class PreflightSeguro(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.arquivo = Path(self.temp.name) / "config.json"

    def verificar_execucao(self, dados, sucesso=False, otimizado=False):
        self.arquivo.write_text(dados if isinstance(dados, str) else json.dumps(dados), encoding="utf-8")
        cmd = [sys.executable]
        if otimizado:
            cmd.append("-O")
        cmd.extend([str(RAIZ / "processar_contratos.py"), "--config", str(self.arquivo), "--preflight"])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if sucesso:
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["sem_transferencia"])
        else:
            self.assertNotEqual(proc.returncode, 0, dados)
            self.assertNotIn('"sem_transferencia": true', proc.stdout)

    def test_configuracao_valida(self):
        self.verificar_execucao(VALIDO, sucesso=True)

    def test_configuracao_valida_python_otimizado(self):
        self.verificar_execucao(VALIDO, sucesso=True, otimizado=True)

    def test_configuracao_nao_segura_python_otimizado(self):
        self.verificar_execucao({**VALIDO, "publicacao": "LIBERADA"}, otimizado=True)
        self.verificar_execucao({**VALIDO, "modo": "ENVIAR"}, otimizado=True)

    def test_bloqueios(self):
        casos = [
            {**VALIDO, "limite": 0}, {**VALIDO, "limite": True},
            {**VALIDO, "paralelismo": 5}, {**VALIDO, "retry": -1},
            {**VALIDO, "backoff": 0}, {**VALIDO, "teto": 0},
            {**VALIDO, "dlq": False},
            {k:v for k,v in VALIDO.items() if k != "modo"},
            {**VALIDO, "token": "NAO_PUBLICAR"},
            '{"modo":"DRY_RUN","modo":"ENVIAR"}',
        ]
        for caso in casos:
            with self.subTest(caso=str(caso)[:60]):
                self.verificar_execucao(caso)

    def test_sem_preflight_nega_execucao(self):
        self.arquivo.write_text(json.dumps(VALIDO), encoding="utf-8")
        p = subprocess.run([sys.executable, str(RAIZ / "processar_contratos.py"), "--config", str(self.arquivo)],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("preflight", p.stderr)

    def test_arquivo_inexistente_nega(self):
        with self.assertRaises(OSError):
            verificar(self.arquivo)


if __name__ == "__main__":
    unittest.main()
