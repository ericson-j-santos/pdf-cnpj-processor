# Preflight corporativo — somente leitura

**Finalidade:** coletar condições técnicas mínimas do host **sem** acessar PDFs, credenciais, APIs, SQL Server ou publicar contratos. Este diagnóstico **não aprova HML** nem a integração dos ~110 mil contratos.

## Onde e como executar

- Somente em host de homologação **explicitamente autorizado pela TI**, via mecanismo de execução corporativo e políticas locais aprovadas. Não executar por acesso remoto improvisado nem usar terminal/GUI como bypass do Gateway.
- Entregar `preflight_hml.py` pelo fluxo interno de software aprovado. Não copiar arquivos reais, senhas, tokens nem endereços privados para GitHub ou relatórios públicos.
- O operador do ambiente autorizado deve informar um volume destinado a arquivos **de teste**. O utilitário consulta apenas espaço livre no volume, versão Python e configuração padrão de verificação TLS. Não executa downloads, upload, DNS, requisições HTTP, comandos de shell nem POST.
- Uso ilustrativo **somente após autorização do host**: `python preflight_hml.py --volume /diretorio/autorizado --minimo-gib 5`. O caminho é um exemplo, não um caminho existente. Em Windows, o responsável deve usar um caminho corporativo autorizado equivalente.
- O valor de 5 GiB é apenas **limite escolhido para um piloto**, não representa dimensionamento necessário para 110 mil contratos.

## Interpretação do resultado

- `checks_locais_aceitos` de `checks_locais_previstos` demonstra apenas três observações locais: Python >=3.10, política padrão de validação de certificado TLS e espaço livre maior que um limiar de piloto.
- `status=NAO_HOMOLOGADO`, `transferencia_autorizada=false`, `publicacao_autorizada=false` e `aprovacoes_corporativas=0/8` permanecem assim mesmo quando os três checks locais passam.
- Confirmar posteriormente, com responsáveis separados, as **oito evidências** da issue #4: APIs e manifesto de origem; segurança/identidade/custo no host; SQL compartilhado/checkpoints; download PDF completo; upload/idempotência/readback; função e regras oficiais por `lote_id`; interrupção/replay em dois hosts; E2E e autorização final.
- Teste de TLS padrão **não testa** a ligação TLS com a API de destino. Espaço livre **não prova** permissão de escrita, throughput, retenção ou capacidade total. Mesmo um retorno 0 do comando **não autoriza** transferências ou publicação.
- Registrar comprovantes apenas em canal corporativo aprovado, com identidade do host, data, hash do artefato, operador, aprovação do dono e correlação de execução; não publicar em repositório público.

## Segurança e reversão

O arquivo não muda configuração, não acessa interfaces corporativas, não altera permissões e não inicia serviços. Não existe mudança de estado a reverter. Se algum resultado for inconclusivo, bloquear a homologação e abrir plano de correção no ambiente proprietário. Custo incremental máximo R$0,00; desconhecido bloqueia.
