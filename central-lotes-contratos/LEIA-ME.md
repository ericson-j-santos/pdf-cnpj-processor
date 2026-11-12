# Central de Lotes de Contratos Legados — versão 0.1.0 local

## O que está entregue

- `index.html`: site autocontido. Abra em um navegador atual, preferencialmente em uma origem HTTPS/intranet controlada. Não requer instalação, Docker nem rede para apresentar a interface.
- `script.sh` e `processar_contratos.py`: modelos *deliberadamente limitados ao preflight*. **Não** transferem PDFs nem publicam contratos.
- `config.exemplo.json`: parâmetros seguros; modo `DRY_RUN` e publicação bloqueada.
- `core.js`, `app.js`, `style.css`: fontes para manutenção (o HTML já contém uma cópia delas).
- `test_core.js`, `test_browser.py`: verificações reproduzíveis.

## Como usar (sem conhecimentos técnicos)

1. Abra `index.html` em navegador que permita armazenamento local e funções JavaScript. Se o aviso "SEM ARMAZENAMENTO DURÁVEL" aparecer, não confie em continuidade após fechar a página: exporte seu backup JSON.
2. Selecione **Fila de lotes** > **Novo lote** e informe intervalo, nome lógico da origem/destino e responsável. O painel bloqueia sobreposições de contratos.
3. Em **Fluxo operacional**, selecione o lote e registre o que foi observado e seu checkpoint externo. Um registro manual **nunca** vira comprovação de publicação.
4. Em **Scripts e limites**, veja os modelos e calcule a identificação SHA-256 da versão. Você pode salvar a configuração ou baixar os scripts.
5. Em **Auditoria e relatórios**, baixe o backup JSON, a fila CSV e um relatório HTML para copiar ou anexar manualmente ao seu e-mail. **Nenhum e-mail é enviado.**
6. Mantenha uma cópia do backup em armazenamento corporativo autorizado. Não guarde dados pessoais ou credenciais neste painel ou no backup.

## Critério mínimo antes de operar PDFs reais

As seguintes dependências são *bloqueantes*:

- fonte externa e formato/API/documentação autenticada;
- destino interno e contrato de upload idempotente;
- sistema de publicação, suas autorizações e método para detectar duplicações;
- regras de negócio para PDF: integridade SHA-256, quantidade, titularidade, intervalo, tipo e correspondência com contrato;
- banco durável compartilhado, travas de execução e recuperação entre máquinas;
- credenciais com menor privilégio em cofre apropriado e rede HTTPS/TLS;
- evidência independente do sistema de destino, aprovação explícita e teste completo em homologação, incluindo casos negativos, replay e interrupção.

Nenhum desses itens é simulado como comprovado. **O total 110.000 é estimado**, não uma medição da origem.

## Estados, evidências e riscos

- `RASCUNHO`: lote cadastrado, sem execução.
- `REGISTRO_LOCAL`: operador informou andamento, sem verificação externa.
- `BLOQUEADO`: falha ou erro informado; nada deve ser repetido automaticamente.
- `AGUARDANDO_HUMANO`: uma pessoa precisa tomar decisão autorizada.
- `ARQUIVADO`: saída administrativa do painel, sem exclusão de arquivos externos.

O uso de IndexedDB no navegador melhora persistência neste computador, porém **não equivale a checkpoint compartilhado e durável entre computadores**. Se o usuário limpar dados do navegador, os registros podem ser perdidos; exporte cópias. Histórico local não é imutável nem possui autenticação de usuário. Mudanças em modo arquivo podem ter armazenamento restrito conforme a política do navegador.

## Testes disponíveis

- `node test_core.js`: casos positivos e negativos de intervalos, limites, contagens, progressão e impedimento de publicação sem prova.
- `python test_browser.py`: testes de interface com Chromium; se o ambiente restringir navegação, carrega o HTML em memória, portanto não valida o IndexedDB real.
- `bash -n script.sh`: sintaxe shell.
- `python -m py_compile processar_contratos.py`: sintaxe Python.
- `python processar_contratos.py --config config.exemplo.json --preflight`: checagem local positiva.
- Invocar Python sem `--preflight` deve falhar: nenhuma operação real é implementada.

## Regras e ambiente

Regras oficiais lidas em 12/11/2026: `ericson-j-santos/chatgpt-operational-rules` `main` em `58dcd4200f412a866278027ba9e433439a03f3b3`, versão 1.6.21. Este artefato foi montado e testado no contêiner isolado de criação de arquivos; **não** foi instalado no PC24x7 ou nos servidores reais, e **não** foi publicado em URL externa. Integração em ambiente real requer admissão e validação independente.

## Revisão 0.1.1 (GitHub)
Python sem `assert` para controles de segurança, teste de execução `python -O`, checks de integridade HTML↔fontes e CI separada. A integração real dos servidores e a transição por `lote_id` continuam pendentes. Não ativar transferências/POST.
