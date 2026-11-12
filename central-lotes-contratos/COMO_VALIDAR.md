# Critérios de aceite técnico

| Gate | Prova verificável | Estado no artefato inicial |
| --- | --- | --- |
| HTML, JavaScript e estilos sincronizados | `python3 -m unittest test_bundle_static -v` | Testado localmente |
| Regras sem duplicação | `node test_core.js` | Testado localmente |
| Preflight positivo e negativos inclusive `python -O` | `python3 -m unittest test_preflight -v` | Testado localmente |
| Código Python e Shell sintaticamente válido | `python3 -m py_compile ...` + `bash -n script.sh` | Testado localmente |
| Interface, exportação, bloqueios | `python3 test_browser.py` | Testado localmente em modo memória |
| Navegador HTTP, persistência após reload | `STRICT_BROWSER_E2E=1 python3 test_browser.py` | Pendente da CI |
| Código remoto e SHA oficial | Commit e arquivos relidos do GitHub | Pendente da publicação |
| Custo incremental zero | Repositório público, runner padrão GitHub | Condição documentada, observar CI |
| Integração com os três servidores e publicação | Homologação real + leitura independente | BLOQUEADO |
| Replay entre dois computadores físicos | Banco durável compartilhado, lease e readback | BLOQUEADO |

**Um teste não executado não conta como aprovado.** A execução no site local
não equivale à operação de contratos nos servidores. Sem prova das integrações,
proibido anunciar 100% funcional.
