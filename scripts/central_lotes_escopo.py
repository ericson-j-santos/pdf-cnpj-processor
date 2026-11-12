#!/usr/bin/env python3
"""Decisão fail-closed sobre aplicabilidade dos testes de contratos.

Não executa transferência, publicação, conexão ou operação corporativa.
Uma remoção parcial/total dos fontes obrigatórios nunca é NAO_APLICAVEL.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

OBRIGATORIOS = (
    "index.html", "index.template.html", "app.js", "core.js", "style.css",
    "config.exemplo.json", "processar_contratos.py", "script.sh",
    "test_core.js", "test_browser.py", "test_preflight.py", "test_bundle_static.py",
)
DIR_LOTES = "central-lotes-contratos"


class EscopoBloqueado(ValueError):
    """Falta prova segura de que os testes são dispensáveis."""


def git(raiz: Path, *argumentos: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(raiz), *argumentos], capture_output=True,
        text=True, check=False, timeout=20,
    )
    if r.returncode:
        raise EscopoBloqueado(f"Git não confirmou {argumentos[0]} (código {r.returncode}).")
    return r.stdout.strip()


def decidir(raiz: Path, base: str, head: str, evento: str = "", criado: bool = False) -> str:
    """Retorna APLICAVEL ou NAO_APLICAVEL, ou bloqueia com erro."""
    if base == "0" * 40:
        if evento != "push" or not criado:
            raise EscopoBloqueado("SHA anterior zero sem evento legítimo de criação de branch.")
        # A plataforma informa before=000... para o primeiro push de uma nova branch.
        # Só nesse caso comprovado é permitido comparar com o pai direto do HEAD.
        base = git(raiz, "rev-parse", f"{head}^")
    if not all(re.fullmatch(r"[0-9a-f]{40}", x or "") for x in (base, head)):
        raise EscopoBloqueado("SHA base/head inválido ou não disponível.")
    if git(raiz, "rev-parse", "HEAD") != head:
        raise EscopoBloqueado("Checkout diverge do SHA declarado pela plataforma.")
    # Impede comparação com referências não ancestrais e HEAD arbitrário.
    git(raiz, "merge-base", "--is-ancestor", base, head)
    # Verifica a mudança mesmo quando a pasta foi removida na proposta.
    alteracoes = git(raiz, "diff", "--name-only", base, head, "--", DIR_LOTES + "/")
    pasta = raiz / DIR_LOTES
    presentes = {n for n in OBRIGATORIOS if (pasta / n).is_file()}
    outros = any(pasta.rglob("*")) if pasta.is_dir() else False
    if presentes and len(presentes) != len(OBRIGATORIOS):
        raise EscopoBloqueado("Arquivos obrigatórios ausentes: " + ", ".join(sorted(set(OBRIGATORIOS) - presentes)))
    if not presentes:
        if alteracoes or outros:
            raise EscopoBloqueado("Remoção ou alteração de contratos sem os arquivos de teste: BLOQUEADO.")
        return "NAO_APLICAVEL"
    return "APLICAVEL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Escopo governado do check obrigatório da Central de Lotes")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--event", default="")
    parser.add_argument("--created", choices=("true", "false"), default="false")
    args = parser.parse_args()
    try:
        print(decidir(Path.cwd(), args.base, args.head, evento=args.event, criado=args.created == "true"))
    except EscopoBloqueado as exc:
        print(f"GATE_BLOQUEADO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
