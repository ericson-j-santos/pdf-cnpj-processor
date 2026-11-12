# Fluxo de negócio por ID do lote — migração de contratos (110 mil no legado)

**Estado:** implementação de referência **não homologada**. O contrato de API documentado abaixo é **hipotético**. Não executar POST contra sistemas reais sem leitura do esquema oficial, homologação e autorização específica.

## Substituição da lógica anterior

A rotina anterior associava PDFs individualmente (`contrato_id/documento_id`). A nova rotina tem como unidade de negócio o **ID de lote**, e aplica a sequência fornecida no desenho:

1. Receber `lote_id`.
2. Verificar o lote em `dbo.conte_lote` (a API oficial deverá confirmar consulta real, contagem positiva de contratos e validade do lote).
3. Confirmar **associação 214**.
4. Confirmar **workflow 181**.
5. Confirmar **etapa de origem 501**.
6. Solicitar ao **motor de negócio oficial** a execução da função **`fn_g1865`** (grafia da imagem; confirmar nome e assinatura no sistema).
7. Reconsultar e confirmar **nova etapa de destino**, identificador da operação e resultado da função. A etapa de destino **não é inventada**.

O download, verificação de PDFs e armazenamento interno continuam como fluxo de preparação **separado**, que deverá estar concluído antes da transição efetiva quando as regras corporativas assim exigirem. Este script **não baixa PDF e não faz upload de PDF**.

## Entrada e volume

`lotes.tsv` contém `lote_id` na primeira linha e um ID por linha a seguir. O limite `LIMITE_LOTES=250` significa **até 250 IDs de lote por execução**, não 250 contratos nem 250 PDFs. Um mesmo lote pode conter vários contratos. O universo de 110 mil contratos exige inventário e reconciliação por lote/contrato antes de qualquer migração real.

## Proposta de adaptador API (não confirmada)

É necessário um serviço interno autorizado que realize as consultas transacionais corretas no SQL Server e acione o mecanismo de workflow sem alterar indevidamente dados. Os campos abaixo são um **contrato a homologar**, e não endpoints que já existam:

- `GET /lotes/{lote_id}/transicao`: `{ "lote_id":"LOTE_TESTE_001", "estado":"NAO_APLICADA" }` ou, quando aplicada, `{ "lote_id":"LOTE_TESTE_001", "estado":"APLICADA", "associacao_id":214, "workflow_id":181, "etapa_origem_id":501, "funcao_nome":"fn_g1865", "funcao_executada":true, "etapa_destino_id":777, "registro_id":"RECIBO_TESTE" }`. **777 é só valor de teste**; não se conhece a etapa real.
- `GET /lotes/{lote_id}/contexto`: `{ "lote_id":"LOTE_TESTE_001", "conte_lote": {"encontrado":true,"valido":true,"quantidade_contratos":2}, "associacao_id":214, "workflow_id":181, "etapa_atual_id":501, "funcao_nome":"fn_g1865", "funcao_habilitada":true }`.
- `POST /lotes/{lote_id}/transicao`: aceita lote e IDs de associação/workflow/origem/função. O **backend** deve validar novamente sob bloqueio transacional, chamar a função pela assinatura oficial e gravar o resultado de forma **atômica e idempotente**, respeitando a chave `Idempotency-Key` e evitando execução duplicada.

Esses dados de GET **não autorizam** o POST por si só. O adaptador deve validar se PDFs e contratos do lote estão íntegros, quando isso for uma condição do negócio. O resultado de um POST só é reconhecido depois de GET independente com recibo/etapa de destino e prova de função executada.

## Execução (somente após adaptar os endpoints)

Requisitos: Python 3, Bash, HTTPS com certificado válido, `API_NEGOCIO_URL` e `TOKEN_NEGOCIO` provenientes de configuração/cofre seguro, estado persistido em diretório protegido, mesmo executor para os testes e custo adicional zero confirmado fora do script.

```bash
export API_NEGOCIO_URL="https://integracao-interna.exemplo/api"  # ilustrativo
# TOKEN_NEGOCIO: apenas por cofre/ambiente protegido
export MANIFESTO_LOTES="/caminho/protegido/lotes.tsv"
export ESTADO_DIR="/caminho/persistente/estado-lotes"
LIMITE_LOTES=10 MODO=VALIDAR bash script.sh  # padrão: não faz POST
LIMITE_LOTES=10 MODO=RECONCILIAR bash script.sh  # somente consulta de incertos
```

**POST permanece bloqueado** sem as três condições externas independentes: `AUTORIZACAO_POST=SIM`, `CONTRATO_API_HOMOLOGADO=SIM`, `CUSTO_ZERO_VALIDADO=SIM`. Essas variáveis são barreiras locais e **não comprovam** as respectivas autorizações ou custos. Somente após aprovação real documentada e validação E2E em homologação:

```bash
LIMITE_LOTES=10 MODO=ENVIAR bash script.sh
```

## Segurança, estados e retomada

- `APTO`: comprovou configuração do lote em consultas; não significa transição.
- `CONFIRMADO`: leitura do destino prova etapa nova e resultado, com associação/workflow/função/recibo compatíveis.
- `TRANSITORIO`: falha antes do POST; pode consultar novamente.
- `INCERTO`: POST com resposta perdida/ambígua; não repetir automaticamente, usar `RECONCILIAR`.
- `BLOQUEADO`: consulta/contrato inválido; corrigir causa, sem alterar `estado.jsonl` manualmente.

O `estado.jsonl` é um diário local com gravação confirmada em disco e trava `flock`; preservá-lo com backups. **Não é apropriado para vários computadores concorrentes** ou 110 mil contratos em operação distribuída. Para isso, usar tabela transacional durável com chave única de lote + versão de processo, reserva exclusiva, histórico, idempotência no servidor e retomada após falha.

**Sem Docker. Sem segredos no repositório. Custo incremental máximo R$ 0,00.** Bloquear quando custo/contrato real não estiverem demonstrados.

## Testes e aceite

```bash
bash -n script.sh
python3 -m unittest -v test_fluxo_lotes.py
```

Testes locais simulam as respostas do serviço. Não comprovam a existência dos endpoints, da tabela/colunas, a assinatura de `fn_g1865`, o vínculo entre os PDFs e o lote, a etapa de destino real ou a operação física no SQL Server/sistema.

Antes de operação real, obter evidência do esquema `dbo.conte_lote`, natureza da associação 214, workflow 181, estágio 501, assinatura/efeitos de `fn_g1865`, política da etapa de destino, transação/idempotência, credenciais de menor privilégio e dois cenários de homologação (sucesso e falha) com leitura independente e registro de quantidade de contratos migrados.