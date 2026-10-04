# pdf-cnpj-processor

Processamento de PDFs por **CNPJ**, **tipologia** e **competência**.

## Regra funcional

Para cada CNPJ, cada tipologia é tratada de forma independente. Havendo mais de uma competência/data para a mesma combinação **CNPJ + tipologia**, somente a maior competência é processada.

Fluxo: **CNPJ → tipologia → maior competência → PDFs → partes de até 45 MiB**.

Arquivos de entrada acima de 50 MiB passam por tentativa de compressão Ghostscript antes da concatenação. A saída é validada com `pdfinfo` e Ghostscript e recebe SHA-256 no manifesto.

## Validação

```bash
bash -n rotina_pdfs_cnpj.sh processar_pdfs_cron.sh tests/test_e2e.sh
bash tests/test_e2e.sh
```

O E2E usa dois CNPJs, múltiplas tipologias e competências e verifica que competências antigas não são produzidas.
