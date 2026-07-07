"""
Scanner principal — varredura de rede com multithreading.

Fluxo para cada IP:
    1. Verifica se o host está acessível (TCP em porta conhecida).
    2. Tenta detectar o fabricante consultando cada módulo registrado.
    3. Solicita informações detalhadas ao módulo identificado.
    4. Retorna CameraInfo (com status "Erro" em caso de falha).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterator, Optional

import requests

from config import Config
from fabricantes import FABRICANTES_REGISTRY, CameraBase, CameraInfo
from utils import ip_range, ip_range_count, is_host_reachable

logger = logging.getLogger(__name__)

# Suprime avisos de certificado SSL para câmeras com HTTPS auto-assinado
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Função principal de varredura
# ---------------------------------------------------------------------------

def varrer(
    ip_inicio: str,
    ip_fim: str,
    usuario: str,
    senha: str,
    progresso_cb: Optional[Callable[[int, int, CameraInfo], None]] = None,
    max_threads: int | None = None,
) -> list[CameraInfo]:
    """
    Varre o intervalo de IPs e retorna lista de CameraInfo encontradas.

    Args:
        ip_inicio: IP inicial do intervalo.
        ip_fim:    IP final do intervalo.
        usuario:   Usuário para autenticação nas câmeras.
        senha:     Senha para autenticação nas câmeras.
        progresso_cb: Callback opcional chamado após cada IP processado.
                      Assinatura: (concluidos, total, resultado)
        max_threads: Número máximo de threads simultâneas.

    Returns:
        Lista de CameraInfo (apenas câmeras encontradas e identificadas).
    """
    threads = max_threads or Config.MAX_THREADS
    total = ip_range_count(ip_inicio, ip_fim)

    logger.info(
        "Iniciando varredura: %s → %s (%d IPs, %d threads)",
        ip_inicio, ip_fim, total, threads,
    )

    resultados: list[CameraInfo] = []
    concluidos = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futuros = {
            executor.submit(_processar_ip, ip, usuario, senha): ip
            for ip in ip_range(ip_inicio, ip_fim)
        }

        for futuro in as_completed(futuros):
            ip = futuros[futuro]
            concluidos += 1
            try:
                resultado = futuro.result()
            except Exception as e:
                logger.error("Erro inesperado processando %s: %s", ip, e)
                resultado = CameraInfo(ip=ip, status="Erro", erro=str(e))

            if resultado is not None:
                resultados.append(resultado)

            if progresso_cb:
                progresso_cb(concluidos, total, resultado)

    logger.info(
        "Varredura concluída: %d IPs verificados, %d câmeras identificadas",
        total, len(resultados),
    )
    return resultados


# ---------------------------------------------------------------------------
# Processamento de um único IP
# ---------------------------------------------------------------------------

def varrer_lista(
    ips: list[str],
    usuario: str,
    senha: str,
    progresso_cb: Optional[Callable[[int, int, CameraInfo], None]] = None,
    max_threads: int | None = None,
) -> list[CameraInfo]:
    """
    Varre uma lista arbitrária de IPs e retorna lista de CameraInfo encontradas.
    Mesma lógica de varrer(), mas aceita IPs avulsos em vez de um intervalo contíguo.
    """
    threads = max_threads or Config.MAX_THREADS
    total = len(ips)

    logger.info("Iniciando varredura por lista: %d IPs, %d threads", total, threads)

    resultados: list[CameraInfo] = []
    concluidos = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futuros = {
            executor.submit(_processar_ip, ip, usuario, senha): ip
            for ip in ips
        }

        for futuro in as_completed(futuros):
            ip = futuros[futuro]
            concluidos += 1
            try:
                resultado = futuro.result()
            except Exception as e:
                logger.error("Erro inesperado processando %s: %s", ip, e)
                resultado = CameraInfo(ip=ip, status="Erro", erro=str(e))

            if resultado is not None:
                resultados.append(resultado)

            if progresso_cb:
                progresso_cb(concluidos, total, resultado)

    logger.info(
        "Varredura por lista concluída: %d IPs verificados, %d câmeras identificadas",
        total, len(resultados),
    )
    return resultados


def _processar_ip(ip: str, usuario: str, senha: str) -> Optional[CameraInfo]:
    """
    Processa um único IP: verifica acessibilidade, detecta fabricante,
    consulta API. Retorna None se o host não responder em nenhuma porta.
    """
    # 1. Verificar acessibilidade
    porta_ativa = _encontrar_porta(ip)
    if porta_ativa is None:
        logger.debug("Host inacessível: %s", ip)
        return CameraInfo(ip=ip, status="Offline", erro="Host inacessível")

    logger.info("Host ativo: %s (porta %d)", ip, porta_ativa)

    # 2. Detectar fabricante
    fabricante_cls = _detectar_fabricante(ip)

    if fabricante_cls is None:
        logger.info("Fabricante desconhecido: %s", ip)
        return CameraInfo(ip=ip, status="Desconhecido", erro="Fabricante não identificado")

    # 3. Obter informações
    instancia: CameraBase = fabricante_cls(timeout=Config.API_TIMEOUT)
    try:
        info = instancia.get_info(ip, usuario, senha)
        logger.info("Câmera identificada: %s | %s | %s | MAC: %s",
                    ip, info.fabricante, info.modelo, info.mac)
        return info
    except PermissionError:
        return CameraInfo(
            ip=ip,
            fabricante=fabricante_cls.FABRICANTE,
            status="Erro",
            erro="Autenticação falhou",
        )
    except Exception as e:
        logger.warning("Falha ao consultar %s (%s): %s", ip, fabricante_cls.FABRICANTE, e)
        return CameraInfo(
            ip=ip,
            fabricante=fabricante_cls.FABRICANTE,
            status="Erro",
            erro=str(e),
        )


def _encontrar_porta(ip: str) -> Optional[int]:
    """Testa as portas conhecidas e retorna a primeira que responder."""
    for porta in Config.HTTP_PORTS:
        if is_host_reachable(ip, porta, timeout=Config.SCAN_TIMEOUT):
            return porta
    return None


def _detectar_fabricante(ip: str) -> Optional[type[CameraBase]]:
    """
    Itera o registro de fabricantes e retorna a classe do primeiro
    que reconhecer o IP. Retorna None se nenhum identificar.
    """
    for cls in FABRICANTES_REGISTRY:
        instancia = cls(timeout=Config.SCAN_TIMEOUT)
        try:
            if instancia.detectar(ip):
                return cls
        except Exception as e:
            logger.debug("Erro na detecção de %s em %s: %s", cls.FABRICANTE, ip, e)
    return None
