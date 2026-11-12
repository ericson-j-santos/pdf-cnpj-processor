from playwright.sync_api import sync_playwright
from pathlib import Path
from urllib.parse import quote
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from functools import partial
from datetime import datetime
import os

ROOT=Path(__file__).resolve().parent
httpd=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT)))
Thread(target=httpd.serve_forever,daemon=True).start()
URI=f'http://127.0.0.1:{httpd.server_port}/index.html'
errors=[]
results=[]

def ok(label,cond=True):
    if not cond: raise AssertionError(label)
    results.append(label)

with sync_playwright() as p:
    chromium_exe='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None
    browser=p.chromium.launch(headless=True,executable_path=chromium_exe,args=['--no-sandbox'])
    context=browser.new_context(accept_downloads=True,viewport={'width':1440,'height':960})
    page=context.new_page()
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    # Em CI a navegação HTTP real é obrigatória. No sandbox local,
    # o modo parcial em memória não prova IndexedDB após reinício.
    e2e_real=os.environ.get('STRICT_BROWSER_E2E') == '1'
    if e2e_real:
        page.goto(URI,wait_until='load',timeout=20000)
    else:
        page.set_content((ROOT/'index.html').read_text(),wait_until='load')
    page.wait_for_timeout(800)
    ok('site abre e navega', page.get_by_text('Operação sob controle.').is_visible())
    ok('estado comprovado inicial zero', page.locator('#k-comprovados').inner_text()=='0')
    ok('sem erros de JavaScript na abertura',not errors)
    page.screenshot(path=str(ROOT/'tela-inicial.png'),full_page=True)
    page.locator('button[data-action="new"]').first.click()
    page.locator('#nl-start').fill('1')
    page.locator('#nl-end').fill('200')
    page.locator('#nl-owner').fill('Operador de homologação')
    page.locator('#nl-origin').fill('Origem de teste')
    page.locator('#nl-target').fill('Destino de teste')
    page.locator('#new-lot-form button[type="submit"]').click()
    page.wait_for_timeout(400)
    ok('lote cadastrado e contagem atualizada', page.locator('#k-cadastrados').inner_text()=='200')
    ok('avanço muda apenas registro', 'REGISTRO' not in page.locator('#flow-current').inner_text())
    ok('persistência de lote', page.locator('#workflow-lot option').count()==2)
    page.locator('#ev-descricao').fill('Registro informativo sem qualquer transferência externa')
    page.locator('#event-form button[type="submit"]').click()
    page.wait_for_timeout(250)
    ok('evento registrado', 'Registro informativo' in page.locator('#evidencias-lote').inner_text())
    page.locator('#q-sucesso').fill('210')
    page.locator('#q-falha').fill('0')
    page.locator('#quantity-form button[type="submit"]').click()
    page.wait_for_timeout(200)
    ok('contagem impossível bloqueada', 'excedem a quantidade' in page.locator('#toast').inner_text())
    page.locator('#q-sucesso').fill('3')
    page.locator('#q-falha').fill('2')
    page.locator('#quantity-form button[type="submit"]').click()
    page.wait_for_timeout(250)
    ok('quantidades declaradas salvas', 'Sucessos informados: 3' in page.locator('#selected-summary').inner_text())
    ok('quantidade informada em memória',page.locator('#k-informados').inner_text()=='3')
    ok('comprovado permanece zero',page.locator('#k-comprovados').inner_text()=='0')
    page.locator('button[data-to="workflow"]').click()
    page.locator('#workflow-lot').select_option(index=1)
    for i,val in {'origem':'200','baixados':'199','conferidos':'199','internos':'199','publicados':'199'}.items():
        page.locator('#rec-'+i).fill(val)
    page.locator('#rec-sha').fill('a'*64)
    page.locator('#reconciliation-form button[type="submit"]').click()
    page.wait_for_timeout(230)
    ok('reconciliação detecta divergência e bloqueia', 'DIVERGENCIA' in page.locator('#rec-resultado').inner_text() and 'BLOQUEADO' in page.locator('#flow-current').inner_text())
    ok('reconciliação não altera publicações comprovadas',page.locator('#k-comprovados').inner_text()=='0')
    page.locator('button[data-to="lotes"]').click()
    page.locator('button[data-action="new"]').last.click()
    page.locator('#nl-start').fill('150')
    page.locator('#nl-end').fill('250')
    page.locator('#nl-owner').fill('Operador')
    page.locator('#nl-origin').fill('Outra origem')
    page.locator('#nl-target').fill('Outro destino')
    page.locator('#new-lot-form button[type="submit"]').click()
    page.wait_for_timeout(200)
    ok('sobreposição bloqueada', 'Sobreposição' in page.locator('#toast').inner_text())
    page.locator('#new-cancel').click()
    page.locator('button[data-to="scripts"]').click()
    page.wait_for_timeout(300)
    ok('script shell aparece', '#!/usr/bin/env bash' in page.locator('#code-edit').input_value())
    page.locator('#hash-script').click()
    page.wait_for_timeout(300)
    ok('hash SHA-256 do shell', 'SHA-256 calculado' in page.locator('#hash-output').inner_text())
    page.locator('button[data-tab="py"]').click()
    ok('script python aparece', 'def verificar' in page.locator('#code-edit').input_value())
    page.locator('button[data-to="audit"]').click()
    with page.expect_download() as d:
        page.locator('#export-json').click()
    download=d.value
    snap=ROOT/'teste-export.json'
    download.save_as(str(snap))
    import json
    obj=json.loads(snap.read_text())
    ok('backup JSON íntegro',len(obj['lotes'])==1 and obj['lotes'][0]['informadosSucesso']==3)
    with page.expect_download() as d:
        page.locator('#export-report').click()
    d.value.save_as(str(ROOT/'teste-relatorio.html'))
    ok('relatório HTML gerado',(ROOT/'teste-relatorio.html').stat().st_size>500)
    page.locator('#link-title').fill('Teste inválido')
    page.locator('#link-url').fill('http://exemplo.com')
    page.locator('#link-form button[type="submit"]').click()
    page.wait_for_timeout(150)
    ok('link não HTTPS bloqueado', 'HTTPS' in page.locator('#toast').inner_text())
    page.locator('button[data-to="overview"]').click()
    page.screenshot(path=str(ROOT/'tela-com-lote.png'),full_page=True)
    ok('sem erros de JavaScript nas interações',not errors)
    if e2e_real:
        page.reload(wait_until='load')
        page.wait_for_timeout(500)
        ok('persistência após reiniciar página por HTTP', page.locator('#k-cadastrados').inner_text()=='200')
        ok('publicação não comprovada após reinício', page.locator('#k-comprovados').inner_text()=='0')
    print('PASS',len(results),'testes de interface:')
    for r in results: print(' -',r)
    if errors: print('ERROS:',errors)
    browser.close()
httpd.shutdown()
