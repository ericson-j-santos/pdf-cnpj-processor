# Controle de carga do piloto local de contratos PDF

**Tipo:** nova camada de admissão de tarefas (*feature*), isolada e demonstrativa. **Não habilita execução corporativa nem publicação.**

## Risco tratado e mecanismo

O streaming limita memória por arquivo, mas não impede o servidor de iniciar novas transferências quando CPU, memória, disco ou fila já estão pressionados. O módulo `controle_carga.py` inspeciona uma medição recente antes de chamar a função que iniciaria **nova tarefa**; diante de medição ausente, antiga, inválida, falha de sensor ou limite excedido, lança `CargaBloqueada` e **não executa essa função**. As verificações incluem: CPU, memória, percentual de disco ocupado, bytes livres e executores ativos.

`PoliticaCarga` exige que todos os limites sejam informados explicitamente, sem padrões que possam ser confundidos com homologação corporativa. O valor dos exemplos usado nos testes (CPU 65%, memória 75%, disco 85%, 2 GiB livres, 1 executor, medição até 5 segundos) serve **somente ao teste automatizado**. Valores reais precisam ser aprovados pela TI após medir a carga-base.

A coleta local opcional `coletar_carga_local()` utiliza `psutil` quando essa dependência já está disponível/autorizada; se não estiver, falha fechado. A quantidade de executores deve vir de uma fila transacional confiável, que **não existe neste piloto**. Inserir `executores_ativos=0` sem prova independente não autoriza uma execução compartilhada.

## Integração demonstrativa

`executar_com_admissao(politica=..., medidor=..., executar=...)` verifica a carga, depois chama `executar` **uma vez**. A suíte testa esta função com HTTP de origem/destino em `127.0.0.1`: CPU ficticiamente alta bloqueia o GET e o PUT; carga ficticiamente adequada permite o piloto, que continua exigindo GET independente e hash. Medições injetadas em teste **não provam condições reais de servidor**.

O módulo `piloto_streaming.py` **não foi alterado**: seus chamadores legados ainda podem invocar `processar_local` diretamente sem esta camada. Assim, o controle **não está ligado obrigatoriamente** ao fluxo oficial. A integração definitiva exigirá fila/runner corporativo que proíba caminho alternativo e utilize medições autênticas, limites de SO e checkpoints duráveis, após a aprovação de HML.

## O que não protege ainda

- Não interrompe uma tarefa que já começou se a carga piorar durante o download/upload.
- Não impõe cotas reais de CPU, RAM, armazenamento ou largura de banda; medição em tempo discreto pode sofrer corrida.
- Não mede pressão do SQL Server, tempo de resposta de APIs, queue depth nem volumes de produção.
- Não impede chamadas diretas a outros métodos se eles não usarem o wrapper.
- Não coordena dois computadores, reserva/lease com fencing, nem executa publicação.
- Não dimensiona os 110 mil contratos nem comprova compatibilidade com servidor corporativo.

## Validação e próximos critérios

Testes (Python 3.13.5, ambiente isolado): `python -m unittest -v test_controle_carga test_piloto_streaming test_preflight_hml` — 43/43; inclui controles de valores desconhecidos, CPU/memória/disco altos, concorrência, amostras antigas, sensor quebrado e HTTP local com GET/PUT bloqueados ou confirmados. Nenhum contrato real ou sistema corporativo foi usado.

Para HML, obter homologação do host, capacidade/custos, limites de CPU/memória/disco/rede no SO, `psutil` ou telemetria oficial permitida, quota e política de suspensão, limite de executor no banco, testes E2E e autorização específica. Sem prova, manter os oito critérios corporativos da issue #4 em **0/8**. Custo adicional permitido R$0,00; custo desconhecido bloqueia.

Fonte de regras: `ericson-j-santos/chatgpt-operational-rules/main`, versão 1.6.21, SHA `58dcd4200f412a866278027ba9e433439a03f3b3` em 12/11/2026. Sem deploy, sem merge e sem POST de negócio.
