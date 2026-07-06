"""
Módulo de banco de dados (SQLite).

Na versão MVP, apenas a estrutura é definida.
As operações serão ativadas em versões futuras conforme evolução do projeto.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from config import Config

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(Config.BASE_DIR, "camera_scanner.db")

_DDL = """
CREATE TABLE IF NOT EXISTS varreduras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em   TEXT    NOT NULL,
    ip_inicio   TEXT    NOT NULL,
    ip_fim      TEXT    NOT NULL,
    usuario     TEXT    NOT NULL,
    total_ips   INTEGER NOT NULL DEFAULT 0,
    encontradas INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cameras (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    varredura_id INTEGER NOT NULL REFERENCES varreduras(id),
    ip           TEXT NOT NULL,
    fabricante   TEXT,
    modelo       TEXT,
    mac          TEXT,
    status       TEXT,
    erro         TEXT,
    criado_em    TEXT NOT NULL
);
"""


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar() -> None:
    """Cria as tabelas se ainda não existirem."""
    with get_conn() as conn:
        conn.executescript(_DDL)
    logger.info("Banco de dados inicializado: %s", DB_PATH)


# Funções futuras — serão implementadas nas próximas versões:
# salvar_varredura(), salvar_cameras(), listar_historico(), etc.
