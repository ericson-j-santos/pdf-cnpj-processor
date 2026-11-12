#!/usr/bin/env python3
"""Admissao de NOVAS tarefas do piloto mediante capacidade observada.

Nao envia requisicoes, nao modifica servidor, nao autoriza transferencias
corporativas nem publicacao. A captura real usa psutil se ja autorizado;
sem coletor, politica ou metricas confiaveis, bloqueia (fail-closed).
"""
from __future__ import annotations

import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


class CargaBloqueada(RuntimeError):
    """Falhou verificacao de capacidade; nenhuma nova tarefa pode comecar."""


def _numero(valor: object) -> bool:
    return type(valor) in (int, float) and math.isfinite(valor)


@dataclass(frozen=True)
class PoliticaCarga:
    """Limites fornecidos e aprovados pelo operador; SEM defaults corporativos."""
    cpu_max_percent: float
    memoria_max_percent: float
    disco_max_percent: float
    disco_livre_min_bytes: int
    executores_max: int
    idade_max_segundos: float

    def __post_init__(self):
        for nome in ("cpu_max_percent", "memoria_max_percent", "disco_max_percent"):
            valor = getattr(self, nome)
            if not _numero(valor) or not 0 < valor < 100:
                raise CargaBloqueada("Limite percentual de carga invalido")
        if type(self.disco_livre_min_bytes) is not int or self.disco_livre_min_bytes < 1:
            raise CargaBloqueada("Reserva de disco invalida")
        if type(self.executores_max) is not int or not 1 <= self.executores_max <= 64:
            raise CargaBloqueada("Limite de executores invalido")
        if not _numero(self.idade_max_segundos) or not 0 < self.idade_max_segundos <= 30:
            raise CargaBloqueada("Janela de frescor invalida")


@dataclass(frozen=True)
class MedicaoCarga:
    cpu_percent: float
    memoria_percent: float
    disco_percent: float
    disco_livre_bytes: int
    executores_ativos: int
    coletado_monotonico: float


@dataclass(frozen=True)
class DecisaoCarga:
    nova_tarefa_permitida: bool
    motivos: tuple[str, ...]
    origem: str = "AVALIACAO_LOCAL_NAO_HOMOLOGADA"
    publicacao_autorizada: bool = False
    hml_homologado: bool = False


def avaliar_carga(medicao: MedicaoCarga, politica: PoliticaCarga, *, agora: float) -> DecisaoCarga:
    """Avaliacao pura. Negar em telemetria ausente, antiga ou fora dos limites."""
    if not isinstance(medicao, MedicaoCarga) or not isinstance(politica, PoliticaCarga):
        return DecisaoCarga(False, ("telemetria_ou_politica_ausente",))
    if not _numero(agora) or not _numero(medicao.coletado_monotonico):
        return DecisaoCarga(False, ("tempo_desconhecido",))
    idade = agora - medicao.coletado_monotonico
    if idade < 0 or idade > politica.idade_max_segundos:
        return DecisaoCarga(False, ("telemetria_desatualizada",))
    percentuais = (medicao.cpu_percent, medicao.memoria_percent, medicao.disco_percent)
    if any(not _numero(v) or not 0 <= v <= 100 for v in percentuais):
        return DecisaoCarga(False, ("percentual_desconhecido",))
    if (type(medicao.disco_livre_bytes) is not int or medicao.disco_livre_bytes < 0 or
            type(medicao.executores_ativos) is not int or medicao.executores_ativos < 0):
        return DecisaoCarga(False, ("medicao_invalida",))
    motivos = []
    if medicao.cpu_percent > politica.cpu_max_percent:
        motivos.append("cpu_acima_do_limite")
    if medicao.memoria_percent > politica.memoria_max_percent:
        motivos.append("memoria_acima_do_limite")
    if medicao.disco_percent > politica.disco_max_percent:
        motivos.append("disco_acima_do_limite")
    if medicao.disco_livre_bytes < politica.disco_livre_min_bytes:
        motivos.append("disco_livre_abaixo_do_minimo")
    if medicao.executores_ativos >= politica.executores_max:
        motivos.append("limite_de_executores_atingido")
    return DecisaoCarga(not motivos, tuple(motivos))


def coletar_carga_local(volume: Path, *, executores_ativos: int) -> MedicaoCarga:
    """Somente leitura. Falha sem psutil; nao infere posse pelo host.

    A quantidade de executores DEVE vir da fila transacional confiavel;
    passar um numero arbitrario nao comprova exclusividade corporativa.
    """
    if type(executores_ativos) is not int or executores_ativos < 0 or not volume.is_dir():
        raise CargaBloqueada("Fonte de execucoes ou volume invalido")
    try:
        import psutil  # dependencia externa opcional; sem ela a execucao e recusada
        cpu = psutil.cpu_percent(interval=0.1)
        memoria = psutil.virtual_memory().percent
        disco = shutil.disk_usage(volume)
        disco_pct = 100.0 * (disco.total - disco.free) / disco.total
    except (ImportError, OSError, AttributeError, ZeroDivisionError) as exc:
        raise CargaBloqueada("Telemetria do servidor indisponivel") from exc
    return MedicaoCarga(cpu, memoria, disco_pct, disco.free,
                        executores_ativos, time.monotonic())


def executar_com_admissao(
    *, politica: PoliticaCarga, medidor: Callable[[], MedicaoCarga],
    executar: Callable[[], T]
) -> T:
    """Apenas NOVO trabalho usa esta protecao; sem medidor, nao executa.

    Nao substitui quotas de SO, limites de rede, checkpoint externo nem
    verificacoes durante tarefas ja iniciadas. Nao habilita POST corporativo.
    """
    if not isinstance(politica, PoliticaCarga) or not callable(medidor) or not callable(executar):
        raise CargaBloqueada("Politica, medidor e executor autorizados sao obrigatorios")
    try:
        medicao = medidor()
    except Exception as exc:
        raise CargaBloqueada("Falha ao obter telemetria; nenhuma tarefa iniciada") from exc
    decisao = avaliar_carga(medicao, politica, agora=time.monotonic())
    if not decisao.nova_tarefa_permitida:
        raise CargaBloqueada("Nova tarefa pausada: " + ",".join(decisao.motivos))
    return executar()
