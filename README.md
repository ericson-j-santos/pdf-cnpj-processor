# pdf-cnpj-processor

Processamento governado de PDFs na estrutura real:

```text
ROOT/
└── 20260910/              # competência/data
    └── 15578569000106/    # CNPJ
        ├── 0001000100030021.pdf
        └── 0001000100060008.pdf
```

## Regra funcional

Fluxo: **competência → CNPJ → tipologia extraída do nome → maior competência por CNPJ+tipologia → concatenação → partes de até 45 MiB**.

A posição oficial da tipologia nos 16 dígitos ainda não está comprovada. Por isso o extrator é configurável por `--typology-regex` (ou `TIPOLOGY_REGEX`) e o modo de processamento é **fail-closed**: sem classificação segura, os PDFs são registrados em `falhas.tsv` e nenhuma concatenação é executada.

O teste E2E usa deliberadamente uma regex de fixture para comprovar a arquitetura; ela **não é apresentada como regra de produção**.

## Inventário seguro

```bash
./rotina_pdfs_cnpj.sh --root /pagina/0000/expectativa_fcvs/tmp/fluxo-pj/SAN_INFRA/TRATADO-A --inventory
```

## Processamento

Somente depois de confirmar a regra oficial de tipologia:

```bash
./rotina_pdfs_cnpj.sh --root /dados --all --typology-regex 'REGEX_COM_GRUPO_CAPTURANDO_TIPO'
```

## Validação

```bash
bash -n rotina_pdfs_cnpj.sh processar_pdfs_cron.sh tests/test_e2e.sh
bash tests/test_e2e.sh
```
