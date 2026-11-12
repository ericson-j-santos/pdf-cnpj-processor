# Integração dos contratos — contrato externo ainda não homologado

**Situação em 12/11/2026: não conectado, sem transferência e sem publicação efetiva.**

Este painel cadastra intervalos **lógicos** de contratos. A branch existente
`feat/pdf-contract-batch-upload-20261111` possui uma rotina separada que opera
por **ID de lote**, com pré-condições de negócio ainda não homologadas.
**Um intervalo numérico do painel não representa automaticamente um ID de lote**.
Não efetuar mapeamento, transição ou POST enquanto essa correspondência não for
comprovada em documentação oficial e homologação.

## Informações necessárias dos responsáveis pelos sistemas

1. **Origem:** identificação do serviço e contrato de acesso; consulta de contratos por lote;
   nomes, tamanho, hashes esperados, acesso autorizado aos PDFs e regras para versões faltantes.
2. **Conferência:** quantidade contratual, identificadores, tipologia, competência,
   associação entre contrato e documento; verificação SHA-256 do arquivo baixado.
3. **Destino interno:** API/serviço de upload, autenticação, nomes e metadados, deduplicação
   por chave de contrato+documento+versão e leitura independente do objeto armazenado.
4. **Sistema de publicação:** assinatura oficial do método de publicar, seus efeitos,
   status, recibo e mecanismo de consulta. A lógica do repositório menciona as condições
   `dbo.conte_lote`, associação 214, workflow 181, etapa 501 e função `fn_g1865`;
   os significados e a assinatura precisam de confirmação oficial.
5. **Segurança:** cofre de credenciais, acesso mínimo, ambiente de homologação,
   restrição de rede/TLS, papéis e proteção de dados (LGPD).

## Contrato de execução antes de operação real

- Chave única global: sistema_origem + contrato + documento + versão de conteúdo.
- Manifesto assinado ou com integridade autenticada; cada PDF conferido por hash SHA-256.
- Fila persistente transacional com reserva exclusiva por lote, geração e expiração da posse.
- Download e upload com transferência para arquivo temporário, validação e confirmação atômica.
- `retry` limitado e backoff; resposta ambígua torna o item **INCERTO**, sem repetição automática
  de publicação. Erro definitivo vai para quarentena (dead-letter queue).
- Ação externa autorizada por lote, idempotência garantida **no servidor de destino** e
  consulta independente comprovando recibo/estado antes de marcar sucesso.
- Checkpoint externo durável fora da máquina, replay em executor diferente sem duplicar efeitos.
- Logs estruturados sanitizados com identificador de correlação, sem PDFs/credenciais/PII.
- Reconciliar inventário de origem, arquivos baixados, arquivos armazenados e registros publicados;
  todas as divergências bloqueiam encerramento até serem resolvidas.
- Testes em homologação: positivo, negativo, corrupção, timeout antes/depois do POST, replay,
  interrupção, concorrência e readback; operação em produção exige autorização específica.

Nada neste documento autoriza POST real, publicação, instalação, deploy ou alterações
nos bancos corporativos. Modelos locais em modo leitura não provam o contrato real.
