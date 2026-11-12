import os, pathlib, subprocess, tempfile, unittest, hashlib
from textwrap import dedent
SCRIPT = pathlib.Path(__file__).parent / 'script.sh'
MOCK = r'''#!/usr/bin/env python3
import os,sys,json,re,pathlib
args=sys.argv[1:]
out=args[args.index('--output')+1]
url=args[-1]
method='POST' if '--request' in args and args[args.index('--request')+1]=='POST' else 'GET'
root=pathlib.Path(os.environ['MOCK_STATE_DIR']); root.mkdir(exist_ok=True, parents=True)
mt=re.search(r'/contratos/([^/]+)/documentos(?:/([^/]+))?$',url)
mi=re.search(r'/documentos/([^/]+)$',url)
sha=os.environ['MOCK_SHA']
status=500; data={}
if 'interno.test' in url and mi and method=='GET':
  doc=mi.group(1)
  data={'contrato_id':'123','documento_id':doc,'sha256':sha if os.getenv('MOCK_CASE')!='wrong_internal' else '0'*64,'estado':'VALIDADO'}
  status=200
elif 'destino.test' in url and mt:
  id,doc=mt.group(1),mt.group(2)
  if method=='POST':doc=json.loads(args[args.index('--data')+1])['documento_id']
  marker=root/f'{id}-{doc}'
  if method=='GET':
    if os.getenv('MOCK_CASE')=='target_unavailable': status=503
    elif os.getenv('MOCK_CASE')=='unauthorized': status=401
    elif marker.exists():
      status=200
      data={'contrato_id':id,'documento_id':doc,'sha256':sha,'estado':'ASSOCIADO'}
    else: status=404
  else:
    with (root/'post_calls').open('a') as f:f.write(f'{id}-{doc}\n')
    marker.write_text('posted')
    if os.getenv('MOCK_CASE')=='drop_after_post':
      sys.exit(7)
    status=201;data={'accepted':True}
pathlib.Path(out).write_text(json.dumps(data))
print(status,end='')
'''

class TestBatch(unittest.TestCase):
  def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    self.root=pathlib.Path(self.tmp.name)
    self.bin=self.root/'bin';self.bin.mkdir()
    p=self.bin/'curl';p.write_text(MOCK);p.chmod(0o755)
    self.sha=hashlib.sha256(b'pdf').hexdigest()
    self.manifest=self.root/'manifesto.tsv'
    self.manifest.write_text('contrato_id\tdocumento_id\tsha256\n'+'123\tdocA\t'+self.sha+'\n'+'123\tdocB\t'+self.sha+'\n')
    self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
       'MANIFESTO':str(self.manifest),'ESTADO_DIR':str(self.root/'estado'),
       'MOCK_STATE_DIR':str(self.root/'remote'),'MOCK_SHA':self.sha,
       'API_INTERNA_URL':'https://interno.test/api',
       'API_DESTINO_URL':'https://destino.test/api','TOKEN_INTERNO':'redacted',
       'TOKEN_DESTINO':'redacted','CUSTO_ZERO_VALIDADO':'SIM'}
  def tearDown(self):self.tmp.cleanup()
  def run_script(self,**kwargs):
    return subprocess.run(['bash',str(SCRIPT)],text=True,capture_output=True,env={**self.env,**kwargs})
  def posts(self):
    p=self.root/'remote/post_calls'
    return p.read_text().splitlines() if p.exists() else []
  def test_success_resume_multiple_docs_same_contract(self):
    self.assertEqual(self.run_script(LOTE='1').returncode,0)
    self.assertEqual(self.posts(),['123-docA'])
    self.assertEqual(self.run_script(LOTE='1').returncode,0)
    self.assertEqual(self.posts(),['123-docA','123-docB'])
    self.assertEqual(self.run_script(LOTE='250').returncode,0)
    self.assertEqual(self.posts(),['123-docA','123-docB'])
  def test_network_drop_not_retried_without_reconciliation(self):
    a=self.run_script(LOTE='1',MOCK_CASE='drop_after_post')
    self.assertEqual(a.returncode,0,a.stderr)
    self.assertIn('INCERTO',a.stdout)
    self.assertEqual(len(self.posts()),1)
    self.assertEqual(self.run_script(LOTE='1').returncode,0)
    self.assertEqual(len(self.posts()),2) # docB is eligible; docA remains uncertain
    self.assertEqual(self.run_script(LOTE='10',MODO='RECONCILIAR').returncode,0)
    self.assertEqual(len(self.posts()),2)
    self.assertEqual(self.run_script(LOTE='10').returncode,0)
    self.assertEqual(len(self.posts()),2)
  def test_wrong_sha_blocks_post(self):
    r=self.run_script(LOTE='1',MOCK_CASE='wrong_internal')
    self.assertEqual(r.returncode,0,r.stderr)
    self.assertIn('BLOQUEADO',r.stdout)
    self.assertEqual(len(self.posts()),0)
  def test_target_get_error_no_post(self):
    r=self.run_script(LOTE='1',MOCK_CASE='target_unavailable')
    self.assertEqual(r.returncode,3,r.stderr)
    self.assertIn('TRANSITORIO',r.stdout)
    self.assertEqual(len(self.posts()),0)
  def test_unauthorized_blocks_post(self):
    r=self.run_script(LOTE='1',MOCK_CASE='unauthorized')
    self.assertEqual(r.returncode,0,r.stderr)
    self.assertIn('BLOQUEADO',r.stdout)
    self.assertEqual(len(self.posts()),0)
  def test_bad_manifest_rejected_before_post(self):
    self.manifest.write_text('contrato_id\tdocumento_id\tsha256\n123\tbad/id\t'+self.sha+'\n')
    r=self.run_script()
    self.assertEqual(r.returncode,2)
    self.assertEqual(len(self.posts()),0)
  def test_duplicate_manifest_rejected(self):
    with self.manifest.open('a') as f: f.write('123\tdocA\t'+self.sha+'\n')
    r=self.run_script()
    self.assertEqual(r.returncode,2)
    self.assertEqual(len(self.posts()),0)
  def test_unknown_cost_blocked(self):
    r=self.run_script(CUSTO_ZERO_VALIDADO='NAO')
    self.assertEqual(r.returncode,2)
    self.assertEqual(len(self.posts()),0)
if __name__=='__main__': unittest.main(verbosity=2)
