# Validação da entrega — 12/11/2026

## Comprovado

- HTML gerado com CSS e JavaScript embutidos (um único arquivo abrível).
- `node --check` dos fontes JavaScript sem erro.
- 23 verificações positivas/negativas das regras puras passaram.
- 21 verificações de interface no Chromium por carregamento do conteúdo passaram.
- Cálculo SHA-256 do Shell no navegador conferiu exatamente com Python `hashlib`.
- Shell analisado por `bash -n`; Python compilado e preflight local executado.
- Controle negativo: Python sem `--preflight` retorna erro e não executa transferências.
- Exportação JSON e relatório HTML exercitadas; conteúdo lido novamente nos testes.

## Não comprovado / bloqueado

- A política do navegador de testes bloqueou navegação local (`ERR_BLOCKED_BY_ADMINISTRATOR`); foram testadas interações via `page.set_content`, não o endereço `file://` ou HTTP público.
- A persistência real IndexedDB após fechar/reabrir o navegador **não foi testada** nesse ambiente. O código executa gravação e leitura independente quando IndexedDB estiver disponível; até comprovação real, trate como validação parcial.
- Endpoints externos, autenticação, validação de negócios, transferência, publicação final, readback real e retomada entre hosts não foram executados.
- Nenhuma hospedagem pública ou acesso remoto foi validado. Nenhum link público é declarado ativo.
- Custo do arquivo e dos testes no ambiente de execução atual não gerou contratação de serviços pagos; custos de futura hospedagem não foram avaliados nem autorizados.

## Aceite para integração real

Responsáveis: proprietário dos contratos + equipe responsável por origem/destino (interfaces), Engineering Control Plane (testes e governança), Runtime Platform (execução física).

Próxima ação: fornecer documentação dos três sistemas e credenciais por canal seguro; preparar homologação read-only, persistência compartilhada, leitura independente e caso de replay. Só depois pedir autorização expressa para habilitar transferência real, publicação ou deploy.

## Revisão 0.1.1 e limites
Preflight com bloqueios explícitos mesmo em Python -O; E2E externo e persistência HTTP ainda não homologados. Nunca interpretar testes locais como transferência/publicação real.
