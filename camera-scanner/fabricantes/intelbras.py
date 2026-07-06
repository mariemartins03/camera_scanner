"""
Módulo Intelbras — HTTP API (Basic/Digest Auth).

As câmeras IP Intelbras utilizam firmware OEM baseado em Dahua,
portanto os endpoints são idênticos. A detecção é feita por
palavras-chave específicas da marca nos cabeçalhos/corpo HTTP.
"""
from __future__ import annotations

import logging
import re

import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

from fabricantes import CameraBase, CameraInfo
from utils import normalize_mac

logger = logging.getLogger(__name__)

_MARKERS = ("intelbras", "vip-", "im3", "im5", "im6", "mhdx", "nvd",
            "vhd", "ivp", "s2120", "s3020", "s4120")

_URL_SYSINFO = "/cgi-bin/magicBox.cgi?action=getSystemInfo"
_URL_NET = "/cgi-bin/configManager.cgi?action=getConfig&name=Network"


class IntelbrasCamera(CameraBase):
    FABRICANTE = "Intelbras"

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
                    logger.debug("Intelbras detectada em %s:%s", ip, porta)
                    return True
            except requests.RequestException:
                continue
        return False

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def get_info(self, ip: str, usuario: str, senha: str) -> CameraInfo:
        base = f"http://{ip}"

        # Intelbras aceita Digest ou Basic dependendo do firmware
        for auth in (HTTPDigestAuth(usuario, senha), HTTPBasicAuth(usuario, senha)):
            modelo, serial = self._get_sysinfo(base, auth)
            if modelo is not None:
                break
        else:
            base = f"http://{ip}:8080"
            for auth in (HTTPDigestAuth(usuario, senha), HTTPBasicAuth(usuario, senha)):
                modelo, serial = self._get_sysinfo(base, auth)
                if modelo is not None:
                    break
            else:
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
    # Helpers (reutilizando lógica compatível com Dahua)
    # ------------------------------------------------------------------
    def _get_sysinfo(self, base: str, auth):
        url = base + _URL_SYSINFO
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code not in (200,):
                return None, None
            data = self._parse_keyvalue(resp.text)
            modelo = data.get("DeviceType") or data.get("deviceType")
            serial = data.get("SerialNo") or data.get("SN")
            return modelo, serial
        except requests.RequestException as e:
            logger.debug("Intelbras sysinfo falhou em %s: %s", base, e)
            return None, None

    def _get_mac(self, base: str, auth) -> str:
        url = base + _URL_NET
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code != 200:
                return ""
            m = re.search(r"PhysicalAddress\s*=\s*([0-9A-Fa-f:.-]{11,17})", resp.text)
            if m:
                return m.group(1).strip()
        except Exception as e:
            logger.debug("Intelbras Network config falhou: %s", e)
        return ""

    @staticmethod
    def _parse_keyvalue(text: str) -> dict:
        result = {}
        for line in text.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
        return result
