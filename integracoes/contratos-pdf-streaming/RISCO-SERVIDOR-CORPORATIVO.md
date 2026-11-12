# Risco de sobrecarga no processamento de contratos PDF

**Data-base:** 12/11/2026. **Estado:** análise e reparo no PILOTO LOCAL; **não** foi executado em servidor corporativo, nem aprovado para HML ou PROD.

## Resposta objetiva

Sim: sem limites de concorrência, espaço em disco, taxa de requisições, uso de CPU/memória e controles de banco, um fluxo de ~110 mil contratos pode deixar um servidor corporativo lento ou indisponível. Streaming evita carregar um PDF inteiro na memória, mas **não** limita uso agregado de disco/rede/CPU, não impede arquivos locais acumulados e não garante que a publicação não será duplicada.

## Riscos e medidas necessárias antes do primeiro piloto de HML

| Risco | Consequência | Proteção exigida |
|---|---|---|
| Espaço em disco insuficiente / retenção sem limite | Falha de aplicativos e do sistema | Volume separado, quota real no sistema operacional, reserva de espaço, políticas de retenção autorizadas e alerta |
| Concorrência alta e PDF/OCR pesado | CPU e memória disputadas com outros serviços | Serviço isolado, teto de workers/processos/memória, fila limitada e pausa automática |
| Download e upload sem limite | Rede congestionada, impacto em outras aplicações | Bandwidth e taxa de requisições limitados, janela autorizada |
| SQL Server compartilhado | Bloqueios e aumento da latência | Índices/chaves únicas, transações curtas, conexão limitada, monitoração de waits e DBA |
| POST com resposta ambígua | Duplicação ou estado incorreto | Idempotência no destino + consulta independente, sem retry cego |
| Falhas de PDF/segurança | Arquivos maliciosos, vazamento, corrupção | Parser e antivírus homologados, assinatura/hash, menor privilégio, LGPD |
| Interrupção ou dois executores | Reprocessamento e perda de controle | Checkpoint persistente no banco, lease/fencing, replay sem duplicação |

## Reparação específica nesta branch

O piloto tinha limite de **até 256 MiB por documento**, padrão **8 MiB**, e streaming de **64 KiB por bloco**, mas ainda não protegia o espaço livre do volume na hora da escrita.

A nova função `_verificar_reserva_disco` no `piloto_streaming.py` mede o espaço **antes** de criar o arquivo temporário e **antes** de gravar cada bloco. Ela exige ao menos **1 GiB livre além da escrita prevista**, para o **piloto local apenas**. Se a consulta do disco falhar, ou a reserva não existir, retorna `Bloqueado`, conserva o checkpoint `BLOQUEADO` e impede o upload. Os temporários parciais são removidos pelo fluxo existente.

**Limites desse controle:** trata-se de observação instantânea, não de quota de disco nem reserva exclusiva. Outro processo pode gastar o espaço após a medição; vários PDFs confirmados ainda podem permanecer em disco. Não liberar 110 mil PDFs nem operação distribuída com base apenas neste controle.

## Plano conservador para homologação, sujeito à TI

1. Selecionar **servidor de homologação isolado** ou serviço de baixa prioridade em host corporativo autorizado; não executar sobre o servidor principal sem capacidade e isolamento comprovados.
2. Medir carga de referência e combinar critérios de interrupção com a TI, antes da execução. Exemplos **não homologados**: 1 trabalhador, lote de 5 a 10 contratos de teste, 0 POSTs de negócio, monitoramento de CPU/memória/disco/rede e limites rígidos de saída.
3. Usar quota real de disco e limite de memória/processos do sistema operacional; estabelecer capacidade para pico + temporários + logs + reprocessos e retenção autorizada.
4. Validar em HML com PDF autorizado, erro de rede, corrupção, arquivo grande, disco quase cheio, reinício no meio do upload, leitura independente, concorrência e idempotência. Pausa automática deve bloquear **novas** tarefas e deixar o item em estado seguro.
5. Só ampliar o volume após evidenciar que outros serviços não foram prejudicados. O tamanho médio dos PDFs, a capacidade do host, o limite de API e o tempo total **não são conhecidos**; não estimar duração ou risco numérico com base em suposições.
6. A publicação continua **proibida** até assinatura oficial do contrato de API e da regra por `lote_id`, incluindo `dbo.conte_lote`, associação 214, workflow 181, etapa 501 e `fn_g1865`, com autorização explícita.

## Prova e bloqueios

- **Antes:** testes novos de falta de espaço reprovam na versão antiga (o fluxo não consulta espaço livre).
- **Depois:** 28/28 testes de código e preflight passam no ambiente isolado, incluindo 3 regressões de disco, comparação SHA e ausência de upload em falha.
- **Ambiente:** sandbox Python 3.13.5. **Não comprova** um servidor corporativo nem carga com 110 mil documentos.
- **Regras:** `chatgpt-operational-rules` v1.6.21, `main@58dcd4200f412a866278027ba9e433439a03f3b3`.
- **Aceite corporativo:** 0/8 critérios da [issue #4](https://github.com/ericson-j-santos/pdf-cnpj-processor/issues/4). Sem merge, sem deploy, sem POST.
- **Próximo responsável:** TI corporativa e DBA, para capacidade do servidor, isolamento de disco, quotas, API e janela de homologação; engenharia para adaptar os controles de execução quando essas condições forem homologadas.

