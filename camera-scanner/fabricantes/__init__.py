"""
Pacote de fabricantes de câmeras IP.

Cada fabricante implementa CameraBase. O registro FABRICANTES_REGISTRY
mapeia nomes para as classes, permitindo adicionar novos fabricantes
sem alterar o restante da aplicação.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    """Dados retornados após consulta a uma câmera."""
    ip: str
    fabricante: str = "Desconhecido"
    modelo: str = "Desconhecido"
    mac: str = ""
    status: str = "OK"
    erro: str = ""

    # Campos reservados para versões futuras
    firmware: str = ""
    serial: str = ""
    nome: str = ""
    versao: str = ""

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "fabricante": self.fabricante,
            "modelo": self.modelo,
            "mac": self.mac,
            "status": self.status,
            "erro": self.erro,
        }


class CameraBase(ABC):
    """
    Classe base abstrata para todos os fabricantes.

    Subclasses devem implementar:
        - FABRICANTE (atributo de classe)
        - get_info(ip, usuario, senha) -> CameraInfo
        - detectar(ip, timeout) -> bool  [opcional, mas recomendado]
    """

    FABRICANTE: str = "Desconhecido"

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    @abstractmethod
    def get_info(self, ip: str, usuario: str, senha: str) -> CameraInfo:
        """Consulta a API do fabricante e retorna informações da câmera."""

    def detectar(self, ip: str, timeout: int | None = None) -> bool:
        """
        Tenta detectar se o IP pertence a este fabricante.
        Retorna True se detectado, False caso contrário.
        Subclasses devem sobrescrever para implementar detecção real.
        """
        return False

    def _erro(self, ip: str, mensagem: str) -> CameraInfo:
        """Helper para retornar CameraInfo com erro já formatado."""
        logger.warning("[%s] %s — %s", self.FABRICANTE, ip, mensagem)
        return CameraInfo(
            ip=ip,
            fabricante=self.FABRICANTE,
            status="Erro",
            erro=mensagem,
        )


# ---------------------------------------------------------------------------
# Importação das implementações concretas
# ---------------------------------------------------------------------------
from fabricantes.hikvision import HikvisionCamera   # noqa: E402
from fabricantes.dahua import DahuaCamera           # noqa: E402
from fabricantes.intelbras import IntelbrasCamera   # noqa: E402

# Ordem importa: fabricantes mais específicos primeiro
FABRICANTES_REGISTRY: list[type[CameraBase]] = [
    HikvisionCamera,
    DahuaCamera,
    IntelbrasCamera,
]

__all__ = [
    "CameraBase",
    "CameraInfo",
    "FABRICANTES_REGISTRY",
    "HikvisionCamera",
    "DahuaCamera",
    "IntelbrasCamera",
]
