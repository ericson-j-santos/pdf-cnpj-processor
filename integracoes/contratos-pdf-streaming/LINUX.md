# Operação preparada para Linux — contratos PDF (somente piloto)

**Situação:** scripts Bash (`.sh`) preparados para Linux, não homologados em servidor corporativo. **Nenhuma transferência de contratos reais, publicação, instalação de serviços ou deploy foi executado.** A camada de controle de carga em Python continua demonstrativa e não está ligada a um worker corporativo.

## Entrada única e comandos permitidos

```bash
# Em diretório de desenvolvimento autorizado, após verificação pelo mecanismo corporativo:
bash script-linux.sh --ajuda
bash script-linux.sh preflight --volume /diretorio/local/autorizado --minimo-gib 5

# Exclusivamente no ambiente de testes, onde sockets 127.0.0.1 são permitidos:
bash script-linux.sh teste-local --confirmar-loopback
```

Atenção: **`/diretorio/local/autorizado` é um exemplo** e deve ser substituído por volume real autorizado. O preflight lê condições locais, não grava arquivos naquele volume e não faz requisições HTTP. O parâmetro `5` GiB é um limiar ilustrativo para um **piloto**, não o espaço necessário para 110 mil PDFs. Ele não prova desempenho do servidor, nem configura cgroups, serviços systemd, firewall ou conexões TLS com sistemas reais.

`preflight-linux.sh` verifica Linux, CPU lógica instalada, memória disponível (`/proc/meminfo`), carga média (`/proc/loadavg`) e chama `preflight_hml.py` para Python, política padrão de certificados TLS e disco livre. **Carga média não é CPU % e não comprova capacidade para processamento.** Saída mantém `NAO_HOMOLOGADO`, `transferencia_autorizada=false` e `publicacao_autorizada=false` mesmo quando os testes locais passam. Ausência de dependência, caminho inválido ou telemetria ausente bloqueiam.

`teste-local` exige confirmação explícita, usa `timeout` (120 s + 5 s para término forçado) e executa apenas testes controlados em `127.0.0.1` com dados fictícios e banco temporário. Os demais comandos — `processar`, `enviar`, `publicar`, `prod`, `upload` — são **bloqueados** mesmo com variáveis que aleguem autorização.

## Integração ao fluxo de negócio

A sequência de produção permanece: inventário autenticado → download HTTPS em blocos → conferência do PDF e SHA-256 → upload interno confirmado → transição oficial por **`lote_id`** → readback independente → checkpoint persistente → encerramento. O identificador do documento não é o ID do lote. O serviço de transição por `dbo.conte_lote`, associação 214, workflow 181, etapa 501 e função `fn_g1865` **não está homologado** e não é chamado pelos scripts desta entrega.

O `script.sh` legado de `integracoes/contratos-pdf-lotes/` **não foi alterado**. Seu uso com `MODO=ENVIAR` não é coberto por este piloto nem autorizado por este documento.

## Proteção corporativa ainda necessária

Antes de qualquer execução real, TI e DBA precisam aprovar servidor **Linux de homologação isolado**, identidade de serviço com menor privilégio, limite de CPU/RAM/processos (por cgroups/systemd aprovados), quota real de disco, limites de rede e requisições, monitoração durante o processamento, políticas de retenção e segredo corporativo. A fila transacional com posse exclusiva e recuperação de falhas deve ficar em banco compartilhado, não em SQLite local. Nenhuma dependência é instalada automaticamente; sem capacidade ou custo adicional R$ 0,00 confirmado, operação bloqueada.

No momento, não há mecanismo aprovado para impedir que o Linux principal execute chamadas diretas de Python sem o dispatcher. Isso será tratado na implementação do worker obrigatório, não em scripts que simulem a proteção.

## Evidência e aceite

- Critérios corporativos da [issue #4](https://github.com/ericson-j-santos/pdf-cnpj-processor/issues/4): **0/8 aceitos**, com pesos iguais.
- Testes `.sh`: sintaxe Bash, leitura local, bloqueio de ações não autorizadas, repetição segura e suíte HTTP local, conforme resultado do ambiente de desenvolvimento.
- Próxima ação: TI corporativa identifica host Linux/HML e recursos disponíveis; responsável da origem/destino entrega contratos oficiais das APIs por canal privado; engenharia cria worker seguro e submete mudanças à governança antes de testes HML.
- Fonte de governança consultada: `chatgpt-operational-rules` versão 1.6.21, `main@58dcd4200f412a866278027ba9e433439a03f3b3` em 12/11/2026.

**Não usar este script em produção.** Não há autorização de deploy, de POST, de mudança de privilégios nem de alteração no ambiente corporativo.
