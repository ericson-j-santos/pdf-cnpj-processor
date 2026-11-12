# Processamento de PDFs por lotes — modelo de integração

**Estado:** protótipo de integração, **não homologado** contra os servidores reais.

O arquivo `script.sh` implementa **somente a etapa final**: associar documentos já validados e comprovadamente armazenados no servidor interno ao sistema de destino. Não baixa PDFs nem faz upload para o servidor interno. Essas etapas precisam produzir o manifesto de entrada.

## Fluxo completo esperado

1. Inventariar os contratos a importar com identificadores estáveis; registrar o legado sem expor dados pessoais.
2. Baixar o PDF via HTTPS para uma área temporária controlada; confirmar limite de tamanho, tipo PDF, legibilidade/estrutura (`qpdf --check` ou validador equivalente), regras de segurança, contrato correto e SHA-256 da origem, quando disponível.
3. Enviar o arquivo ao servidor interno, usando chave idempotente; ler novamente os metadados/hashes no servidor e registrar `INTERNO_CONFIRMADO`.
4. Criar `manifesto.tsv` com **uma linha por documento validado**, incluindo `contrato_id`, `documento_id` e `sha256` (três campos separados por TAB). O mesmo contrato pode ter vários PDFs.
5. Executar `script.sh` em lotes. Antes do POST, o script consulta o destino e a prova de armazenamento interno. Depois do POST, consulta novamente o destino; somente a associação correta com hash correspondente vira `CONFIRMADO`.
6. Reconciliar as respostas incertas por consulta antes de permitir qualquer repetição. Analisar rejeições, documentar e autorizar correção pontual do registro.

## Contratos de API **hipotéticos** (devem ser adaptados)

- `GET https://<interno>/documentos/{documento_id}` retorna JSON com `contrato_id`, `documento_id`, `sha256`, `estado="VALIDADO"`.
- `GET https://<destino>/contratos/{contrato_id}/documentos/{documento_id}` retorna JSON com `contrato_id`, `documento_id`, `sha256`, `estado="ASSOCIADO"`, ou HTTP 404 quando realmente ausente.
- `POST https://<destino>/contratos/{contrato_id}/documentos` aceita JSON `{"documento_id":"...","sha256":"..."}` e cabeçalho `Idempotency-Key`, cujo comportamento **precisa ser efetivamente suportado pelo servidor**. O destino também deve impedir duplicação por chave única de negócio.

Se a API exigir transferência física do PDF (multipart) em vez de associação por `documento_id`, adaptar o POST sem alterar o estado e os critérios de readback.

## Pré-requisitos

Bash, `curl`, `jq`, `awk`, `flock`, `sha256sum`, manifesto íntegro, disco com persistência, TLS, credenciais de escopo mínimo fornecidas via cofre e **custo incremental de R$ 0,00 comprovado fora do script**. A flag `CUSTO_ZERO_VALIDADO=SIM` é só um bloqueio operacional, não substitui prova financeira.

Exemplo de configuração (substitua URLs; **não coloque tokens em scripts ou no terminal compartilhado**):

```bash
export API_INTERNA_URL="https://interno.exemplo/api"
export API_DESTINO_URL="https://destino.exemplo/api"
# TOKEN_INTERNO e TOKEN_DESTINO: injetar via gerenciador de segredos
export CUSTO_ZERO_VALIDADO="SIM" # apenas quando comprovado
export MANIFESTO="/caminho/protegido/manifesto.tsv"
export ESTADO_DIR="/caminho/persistente/estado"
LOTE=250 MODO=ENVIAR bash script.sh
LOTE=250 MODO=RECONCILIAR bash script.sh  # nao efetua POST
```

**Não execute isso contra sistemas reais sem autorização e homologação**. Por segurança, HTTPS remoto é obrigatório. Nunca desative validação de certificados. As credenciais no ambiente/argumentos de processo requerem gestão de segredos e avaliação de exposição no host.

## Estados

- `CONFIRMADO`: associação presente no sistema de destino com contrato, documento e SHA corretos.
- `TRANSITORIO`: falha de consulta anterior ao POST; pode tentar novamente com segurança na próxima execução.
- `INCERTO`: POST potencialmente aceito sem confirmação final; **não repetir automaticamente**. Executar a reconciliação somente leitura.
- `BLOQUEADO`: dado inválido, hash divergente, erro de autenticação ou rejeição que exige análise/correção.

O controle usa um `estado/estado.tsv` local, mantido sob `flock`. Ele é adequado para **piloto em um executor e um volume moderado**, mas para operação contínua com 110 mil contratos, vários processos ou mais de um host deve ser substituído por uma tabela transacional (por exemplo, SQL Server), com `UNIQUE(contrato_id, documento_id, sha256)`, lease, versão da linha, histórico de tentativas e checkpoint durável. Backup do journal é obrigatório enquanto ele for a fonte de estado.

Recomenda-se iniciar com 10 documentos de teste, depois 100, depois 250, medindo taxa, respostas 429/503, tempo, tamanho, consumo de disco e limites das APIs antes de aumentar. **250 contratos por lote não significa um POST único com 250 PDFs**.

## Testes locais

```bash
bash -n script.sh
python3 test_script.py
```

Os testes usam um cliente HTTP **simulado**: lote de 1, retomada, múltiplos documentos no mesmo contrato, erro de rede após POST, SHA divergente, indisponibilidade, rejeição/autorização, manifesto duplicado e custo desconhecido. Os testes não validam o sistema de destino real.

## Critério de aceite de produção

PDF validado e íntegro na origem; armazenamento interno confirmado por fonte independente; POST com idempotência real; associação persistida no sistema de destino e comprovada por leitura independente (incluindo ID, hash e contrato); tratamento de erro e replay sem duplicidade; teste de rejeição; backup/rollback e custo incremental zero.