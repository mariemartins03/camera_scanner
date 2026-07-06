"""
Módulo Dahua — HTTP API (Digest Auth).

Referência: Dahua HTTP API
    GET /cgi-bin/magicBox.cgi?action=getSystemInfo  → modelo, serial
    GET /cgi-bin/configManager.cgi?action=getConfig&name=Network → MAC / IP
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from requests.auth import HTTPDigestAuth

from fabricantes import CameraBase, CameraInfo
from utils import normalize_mac

logger = logging.getLogger(__name__)

_MARKERS = ("dahua", "dh-", "ipc-hd", "ipc-hfw", "ipc-hdw", "sd49", "sd59")

_URL_SYSINFO = "/cgi-bin/magicBox.cgi?action=getSystemInfo"
_URL_NET = "/cgi-bin/configManager.cgi?action=getConfig&name=Network"


class DahuaCamera(CameraBase):
    FABRICANTE = "Dahua"

    # ------------------------------------------------------------------
    # Detecção
    # ------------------------------------------------------------------
    def detectar(self, ip: str, timeout: int | None = None) -> bool:
        t = timeout or self.timeout
        for porta in (80, 8080):
            url = f"http://{ip}:{porta}/"
            try:
                resp = requests.get(url, timeout=t, verify=False, allow_redirects=True)
                text = (resp.text + " ".join(str(v) for v in resp.headers.values())).lower()
                if any(m in text for m in _MARKERS):
                    logger.debug("Dahua detectada em %s:%s", ip, porta)
                    return True
                # Dahua retorna /RPC2 ou /rpc2 quando não autenticado
                if "/rpc2" in text or "dh_" in text:
                    return True
            except requests.RequestException:
                continue
        return False

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def get_info(self, ip: str, usuario: str, senha: str) -> CameraInfo:
        auth = HTTPDigestAuth(usuario, senha)
        base = f"http://{ip}"

        modelo, serial = self._get_sysinfo(base, auth)
        if modelo is None:
            base = f"http://{ip}:8080"
            modelo, serial = self._get_sysinfo(base, auth)
            if modelo is None:
                return self._erro(ip, "API não respondeu ou autenticação falhou")

        mac = self._get_mac(base, auth)

        return CameraInfo(
            ip=ip,
            fabricante=self.FABRICANTE,
            modelo=modelo or "Desconhecido",
            mac=normalize_mac(mac or ""),
            serial=serial or "",
            status="OK",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_sysinfo(self, base: str, auth: HTTPDigestAuth):
        """Retorna (modelo, serial) ou (None, None) em caso de falha."""
        url = base + _URL_SYSINFO
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code == 401:
                raise PermissionError("Autenticação falhou (401)")
            if resp.status_code != 200:
                return None, None
            # Resposta no formato: DeviceType=IPC-HFW...\r\nSN=...\r\n
            data = self._parse_keyvalue(resp.text)
            modelo = data.get("DeviceType") or data.get("deviceType")
            serial = data.get("SerialNo") or data.get("SN")
            return modelo, serial
        except PermissionError:
            raise
        except requests.RequestException as e:
            logger.debug("Dahua sysinfo falhou em %s: %s", base, e)
            return None, None

    def _get_mac(self, base: str, auth: HTTPDigestAuth) -> str:
        url = base + _URL_NET
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code != 200:
                return ""
            # Exemplo: table.Network.eth0.PhysicalAddress=XX:XX:XX:XX:XX:XX
            m = re.search(r"PhysicalAddress\s*=\s*([0-9A-Fa-f:.-]{11,17})", resp.text)
            if m:
                return m.group(1).strip()
        except Exception as e:
            logger.debug("Dahua Network config falhou: %s", e)
        return ""

    @staticmethod
    def _parse_keyvalue(text: str) -> dict:
        """Converte 'Key=Value\r\n' em dicionário."""
        result = {}
        for line in text.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
        return result
