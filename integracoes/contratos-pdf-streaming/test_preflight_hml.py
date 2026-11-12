"""Preflight nao abre portas e nunca publica contratos."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import preflight_hml as alvo


class TestePreflightHML(unittest.TestCase):
    def test_medicoes_favoraveis_nao_aprovam_corporativo(self):
        r = alvo.avaliar_medicoes(versao_python=(3, 13), tls_valido=True,
                                  livre_bytes=7 * 1024**3, minimo_gib=5)
        self.assertEqual(r["checks_locais_aceitos"], 3)
        self.assertEqual(r["status"], "NAO_HOMOLOGADO")
        self.assertEqual(r["aprovacoes_corporativas"], 0)
        self.assertFalse(r["transferencia_autorizada"])
        self.assertFalse(r["publicacao_autorizada"])
        self.assertEqual(len(r["pendencias"]), 8)

    def test_python_antigo_bloqueia(self):
        r = alvo.avaliar_medicoes(versao_python=(3, 9), tls_valido=True,
                                  livre_bytes=20 * 1024**3, minimo_gib=5)
        self.assertFalse(r["checks_locais"]["python_3_10_ou_superior"])

    def test_disco_insuficiente_bloqueia(self):
        r = alvo.avaliar_medicoes(versao_python=(3, 13), tls_valido=True,
                                  livre_bytes=4 * 1024**3, minimo_gib=5)
        self.assertEqual(r["checks_locais_aceitos"], 2)

    def test_tls_inseguro_bloqueia(self):
        r = alvo.avaliar_medicoes(versao_python=(3, 13), tls_valido=False,
                                  livre_bytes=10 * 1024**3, minimo_gib=5)
        self.assertFalse(r["checks_locais"]["tls_validacao_certificado_ativa"])

    def test_valores_booleanos_disfarçados_bloqueiam(self):
        with self.assertRaises(alvo.PreflightBloqueado):
            alvo.avaliar_medicoes(versao_python=(3, 13), tls_valido=True,
                                  livre_bytes=True, minimo_gib=5)
        with self.assertRaises(alvo.PreflightBloqueado):
            alvo.avaliar_medicoes(versao_python=(3, 13), tls_valido=True,
                                  livre_bytes=10000000000, minimo_gib=True)

    def test_volume_inexistente_nao_tenta_rede(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(alvo.shutil, "disk_usage", side_effect=AssertionError("nao deve chamar")):
                with self.assertRaises(alvo.PreflightBloqueado):
                    alvo.observar(Path(pasta) / "inexistente", 5)

    def test_execucao_positiva_sanitizada_sem_endereco_e_sem_credenciais(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(alvo.shutil, "disk_usage", return_value=SimpleNamespace(free=8*1024**3)):
                saida = io.StringIO()
                with contextlib.redirect_stdout(saida):
                    rc = alvo.main(["--volume", pasta, "--minimo-gib", "5"])
                self.assertEqual(rc, 0)
                texto = saida.getvalue()
                self.assertNotIn(pasta, texto)
                r = json.loads(texto)
                self.assertEqual(r["status"], "NAO_HOMOLOGADO")
                self.assertFalse(r["publicacao_autorizada"])

    def test_execucao_negativa_sem_volume_ou_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(alvo.shutil, "disk_usage", return_value=SimpleNamespace(free=2*1024**3)):
                saida = io.StringIO()
                with contextlib.redirect_stdout(saida):
                    rc = alvo.main(["--volume", pasta])
                self.assertEqual(rc, 2)
                self.assertEqual(json.loads(saida.getvalue())["status"], "NAO_HOMOLOGADO")
            with self.assertRaises(alvo.PreflightBloqueado):
                alvo.observar(Path(pasta), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
