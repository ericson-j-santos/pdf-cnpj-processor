# Etapa de planejamento para homologação Linux — 110 mil contratos PDF

**Estado:** código de preparação testado localmente, **não instalado em servidor corporativo**. A declaração de que HML está homologada é aceita **somente como premissa de planejamento**; não é recibo autenticado da TI, do banco ou do sistema de negócio. Sem HTTP, SQL, download, upload, POST, publicação ou agendamento de migração.

## Alvo e critérios de aceite deste incremento

- Entrada com manifestos JSON sintéticos de **1–3 IDs de lote**, até **10 documentos** no total, cada um com tamanho declarado de até **8 MiB**, e limite total de **40 MiB**. São **limites de piloto**, não dimensionamento para 110 mil contratos.
- Verificação de esquema `schema_version=1`, IDs estritos, SHA-256 declarado com 64 caracteres, tamanho positivo, campos sem extensões, duplicações e associação ambígua entre lote e contrato.
- Chave idempotente determinística por `lote_id|contrato_id|documento_id|versao`, usando SHA-256. Ela evita nomes diferentes para o **mesmo planejamento**, mas **não** prova que o destino suporta idempotência nem autoriza rePOST.
- Auditoria obrigatória do próprio host Linux **sem sonda de rede**. Amostras fora dos limites propostos bloqueiam o planejamento. CPU 60%, memória 75%, reserva de 5 GiB são referências de teste **não homologadas pela TI**.
- Resultado detalhado em JSON no terminal. A saída não grava arquivo ou contém token. O hash do manifesto demonstra integridade das entradas **lidas no momento**, não autenticidade de quem as enviou.
- Mesmo com a opção `--premissa-hml-declarada`, sempre `homologacao_corporativa_comprovada=false`, `transferencia_autorizada=false`, `publicacao_autorizada=false`, `aprovacoes_hml_comprovadas=0`.

## Execução em Linux autorizado, exclusivamente diagnóstica

A partir de `integracoes/contratos-pdf-streaming`, conferir que o repositório está no SHA exato aprovado, sem trabalho de terceiros, e usar o canal de execução governado da TI. O manifesto de exemplo possui exclusivamente contratos **fictícios**:

```bash
bash script-linux.sh planejar-hml \
  --manifesto manifesto-hml-exemplo.json \
  --volume /volume-de-teste-autorizado \
  --max-documentos 10 \
  --premissa-hml-declarada
```

O caminho deve existir e ser autorizado; não indica diretório real da empresa. Se o host estiver pressionado, o programa retorna `BLOQUEADO` (código 2), não inicia tarefas e não deve ser contornado. A opção `--premissa-hml-declarada` apenas registra a premissa usada, não libera rede ou publicação. `--alvos`, variáveis `AUTORIZACAO_POST=SIM` e outros atalhos **não são aceitos** pelo planejador.

## Etapas da operação completa (não implementadas neste incremento)

1. **Inventário oficial**: confirmar na fonte real cada `lote_id`, contrato, documento, versão e hash **autenticado** e corrigir divergências sem expor dados em GitHub público.
2. **HML física**: comprovar host Linux, perfil de execução, permissões mínimas, CPU, RAM, quotas reais de disco e processos, rede, custos, responsáveis e rollback.
3. **Fila e exclusividade**: SQL Server corporativo ou solução transacional aprovada com chave única, lease/fencing, checkpoint, histórico e recuperação entre hosts.
4. **Transferência**: adaptadores HTTPS autorizados, streaming com limitação de banda e concorrência, PDF analisado por parser e antivírus aprovados, hash e leitura independente do destino.
5. **Publicação separada por lote**: contrato oficial da API de `dbo.conte_lote`, associação 214, workflow 181, etapa 501, função `fn_g1865`, destino real e comprovante — **POST somente após autorização específica** e teste de não duplicidade.
6. **E2E e escala**: iniciar com lote permitido pela TI, conferir impacto nos demais serviços, simular falhas, interrupção e reprocessamento. Expandir gradualmente apenas com métricas de servidor, sem executar 110 mil contratos numa única solicitação.

## Agenda e execução contínua

Manter `contratos-auditoria.timer` como **modelo opcional de auditoria somente leitura**. Não agendar `planejar-hml` ou execução de contratos automaticamente: os manifestos verdadeiros, a fila SQL, quotas, identidade de serviço e gates ainda não existem. O agendamento precisará de autorização própria antes da implantação.

## Provas e limitações

- Ambiente de desenvolvimento isolado: Linux, Python 3.13.5; suíte completa `python3 -B -m unittest -q test_piloto_streaming test_preflight_hml test_controle_carga test_script_linux test_auditar_linux test_planejar_hml`.
- Conjunto de testes no incremento: **96/96 aprovados** (76 anteriores + 20 novos). Sintaxe Bash validada. Os testes que dependem do HTTP usam **somente loopback**, não APIs corporativas.
- Sem homologação física, sem aprovação CI/readback do SHA futuro até que exista execução real e independente.
- Escopo corporativo da issue #4: 8 critérios de mesmo peso; **0/8 comprovados**, 0%. TODO Global: sincronização pendente.
- Custo incremental máximo R$ 0,00; capacidade e preço não comprovados bloqueiam implantação.
- Versão das regras consultada: `chatgpt-operational-rules/main@58dcd4200f412a866278027ba9e433439a03f3b3`, versão 1.6.21, 12/11/2026.
