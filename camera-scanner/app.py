"""
Aplicação Flask — Camera Scanner.

Endpoints:
    GET  /                → Interface principal
    POST /api/scan        → Inicia varredura (retorna resultados JSON)
    GET  /api/export      → Exporta último resultado para Excel
    GET  /exports/<nome>  → Download de arquivo exportado
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime

from flask import (
    Flask, Response, jsonify, render_template,
    request, send_from_directory, stream_with_context,
)

from config import Config
from database import inicializar
from export import exportar_excel
from fabricantes import CameraInfo
from scanner import varrer, varrer_lista
from utils import ip_range_count, parse_csv_ips, setup_logging

# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
setup_logging(Config.LOGS_DIR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

inicializar()

# Armazenamento em memória dos resultados (substitua por DB nas versões futuras)
_sessoes: dict[str, dict] = {}
_sessoes_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def scan():
    """
    Recebe parâmetros da varredura e retorna Server-Sent Events (SSE)
    para atualizar a interface em tempo real.

    Body JSON:
        ip_inicio, ip_fim, usuario, senha
    """
    data = request.get_json(force=True, silent=True) or {}

    ip_inicio = (data.get("ip_inicio") or "").strip()
    ip_fim = (data.get("ip_fim") or "").strip()
    usuario = (data.get("usuario") or "").strip()
    senha = (data.get("senha") or "")

    # Validações
    erros = []
    if not ip_inicio:
        erros.append("IP inicial é obrigatório")
    if not ip_fim:
        erros.append("IP final é obrigatório")
    if not usuario:
        erros.append("Usuário é obrigatório")
    if not senha:
        erros.append("Senha é obrigatória")

    if erros:
        return jsonify({"erro": "; ".join(erros)}), 400

    try:
        total = ip_range_count(ip_inicio, ip_fim)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400

    if total > 65536:
        return jsonify({"erro": "Intervalo muito grande (máx. 65.536 IPs)"}), 400

    sessao_id = str(uuid.uuid4())

    def _gerar_eventos():
        """Gerador SSE: emite progresso e resultados conforme a varredura avança."""
        resultados: list[CameraInfo] = []
        inicio = time.time()

        def _sse(tipo: str, payload: dict) -> str:
            return f"data: {json.dumps({'tipo': tipo, **payload})}\n\n"

        # Evento inicial
        yield _sse("inicio", {"total": total, "sessao_id": sessao_id})

        def _progresso(concluidos: int, total: int, resultado: CameraInfo | None):
            if resultado is not None:
                resultados.append(resultado)
                yield_result = resultado.to_dict()
            else:
                yield_result = None
            # Não podemos yield dentro de callback — usamos lista compartilhada
            # O streaming é feito logo abaixo no loop principal

        cameras_enviadas = 0

        def _cb(concluidos, total_ips, resultado):
            if resultado is not None:
                resultados.append(resultado)

        # Executa varredura em thread separada para não bloquear o gerador SSE
        scan_thread = threading.Thread(
            target=varrer,
            args=(ip_inicio, ip_fim, usuario, senha),
            kwargs={"progresso_cb": _cb, "max_threads": Config.MAX_THREADS},
            daemon=True,
        )
        scan_thread.start()

        # Polling: emite progresso a cada 0.5s enquanto a thread roda
        processados_enviados = 0
        while scan_thread.is_alive():
            time.sleep(0.4)
            novas = resultados[cameras_enviadas:]
            cameras_enviadas += len(novas)
            concluidos_aprox = cameras_enviadas  # aproximação

            for cam in novas:
                yield _sse("camera", {"camera": cam.to_dict()})

            yield _sse("progresso", {
                "concluidos": concluidos_aprox,
                "total": total,
                "percentual": round(concluidos_aprox / total * 100, 1) if total > 0 else 0,
            })

        # Garante envio de câmeras restantes
        for cam in resultados[cameras_enviadas:]:
            yield _sse("camera", {"camera": cam.to_dict()})

        duracao = round(time.time() - inicio, 1)

        # Salva sessão para exportação posterior
        with _sessoes_lock:
            _sessoes[sessao_id] = {
                "resultados": resultados,
                "criado_em": datetime.now().isoformat(),
                "ip_inicio": ip_inicio,
                "ip_fim": ip_fim,
            }

        yield _sse("fim", {
            "total_ips": total,
            "encontradas": len(resultados),
            "duracao": duracao,
            "sessao_id": sessao_id,
        })

    return Response(
        stream_with_context(_gerar_eventos()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/scan-lista", methods=["POST"])
def scan_lista():
    """
    Recebe um arquivo CSV com IPs + usuário + senha via multipart/form-data
    e retorna Server-Sent Events (SSE) com o progresso da varredura.

    Form fields:
        arquivo  — arquivo CSV com IPs (um por linha ou em colunas)
        usuario  — usuário para autenticação nas câmeras
        senha    — senha para autenticação nas câmeras
    """
    arquivo = request.files.get("arquivo")
    usuario = (request.form.get("usuario") or "").strip()
    senha = request.form.get("senha") or ""

    erros = []
    if not arquivo or arquivo.filename == "":
        erros.append("Arquivo CSV é obrigatório")
    if not usuario:
        erros.append("Usuário é obrigatório")
    if not senha:
        erros.append("Senha é obrigatória")

    if erros:
        return jsonify({"erro": "; ".join(erros)}), 400

    try:
        conteudo = arquivo.read().decode("utf-8", errors="ignore")
    except Exception:
        return jsonify({"erro": "Não foi possível ler o arquivo"}), 400

    ips = parse_csv_ips(conteudo)
    if not ips:
        return jsonify({"erro": "Nenhum IP válido encontrado no arquivo"}), 400

    if len(ips) > 65536:
        return jsonify({"erro": "Arquivo contém mais de 65.536 IPs"}), 400

    sessao_id = str(uuid.uuid4())
    total = len(ips)

    def _gerar_eventos():
        resultados: list[CameraInfo] = []

        def _sse(tipo: str, payload: dict) -> str:
            return f"data: {json.dumps({'tipo': tipo, **payload})}\n\n"

        yield _sse("inicio", {"total": total, "sessao_id": sessao_id})

        cameras_enviadas = 0

        def _cb(concluidos, total_ips, resultado):
            if resultado is not None:
                resultados.append(resultado)

        scan_thread = threading.Thread(
            target=varrer_lista,
            args=(ips, usuario, senha),
            kwargs={"progresso_cb": _cb, "max_threads": Config.MAX_THREADS},
            daemon=True,
        )
        scan_thread.start()

        inicio = time.time()
        while scan_thread.is_alive():
            time.sleep(0.4)
            novas = resultados[cameras_enviadas:]
            cameras_enviadas += len(novas)

            for cam in novas:
                yield _sse("camera", {"camera": cam.to_dict()})

            yield _sse("progresso", {
                "concluidos": cameras_enviadas,
                "total": total,
                "percentual": round(cameras_enviadas / total * 100, 1) if total > 0 else 0,
            })

        for cam in resultados[cameras_enviadas:]:
            yield _sse("camera", {"camera": cam.to_dict()})

        duracao = round(time.time() - inicio, 1)

        with _sessoes_lock:
            _sessoes[sessao_id] = {
                "resultados": resultados,
                "criado_em": datetime.now().isoformat(),
                "ips": ips,
            }

        yield _sse("fim", {
            "total_ips": total,
            "encontradas": len(resultados),
            "duracao": duracao,
            "sessao_id": sessao_id,
        })

    return Response(
        stream_with_context(_gerar_eventos()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/export/<sessao_id>", methods=["GET"])
def exportar(sessao_id: str):
    """Gera e retorna o arquivo Excel da sessão informada."""
    with _sessoes_lock:
        sessao = _sessoes.get(sessao_id)

    if not sessao:
        return jsonify({"erro": "Sessão não encontrada ou expirada"}), 404

    cameras = sessao["resultados"]

    # Reordena pelo arquivo original (CSV) ou por IP numérico (faixa)
    ordem_original = sessao.get("ips")
    if ordem_original:
        indice = {ip: i for i, ip in enumerate(ordem_original)}
        cameras = sorted(cameras, key=lambda c: indice.get(c.ip, len(ordem_original)))
    else:
        import ipaddress
        cameras = sorted(cameras, key=lambda c: int(ipaddress.IPv4Address(c.ip)))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome = f"cameras_{ts}.xlsx"

    caminho = exportar_excel(cameras, nome)
    return send_from_directory(Config.EXPORTS_DIR, nome, as_attachment=True)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"erro": "Recurso não encontrado"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Erro interno: %s", e)
    return jsonify({"erro": "Erro interno do servidor"}), 500


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
