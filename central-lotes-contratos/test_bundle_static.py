"""Valida que o HTML entregue contém exatamente os fontes versionados."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
HTML = (RAIZ / "index.html").read_text(encoding="utf-8")


class IntegridadeDoSite(unittest.TestCase):
    def test_documento_portugues_e_sem_codigo_remoto(self):
        self.assertIn('<html lang="pt-BR">', HTML)
        self.assertNotRegex(HTML, r'<script\s+src=')
        self.assertNotRegex(HTML, r'<link\s+[^>]*href=["\x27]https?://')
        self.assertIn('Publicação', HTML)
        self.assertIn('Validação independente', HTML)

    def test_fontes_coincidem_com_html(self):
        css = re.search(r'<style>\s*([\s\S]*?)\s*</style>', HTML)
        scripts = re.findall(r'<script>\s*([\s\S]*?)\s*</script>', HTML)
        sh = re.search(r'<script type="text/plain" id="seed-sh">([\s\S]*?)</script>', HTML)
        py = re.search(r'<script type="text/plain" id="seed-py">([\s\S]*?)</script>', HTML)
        self.assertIsNotNone(css)
        self.assertEqual(len(scripts), 2)
        self.assertIsNotNone(sh)
        self.assertIsNotNone(py)
        for fonte, extraido in [('style.css',css.group(1)), ('core.js',scripts[0]),
                                ('app.js',scripts[1]), ('script.sh',sh.group(1)),
                                ('processar_contratos.py',py.group(1))]:
            with self.subTest(fonte=fonte):
                self.assertEqual((RAIZ / fonte).read_text(encoding='utf-8').strip(), extraido.strip())

    def test_marcadores_de_template_preservados(self):
        modelo=(RAIZ / 'index.template.html').read_text(encoding='utf-8')
        for marcador in ('/*INLINE_CSS*/','/*INLINE_CORE*/','/*INLINE_APP*/'):
            self.assertEqual(modelo.count(marcador),1)
        resultado=modelo.replace('/*INLINE_CSS*/',(RAIZ/'style.css').read_text())
        resultado=resultado.replace('/*INLINE_CORE*/',(RAIZ/'core.js').read_text())
        resultado=resultado.replace('/*INLINE_APP*/',(RAIZ/'app.js').read_text())
        self.assertEqual(resultado,HTML)


if __name__ == '__main__':
    unittest.main()
