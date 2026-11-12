"""Entrada de compatibilidade para a bateria atual de testes por lote.

O processo antigo de associacao individual de PDFs foi substituido por
validacao do lote e transicao de workflow 214/181/501/fn_g1865.
"""
import unittest

if __name__ == "__main__":
    unittest.main(module="test_fluxo_lotes", verbosity=2)
