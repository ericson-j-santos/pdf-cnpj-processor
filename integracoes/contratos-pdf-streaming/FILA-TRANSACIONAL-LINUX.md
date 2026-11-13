# Fila transacional para contratos PDF: Linux + SQL Server

**Data-base: 12/11/2026. Status: implementação de referência em DEV, não implantada em HML/PROD.**

## Resultado técnico

Há dois componentes distintos. `fila_sqlserver.sql` define a estrutura e os procedimentos transacionais para **revisão do administrador de banco (DBA)**, ainda sem implantação. `fila_local.py` utiliza SQLite para testar concorrência e retomada **em um único host Linux**, com o script `fila-linux.sh` disponível pelo `script-linux.sh fila-status`. Este SQLite **não é a fila corporativa compartilhada** e não serve para múltiplos hosts.

A chave estável utiliza **lote_id + contrato_id + documento_id + versão** e deve corresponder ao manifesto autenticado. O `lote_id` não substitui os IDs de contrato/documento. O documento é enfileirado de modo idempotente: inserção repetida idêntica não duplica; hash, tamanho ou lote divergentes bloqueiam. Limite de 8 MiB por PDF e somente um executor ativo são limites **do piloto local, não homologação corporativa**.

### Estados e responsabilidade

```text
PENDENTE -> RESERVADO -> INCERTO_UPLOAD -> CONFIRMADO_UPLOAD
                |                |
             sem efeito       sem readback = BLOQUEAR (sem reenvio)
```

- `RESERVADO`: registro atribuído a token aleatório, geração e expiração de lease. Uma segunda conexão não assume simultaneamente.
- **Antes de qualquer PUT**, persistir `INCERTO_UPLOAD`. Se o processo cair ou perder a resposta HTTP, a fila congela novas reservas até prova independente. **Nunca repetir automaticamente**.
- `CONFIRMADO_UPLOAD`: no piloto SQLite, apenas após GET HTTP real em `127.0.0.1`, com SHA-256 e bytes correspondentes ao destino fictício; no SQL Server, o procedimento recebe campos de readback, mas **não autentica esses campos nem acessa a API**. A aplicação produtiva deverá validar o GET autenticado, recibo e identidade antes de solicitar a confirmação.
- `BLOQUEADO`: disponível como estado reservado no esquema; não existe comando de correção automática ou POST.
- Um lease vencido **não** autoriza outro worker a tomar o mesmo trabalho; isso requer reconciliação governada, prova externa e política aprovada. A fila deliberadamente bloqueia até essa etapa. O modelo **ainda não oferece liberação/reconciliação após timeout**, para não induzir reprocessamento perigoso.

## O que está implementado e o que falta

**Implementado e testável localmente:** exclusividade com transação SQLite, duas conexões simultâneas, chaves idempotentes, bloqueio em conflito, token+geração, checkpoint persistido antes da suposta ação, reinicialização, readback real apenas em loopback, controle negativo de hash alterado, SQL T-SQL versionado e consulta de status via `.sh`.

**Não implementado:** driver corporativo Python para SQL Server, instalação do esquema, `GRANT`/conta corporativa, autenticação do readback externo, fila por múltiplos hosts físicos, backup/restore real, expansão de lease durante transferências longas, reconciliação para liberar `INCERTO`, API corporativa HTTPS para origem/destino e POST de negócio `dbo.conte_lote`/214/181/501/`fn_g1865`. **SQL Server corporativo não foi acessado.** O código é uma base para DBA revisar, não declaração de operação pronta.

## Verificar no Linux autorizado, sem escrever no servidor corporativo

Para rodar testes num checkout isolado sem Docker ou instalação de dependências:

```bash
bash -n fila-linux.sh script-linux.sh
python3 -B -m unittest -v test_fila_local
```

Para consultar **um banco local criado previamente pelos testes**:

```bash
bash script-linux.sh fila-status --banco /caminho/privado/fila-teste.db
```

Nenhum comando acima conecta ao SQL Server da empresa. O status **não cria** banco ausente nem aceita operações de escrita no CLI. Os testes criam e descartam seus bancos temporários. Os scripts `enviar`, `publicar`, `transferir` continuam BLOQUEADOS. Não agendar processamento; agendamento existente contempla apenas a auditoria sem rede.

## Instalação SQL Server: bloqueada até revisão

O arquivo T-SQL `fila_sqlserver.sql` **criaria** tabela, índice e procedimentos se executado. Portanto, **não executá-lo automaticamente**. O DBA deverá validar versão/compatibilidade, bancos e esquemas, índices e locks, tempo de expiração do lease, carga e impacto, isolamento, identidade e permissões mínimas, rollback testado, backup, política de retenção, auditoria de PII, idempotência no destino e a impossibilidade de permitir que um executor vencido faça upload sem token de fencing no destino. SQL Server multi-host não é comprovado por dois processos SQLite locais.

O modelo SQL Server utiliza bloqueios `UPDLOCK`/`HOLDLOCK`, transações `XACT_ABORT`, `sp_getapplock` para reserva única, índice único de documentos, token e geração. **A presença desses comandos no arquivo não é teste funcional do SQL Server**: ainda são necessários testes reais de concorrência, bloqueio, rollback, recuperação de falha e readback E2E em HML.

## Segurança, homologação e próximos passos

- Custo incremental máximo autorizado: **R$ 0,00**; qualquer incerteza bloqueia.
- Regras atuais: `ericson-j-santos/chatgpt-operational-rules/main@58dcd4200f412a866278027ba9e433439a03f3b3` v1.6.21.
- Critérios corporativos: **0/8 comprovados no servidor real**, mesmo com homologação declarada como premissa para planejamento. Nenhum código publicado no GitHub equivale a deploy.
- Donos: Engenharia — modelo e testes; DBA — revisão T-SQL, autorização de banco/backup e instalação HML; TI — host Linux e rede; Sistemas de origem/destino — APIs, manifesto e readback; Negócio — assinatura de função/etapa e autorização de POST.
- Prazo: **não estimável** sem os critérios de segurança e acesso. Não criar agendamento automático de envio nem publicar contratos. TODO Global: sincronização pendente até recibo no destino.

**Próxima ação:** validar `fila_sqlserver.sql` de forma independente em SQL Server de homologação autorizado, testar dois clientes reais, restaurar backup e checar a exclusividade/fencing; então projetar adaptadores HTTPS autenticados e extensão de lease, sem permitir operações enquanto dependerem de confirmações indisponíveis.
