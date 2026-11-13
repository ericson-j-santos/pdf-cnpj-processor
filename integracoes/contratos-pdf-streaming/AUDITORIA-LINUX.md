# Auditoria Linux e agenda opcional — contratos PDF

**Estado:** pacote de diagnóstico e planejamento para homologação, não instalado no servidor corporativo. **Não executa downloads, upload, mudança de workflow nem POST.** O sistema de produção permanece bloqueado.

## O que o diagnóstico responde

`auditar-linux.sh` lê condições do **Linux que executa o comando** e mostra:

- versão do Python; carga instantânea de CPU (amostra de `/proc/stat`), memória disponível e percentual de ocupação (`/proc/meminfo`);
- espaço livre no volume indicado, presença de `systemd` e informações **não conclusivas** sobre cgroups v2 na raiz de `/sys/fs/cgroup`;
- opcionalmente, se um servidor da lista autorizada aceita uma conexão **TLS** válida em porta 443; sem acessar endpoints da aplicação nem autenticar usuários;
- `APTO_APENAS_PARA_TESTE_LOCAL` quando as medições locais estão dentro de limites de exemplo, ou `BLOQUEADO` com as causas objetivas.

**Sempre retorna `NAO_HOMOLOGADO` para o ambiente corporativo e mantém os 8 critérios de negócio pendentes (0/8).** Um servidor que tem CPU, memória e disco livres *não* está automaticamente apto para processar 110 mil contratos. Ainda faltam: a autorização da TI, o custo R$0,00 comprovado, os limites e isolamento de CPU/memória/disco do **worker**, rede e APIs homologadas, conta de serviço, certificado e acesso à fila SQL Server compartilhada, idempotência, vínculo lote-PDF, regra `fn_g1865`, testes E2E e aprovação de produção.

## Como a TI pode executar — após admissão do host e pela via corporativa autorizada

O script de entrada do repositório ganhou a opção `auditoria`. Em uma cópia íntegra do projeto em um Linux autorizado:

```bash
bash script-linux.sh auditoria --volume /pasta-de-teste-autorizada --minimo-gib 5
```

Saída resumida **ilustrativa** (não representa medição do seu Linux):

```text
RESULTADO LOCAL: APTO_APENAS_PARA_TESTE_LOCAL
RESULTADO CORPORATIVO: NAO_HOMOLOGADO (0/8 aprovados)
AUTORIZADO PARA BAIXAR/PUBLICAR: NAO
BLOQUEIOS LOCAIS: nenhum na amostra pontual
REDE: NAO_TESTADA
PROXIMA ACAO: TI homologar host, cgroups do worker, APIs, fila, custo e seguranca
```

Para integração com um painel de observabilidade, acrescente `--json`. O JSON é impresso no terminal; nenhum relatório é gravado automaticamente. Se a TI desejar guardar evidências, deve direcionar a saída a armazenamento corporativo autorizado, sanitizar e comprovar a integridade do arquivo. Os limites padrão de 60% de CPU, 75% de memória e 5 GiB disponíveis **são hipóteses conservadoras do piloto**, não limites autorizados pela TI.

### Verificação opcional dos acessos de rede

Por padrão, **não há tráfego de rede**. A TI pode criar fora do repositório público um arquivo JSON sem tokens, por exemplo:

```json
{"servicos":[
  {"nome":"origem","hostname":"origem.exemplo.org","porta":443},
  {"nome":"upload","hostname":"upload.exemplo.org","porta":443}
]}
```

Somente com autorização explícita dos responsáveis pelos sistemas, o operador pode usar `--alvos /configuracao-privada/alvos.json --autorizar-sonda-tls`. O script limita a três alvos, conecta apenas por TLS com verificação de certificado e timeout, não envia GET/POST nem credenciais, e mostra somente os nomes lógicos dos serviços. O resultado `TLS_VALIDO_SEM_VALIDAR_API` comprova **apenas a negociação criptográfica**, não autorização de acesso à API, login, regras de firewall de todos os fluxos ou funcionamento do negócio. Se a CPU estiver acima do limite, nem essa sonda é iniciada.

## Agenda opcional por systemd (inativa)

Arquivos fornecidos:

- `contratos-auditoria.service`: execução somente leitura, conta dedicada `contratos-auditoria`, sem rede (`PrivateNetwork=yes`), privilégios bloqueados, com limites de exemplo sobre o **auditor**, não sobre o processador de contratos: `CPUQuota=20%`, `MemoryMax=256M`, `TasksMax=32`;
- `contratos-auditoria.timer`: dias úteis às **08h no fuso configurado no Linux**, com dispersão de até dez minutos. `Persistent=false` evita executar auditorias acumuladas após períodos desligado.

**Nenhuma agenda foi ativada.** Os caminhos `/opt/contratos-pdf-streaming` e `/var/lib/contratos-piloto`, a conta dedicada e os limites são exemplos que a TI deve adaptar e aprovar. O serviço requer que a TI instale os arquivos e execute suas operações administrativas usuais (por exemplo, disponibilizar a conta, definir as permissões e habilitar o timer). Não solicite `sudo` nem altere permissões para contornar controle. Antes, validar os arquivos com `systemd-analyze verify contratos-auditoria.service contratos-auditoria.timer` e o calendário com `systemd-analyze calendar 'Mon..Fri *-*-* 08:00:00'` em ambiente autorizado. Um teste de agenda no Linux do desenvolvedor não comprova ativação no servidor.

**Recomendação:** agendar apenas a *auditoria* — não o processamento real. Agendar o fluxo de contratos só após a fila persistente SQL, a reserva exclusiva, limites do worker, leitura independente e autorização da publicação. Nenhum relatório é enviado por e-mail automaticamente.

## Prova, rollback e próxima ação

- Escopo de aceite corporativo: 8 critérios, pesos iguais; **0/8 comprovados no destino**.
- Testes locais: testar casos positivos/negativos e no loopback. Testes com TLS real da rede corporativa e verificações do `systemd` corporativo continuam pendentes.
- Rollback: apagar os arquivos da auditoria da cópia DEV se necessário (ou reverter o commit isolado). Como o timer não foi instalado ou ativado, não existe serviço corporativo a desativar.
- Donos: engenharia publica o código e valida testes locais; TI corporativa homologa host, conta e agendamento; DBA homologa fila e SQL; responsáveis pelos sistemas validam endpoints e regras por `lote_id`.
- Evidências devem ser armazenadas em canal privado aprovado, com identidade do host, data, versão, hashes e responsável; **não** gravar nomes de hosts corporativos, certificados, tokens, dados de contratos ou credenciais no GitHub público.
- Prazo: **não estimável** sem capacidade, acessos e homologação da infraestrutura.
- Regras canônicas: `chatgpt-operational-rules` v1.6.21, SHA `58dcd4200f412a866278027ba9e433439a03f3b3`, consultadas em 12/11/2026.
