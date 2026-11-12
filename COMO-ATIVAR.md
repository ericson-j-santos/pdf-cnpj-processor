# Proposta de check obrigatório da Central de Lotes — não aplicada

Data-base: 12/11/2026. Repositório: `ericson-j-santos/pdf-cnpj-processor`, público. Regras globais: versão 1.6.21, SHA `58dcd4200f412a866278027ba9e433439a03f3b3`.

## Problema reproduzível

O workflow antigo `.github/workflows/central-lotes-ci.yml` usa `pull_request.paths`: por isso o job `validar` nem sempre ocorre. O ruleset antigo exige somente o job `shell` da CI legada, que não testa o site. `main` permanece `protected=false`, `rulesets=[]` até ativação administrativa.

## Menor correção proposta

1. Em `pull_request` e `merge_group`, emitir o job estável **`validar`** sem filtro de arquivos. O push pode continuar filtrado porque **não** é o check requerido para admissão.
2. Ao receber checkout, verificar SHA de base/HEAD, ancestralidade, arquivos obrigatórios e alterações deletadas. Na primeira criação de branch, `before=000...` só é aceito com evento `push` e `created=true`, utilizando o pai Git comprovado; demais SHAs zero bloqueiam. Sem a Central e sem qualquer alteração nela, declarar **não aplicável com prova Git**; não mascarar arquivo removido.
3. Se o site existir, rodar sintaxe, casos de bloqueio, 44 testes Node, 9 testes Python, navegador HTTP real e persistência. Um erro interrompe o job.
4. Exigir **`shell` e `validar`** no ruleset. O arquivo JSON em `governanca/` é somente proposta declarativa, **não é uma proteção ativa**.
5. CI não protege a própria regra se o autor puder modificar workflows e aprovar a própria PR. A ativação e revisão independente do ruleset, os negativos de enforcement e a decisão de merge são controles adicionais indispensáveis.

## Validação sem produção

- Executar: `python3 -m unittest discover -s tests -p 'test_central_lotes_gate.py' -v`.
- Controles previstos: site íntegro, ausência legítima, retirada de todo o site, retirada parcial de testes, base falsa, HEAD não correspondente, ancestralidade inválida, replay sem efeitos e consistência do JSON/CI.
- No GitHub: obter check `validar` realmente executado no SHA do PR e verificar pela API a presença de regras de `main` com `required_status_checks`. Caso `skipped`, `neutral` ou sem check, bloquear.

## Limites e aprovação

- A proposta preserva `required_approving_review_count=0` do ruleset antigo por não existir comprovação de que há revisor humano independente disponível. **Isso NÃO comprova revisão independente**; a revisão técnica e aprovação do proprietário permanecem gates separados.
- Não usar esta proposta para liberar merge ou deploy; ativação de ruleset é alteração administrativa e exige autorização específica; o estado instalado precisa de readback, negativos de enforcement e gates no SHA atual.
- A integração com três servidores, PDF real, workflow de publicação e checkpoint entre máquinas continua BLOQUEADA.
- Sem Docker, segredos, dados pessoais, POST ou gastos incrementais. O runner padrão do GitHub em repositório público é gratuito conforme documentação oficial; verificar a condição antes de cada operação medida.
