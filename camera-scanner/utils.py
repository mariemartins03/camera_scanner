import ipaddress
import socket
import logging
import re
from typing import Generator

logger = logging.getLogger(__name__)


def ip_range(start_ip: str, end_ip: str) -> Generator[str, None, None]:
    """Gera todos os IPs dentro de um intervalo (inclusive)."""
    try:
        start = int(ipaddress.IPv4Address(start_ip))
        end = int(ipaddress.IPv4Address(end_ip))
        if start > end:
            raise ValueError(f"IP inicial ({start_ip}) deve ser menor ou igual ao IP final ({end_ip})")
        for ip_int in range(start, end + 1):
            yield str(ipaddress.IPv4Address(ip_int))
    except ipaddress.AddressValueError as e:
        raise ValueError(f"Endereço IP inválido: {e}") from e


def ip_range_count(start_ip: str, end_ip: str) -> int:
    """Retorna o total de IPs no intervalo."""
    start = int(ipaddress.IPv4Address(start_ip))
    end = int(ipaddress.IPv4Address(end_ip))
    return max(0, end - start + 1)


def is_host_reachable(ip: str, port: int = 80, timeout: float = 2.0) -> bool:
    """Verifica se um host está acessível via TCP na porta informada."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def normalize_mac(mac: str) -> str:
    """Normaliza endereço MAC para o formato XX:XX:XX:XX:XX:XX em maiúsculas."""
    if not mac:
        return ""
    clean = re.sub(r"[^a-fA-F0-9]", "", mac)
    if len(clean) != 12:
        return mac  # retorna como veio se não reconhecer
    return ":".join(clean[i:i+2].upper() for i in range(0, 12, 2))


def parse_csv_ips(conteudo: str) -> list[str]:
    """
    Extrai IPs válidos de um conteúdo CSV.
    Aceita IPs em qualquer coluna; ignora cabeçalhos e valores inválidos.
    Retorna lista sem duplicatas, na ordem de aparição.
    """
    ips: list[str] = []
    vistos: set[str] = set()
    for linha in conteudo.splitlines():
        for campo in linha.split(','):
            campo = campo.strip().strip('"').strip("'")
            try:
                ip = str(ipaddress.IPv4Address(campo))
                if ip not in vistos:
                    vistos.add(ip)
                    ips.append(ip)
            except ipaddress.AddressValueError:
                continue
    return ips


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    """Configura logging para arquivo e console."""
    import os
    from logging.handlers import RotatingFileHandler

    log_file = os.path.join(log_dir, "camera_scanner.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
