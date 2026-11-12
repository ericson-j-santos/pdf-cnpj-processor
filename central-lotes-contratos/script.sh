#!/usr/bin/env bash
set -euo pipefail
# Modelo seguro: só planejamento. Não baixa, envia nem publica PDFs.
# Configure a chamada ao Python num ambiente autorizado.
PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG_FILE="${1:-config.exemplo.json}"
"$PYTHON_BIN" processar_contratos.py --config "$CONFIG_FILE" --preflight
