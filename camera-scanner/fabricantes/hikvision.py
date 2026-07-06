"""
Módulo Hikvision — ISAPI (HTTP/Digest Auth).

Referência: Hikvision ISAPI 2.0
    GET /ISAPI/System/deviceInfo  → modelo, serial
    GET /ISAPI/System/Network/interfaces → MAC
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Optional

import requests
from requests.auth import HTTPDigestAuth

from fabricantes import CameraBase, CameraInfo
from utils import normalize_mac

logger = logging.getLogger(__name__)

_ISAPI_DEVICE = "/ISAPI/System/deviceInfo"
_ISAPI_NET    = "/ISAPI/System/Network/interfaces"
_ISAPI_CHAN   = "/ISAPI/System/Video/inputs/channels/1"

# Palavras-chave encontradas nos cabeçalhos / corpo de resposta HTTP
_MARKERS = ("hikvision", "hikv", "hik-", "ds-2", "ds-7")


class HikvisionCamera(CameraBase):
    FABRICANTE = "Hikvision"

    # ------------------------------------------------------------------
    # Detecção
    # ------------------------------------------------------------------
    def detectar(self, ip: str, timeout: int | None = None) -> bool:
        t = timeout or self.timeout
        for porta in (80, 8080, 443):
            # Estratégia 1: bate no endpoint ISAPI sem auth — Hikvision devolve 401 Digest
            isapi_url = f"http://{ip}:{porta}{_ISAPI_DEVICE}"
            try:
                resp = requests.get(isapi_url, timeout=t, verify=False, allow_redirects=False)
                if resp.status_code == 401:
                    auth_header = resp.headers.get("WWW-Authenticate", "").lower()
                    if "digest" in auth_header:
                        logger.debug("Hikvision detectada via ISAPI 401 em %s:%s", ip, porta)
                        return True
            except requests.RequestException:
                pass

            # Estratégia 2: verifica markers na página raiz (fallback)
            try:
                resp = requests.get(
                    f"http://{ip}:{porta}/", timeout=t, verify=False, allow_redirects=True
                )
                text = (resp.text + " ".join(str(v) for v in resp.headers.values())).lower()
                if any(m in text for m in _MARKERS):
                    logger.debug("Hikvision detectada via markers em %s:%s", ip, porta)
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

        modelo = self._get_modelo(base, auth)
        if modelo is None:
            # tenta porta 8080
            base = f"http://{ip}:8080"
            modelo = self._get_modelo(base, auth)
            if modelo is None:
                return self._erro(ip, "ISAPI não respondeu ou autenticação falhou")

        mac  = self._get_mac(base, auth)
        nome = self._get_nome(base, auth)

        return CameraInfo(
            ip=ip,
            fabricante=self.FABRICANTE,
            modelo=modelo or "Desconhecido",
            mac=normalize_mac(mac or ""),
            nome=nome or "",
            status="OK",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_modelo(self, base: str, auth: HTTPDigestAuth) -> Optional[str]:
        url = base + _ISAPI_DEVICE
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code == 401:
                raise PermissionError("Autenticação falhou (401)")
            if resp.status_code != 200:
                return None
            return self._xml_text(resp.text, "model") or self._xml_text(resp.text, "deviceName")
        except PermissionError:
            raise
        except requests.RequestException as e:
            logger.debug("Hikvision deviceInfo falhou em %s: %s", base, e)
            return None

    def _get_nome(self, base: str, auth: HTTPDigestAuth) -> str:
        url = base + _ISAPI_CHAN
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code == 200:
                return self._xml_text(resp.text, "name") or ""
        except requests.RequestException as e:
            logger.debug("Hikvision channel name falhou em %s: %s", base, e)
        return ""

    def _get_mac(self, base: str, auth: HTTPDigestAuth) -> str:
        url = base + _ISAPI_NET
        try:
            resp = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
            if resp.status_code != 200:
                return ""
            # Pega o primeiro MAC encontrado
            root = ET.fromstring(resp.text)
            ns = {"h": self._detect_ns(resp.text)}
            for tag in ("macAddress", "MACAddress", "mac"):
                for elem in root.iter():
                    if elem.tag.endswith(tag) and elem.text:
                        return elem.text.strip()
        except Exception as e:
            logger.debug("Hikvision Network interfaces falhou: %s", e)
        return ""

    @staticmethod
    def _xml_text(xml_str: str, tag: str) -> Optional[str]:
        try:
            root = ET.fromstring(xml_str)
            for elem in root.iter():
                if elem.tag.endswith(tag) and elem.text:
                    return elem.text.strip()
        except ET.ParseError:
            pass
        return None

    @staticmethod
    def _detect_ns(xml_str: str) -> str:
        import re
        m = re.search(r'xmlns="([^"]+)"', xml_str)
        return m.group(1) if m else ""
