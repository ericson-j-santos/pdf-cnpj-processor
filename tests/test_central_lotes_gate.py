"""Regressão de um check obrigatório sem 'skipped' ou falso N/A."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import central_lotes_escopo as modulo


def git(p: Path, *args: str) -> str:
    result = subprocess.run(['git','-C',str(p),*args],capture_output=True,text=True,timeout=15)
    if result.returncode:
        raise AssertionError('git falhou: '+result.stderr)
    return result.stdout.strip()


class GateDeEscopo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='test-lotes-gate-')
        self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name)
        git(self.raiz,'init','-b','main','-q')
        git(self.raiz,'config','user.name','Validator em fixture')
        git(self.raiz,'config','user.email','fixture@example.invalid')
        (self.raiz/'README.md').write_text('Repositorio de teste sem contratos\n',encoding='utf-8')
        self.commit('baseline')
        self.baseline=git(self.raiz,'rev-parse','HEAD')

    def commit(self,mensagem):
        git(self.raiz,'add','-A')
        git(self.raiz,'commit','-q','-m',mensagem)
        return git(self.raiz,'rev-parse','HEAD')

    def site(self):
        site=self.raiz/modulo.DIR_LOTES
        site.mkdir()
        for item in modulo.OBRIGATORIOS:
            (site/item).write_text(f'fixture: {item}\n',encoding='utf-8')
        return site

    def test_nao_aplicavel_ausencia_comprovada(self):
        self.assertEqual(modulo.decidir(self.raiz,self.baseline,self.baseline),'NAO_APLICAVEL')

    def test_nao_aplicavel_mudanca_fora_do_escopo(self):
        (self.raiz/'README.md').write_text('Mudou apenas README\n')
        sha=self.commit('docs')
        self.assertEqual(modulo.decidir(self.raiz,self.baseline,sha),'NAO_APLICAVEL')

    def test_completo_aplicavel(self):
        self.site()
        head=self.commit('site completo')
        self.assertEqual(modulo.decidir(self.raiz,self.baseline,head),'APLICAVEL')

    def test_replay_sem_nova_mutacao(self):
        self.site()
        head=self.commit('site completo')
        self.assertEqual(modulo.decidir(self.raiz,self.baseline,head),'APLICAVEL')
        self.assertEqual(modulo.decidir(self.raiz,self.baseline,head),'APLICAVEL')
        self.assertEqual(git(self.raiz,'rev-parse','HEAD'),head)

    def test_primeiro_push_branch_com_zero_validado(self):
        self.site()
        head=self.commit('primeiro commit da branch')
        self.assertEqual(modulo.decidir(self.raiz,'0'*40,head,evento='push',criado=True),'APLICAVEL')

    def test_zero_sem_criacao_real_bloqueia(self):
        self.site()
        head=self.commit('mudança')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'SHA anterior zero'):
            modulo.decidir(self.raiz,'0'*40,head,evento='push',criado=False)
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'SHA anterior zero'):
            modulo.decidir(self.raiz,'0'*40,head,evento='pull_request',criado=True)

    def test_remocao_total_bloqueada(self):
        self.site()
        antigo=self.commit('site antes')
        git(self.raiz,'rm','-qr',modulo.DIR_LOTES)
        novo=self.commit('removido')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'Remoção'):
            modulo.decidir(self.raiz,antigo,novo)

    def test_remocao_parcial_bloqueada(self):
        self.site()
        antigo=self.commit('site antes')
        (self.raiz/modulo.DIR_LOTES/'test_core.js').unlink()
        novo=self.commit('teste removido')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'Arquivos obrigatórios'):
            modulo.decidir(self.raiz,antigo,novo)

    def test_pasta_incompleta_bloqueada(self):
        p=self.raiz/modulo.DIR_LOTES
        p.mkdir()
        (p/'index.html').write_text('incompleto')
        novo=self.commit('site parcial')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'Arquivos obrigatórios'):
            modulo.decidir(self.raiz,self.baseline,novo)

    def test_arquivo_nao_reconhecido_apos_remocao_bloqueado(self):
        p=self.raiz/modulo.DIR_LOTES
        p.mkdir()
        (p/'ANOMALIA.txt').write_text('não homologado')
        novo=self.commit('site sem fonte')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'Remoção ou alteração'):
            modulo.decidir(self.raiz,self.baseline,novo)

    def test_sha_base_ausente_bloqueado(self):
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'SHA'):
            modulo.decidir(self.raiz,'',self.baseline)

    def test_checkout_divergente_bloqueado(self):
        git(self.raiz,'checkout','-q','-b','outra')
        (self.raiz/'README.md').write_text('branch outra')
        outro=self.commit('outro')
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'Checkout diverge'):
            modulo.decidir(self.raiz,self.baseline,self.baseline)
        self.assertNotEqual(outro,self.baseline)

    def test_base_nao_ancestral_bloqueada(self):
        git(self.raiz,'checkout','-q','-b','outra')
        (self.raiz/'README.md').write_text('branch outra')
        desvio=self.commit('desvio')
        git(self.raiz,'checkout','-q','main')
        (self.raiz/'README.md').write_text('branch main')
        atual=self.commit('principal')
        self.assertNotEqual(desvio,atual)
        with self.assertRaisesRegex(modulo.EscopoBloqueado,'merge-base'):
            modulo.decidir(self.raiz,desvio,atual)

    def test_cli_saida_negativa(self):
        script=BASE/'scripts'/'central_lotes_escopo.py'
        r=subprocess.run([sys.executable,str(script),'--base','x','--head',self.baseline],cwd=self.raiz,text=True,capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('GATE_BLOQUEADO',r.stderr)

    def test_cli_saida_positiva(self):
        script=BASE/'scripts'/'central_lotes_escopo.py'
        r=subprocess.run([sys.executable,str(script),'--base',self.baseline,'--head',self.baseline],cwd=self.raiz,text=True,capture_output=True)
        self.assertEqual(r.returncode,0)
        self.assertEqual(r.stdout.strip(),'NAO_APLICAVEL')

    def test_ruleset_exige_ambos_checks(self):
        doc=json.loads((BASE/'governanca/pdf-cnpj-main-ruleset-proposta.json').read_text())
        self.assertEqual(doc['target'],'branch')
        self.assertEqual(doc['enforcement'],'active')
        self.assertEqual(doc['bypass_actors'],[])
        self.assertEqual(doc['conditions']['ref_name']['include'],['refs/heads/main'])
        regras={r['type']:r for r in doc['rules']}
        self.assertIn('pull_request',regras)
        self.assertIn('deletion',regras)
        self.assertIn('non_fast_forward',regras)
        status=regras['required_status_checks']['parameters']
        self.assertTrue(status['strict_required_status_checks_policy'])
        checks=status['required_status_checks']
        self.assertEqual({c['context'] for c in checks},{'shell','validar'})
        self.assertTrue(all(c['integration_id']==15368 for c in checks))

    def test_workflow_nao_filtra_pull_request_e_executa_gate(self):
        text=(BASE/'.github/workflows/central-lotes-ci.yml').read_text()
        self.assertIn('  pull_request:\n  merge_group:',text)
        self.assertIn('  validar:',text)
        self.assertIn('python3 scripts/central_lotes_escopo.py',text)
        self.assertIn("REF_CREATED: ${{ github.event.created || 'false' }}",text)
        self.assertIn('--created "$REF_CREATED"',text)
        self.assertIn('STRICT_BROWSER_E2E=1',text)
        self.assertIn('node test_core.js',text)
        self.assertNotIn('    if:',text)
        self.assertIn('set -euo pipefail',text)
        # Evita falso sucesso caso removam o teste de porta HTTP real.
        self.assertIn('python3 -m venv',text)


if __name__=='__main__':
    unittest.main()
