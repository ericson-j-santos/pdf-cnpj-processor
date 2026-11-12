# Piloto seguro de streaming de contratos PDF (Python)

**Situação:** prova técnica LOCAL, não homologada e não apta para conexão corporativa. Em 12/11/2026, **nenhum contrato real foi baixado, enviado ou publicado**.

## Objetivo

Comprovar, por HTTP real apenas no loopback `127.0.0.1`, o percurso `download em blocos → conferência de integridade → upload PUT em blocos → GET independente → checkpoint no banco`, sem guardar todo o PDF em memória. Os testes trabalham com dados fictícios de PDF. O fluxo não implementa nem autoriza o **POST de transição** do sistema de negócio.

O identificador de PDF é derivado de contrato + documento + versão. **Não** equivale ao ID de lote de negócio. A transição por lote do projeto existente continua separada e bloqueada, até confirmação oficial de `dbo.conte_lote`, associação `214`, workflow `181`, etapa `501`, função `fn_g1865`, etapa real de destino, identificação de contratos/PDFs e recibo.

## Testar sem servidor externo

Requisito: Python 3.10+ (somente biblioteca padrão), disponível no computador de desenvolvimento autorizado. O teste sobe dois papéis HTTP na memória de um único servidor local, escuta somente em `127.0.0.1` e o desliga automaticamente.

```text
python -m unittest -v test_piloto_streaming.py
python -m py_compile piloto_streaming.py test_piloto_streaming.py
```

Os testes de rede **não simulam funções HTTP**: exercitam sockets locais reais; a lógica do servidor de origem/destino é uma implementação fictícia de teste. Não são provas de integração com serviços corporativos.

## Controles implementados neste piloto

- Apenas endereço `127.0.0.1` com porta explícita; endereços externos, HTTPS corporativo, URLs com credenciais, redirecionamentos e publicação não estão habilitados.
- Download com leitura de até 64 KiB por vez, tamanho máximo permitido configurável e teto absoluto 256 MiB; PDF salvo em arquivo temporário antes de troca atômica.
- Exigência de SHA-256 esperado, que **deve ser obtido de manifesto autenticado**. Checagem mínima de `%PDF-` e `%%EOF` **não valida toda a estrutura, assinatura ou segurança do PDF**.
- Upload PUT em blocos somente para serviço de testes local. A chave de idempotência é derivada de contrato + documento + versão. O destino de testes armazena uma só cópia.
- Estado `INCERTO` gravado **antes** de iniciar o PUT. Se a resposta se perder, uma nova execução consulta o destino, sem reenviar. Se a confirmação não vier, permanece bloqueado.
- SQLite local com transações e restrição de chave única, para comprovar comportamento de reinicialização. Reservas exclusivas falham fechadas; processos interrompidos precisam de reconciliação governada, não de desbloqueio automático.
- Eventos de progresso NDJSON (um objeto JSON por linha) sem conteúdo do PDF, com reconstrução de linhas fragmentadas e recusa de mensagens incompletas ou malformadas.
- Sem Docker, dependências extras, conta externa ou acesso a contratos reais.

## Limites que impedem uso corporativo direto

1. O programa de teste aceita **apenas HTTP local**. Em servidor corporativo, desenvolver outro adaptador com HTTPS/TLS e identidade de serviço, lista de endpoints autorizados e proteção de segredos; não liberar HTTP sem criptografia na rede.
2. A fila SQLite serve para demonstração **em um único computador**. Para 110 mil contratos e várias máquinas, usar banco transacional compartilhado (SQL Server corporativo existente, quando autorizado) com chave única, reserva exclusiva com geração, expiração de posse, checkpoint externo, reprocessamento após falhas e histórico.
3. A conferência completa de PDF exige parser confiável, avaliação antivírus/sandbox permitida, limite de páginas/tamanho, comprovante da origem, identidade do contrato, tipologia, competência e regras de negócio.
4. A API real de upload precisa suportar chave idempotente verificável, upload temporário, confirmação atômica e consulta independente de hash/tamanho/identidade. **PUT 2xx não é comprovante de publicação**.
5. A publicação no sistema de negócios por POST, regra `fn_g1865`, estado de destino e recibo não estão implementados, pois não há contrato oficial homologado.
6. A continuidade entre hosts exige dois computadores físicos autorizados, posse exclusiva, leitura do checkpoint persistido fora do host, replay seguro, readback e testes com queda real.
7. O controle CORS (permissão entre origens do navegador), se necessário, deve autorizar somente origens corporativas específicas; não usar `*` como nos exemplos públicos do vídeo. A tarefa de processamento deve rodar no servidor, não depender do navegador permanecer aberto.
8. A operação exige documentação, mudanças sob PR, gestão de dados conforme LGPD, retenção/backup, observabilidade sem dados pessoais e validação de custo incremental **R$ 0,00**; sem comprovação, bloquear instalação/deploy.

## Caminho de evolução (sem execução real autorizada)

`Inventário por lote e documento → consulta de APIs oficiais → homologação somente leitura → adaptador HTTPS de download → conferência completa → upload idempotente + readback → checkpoint SQL Server → transição oficial por lote → reconciliação independente e replay com dois hosts → implantação autorizada`.

Começar com **um lote de homologação pequeno, com dados desidentificados ou autorizados**. Só aumentar concorrência e tamanho após medir RAM, uso de disco, rede, latência da API, erros e impacto nos servidores. Tamanho médio e limites oficiais dos PDFs ainda são desconhecidos; prazo e capacidade não são estimáveis neste momento.

## Registro de prova

- Data-base: 12/11/2026.
- Testes executados em ambiente isolado (Python 3.11+): **15/15 aprovados**, incluindo download/upload HTTP reais somente na máquina de teste, limite, corrupção, perda de resposta depois da gravação, perda sem gravação, replay sem duplicar, readback adulterado, conflito de versões, exclusividade e NDJSON fragmentado.
- Resultado da execução simulada: nenhum POST de negócio e nenhum serviço externo.
- Regras canônicas consultadas: `ericson-j-santos/chatgpt-operational-rules` versão `1.6.21`, `main@58dcd4200f412a866278027ba9e433439a03f3b3`.
- O código da prova **não** substitui `central-lotes-contratos/processar_contratos.py` nem `integracoes/contratos-pdf-lotes/fluxo_lotes.py`.

## Critérios de aceite corporativo (8 critérios, pesos iguais)

São requisitos, **não entregas aprovadas**: (1) contrato de origem/IDs documentado; (2) segurança e infraestrutura corporativa validadas; (3) fila SQL Server durável; (4) download real com conferência completa; (5) upload real com readback; (6) publicação autorizada por lote e comprovada; (7) replay de falhas sem duplicações e alternância física; (8) operação com evidência de 100% dos testes pertinentes, backup, custo e autorização. **0/8 comprovados no destino corporativo**. Não confundir 15/15 testes do piloto com aprovação corporativa.
