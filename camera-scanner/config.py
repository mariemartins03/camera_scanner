import os

class Config:
    # Scanner
    MAX_THREADS = int(os.getenv("MAX_THREADS", 50))
    SCAN_TIMEOUT = int(os.getenv("SCAN_TIMEOUT", 3))          # segundos por IP (ping/HTTP)
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", 5))            # segundos por chamada de API

    # Caminhos
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
    LOGS_DIR = os.path.join(BASE_DIR, "logs")

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "camera-scanner-dev-key")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Portas HTTP padrão para tentar
    HTTP_PORTS = [80, 8080, 443, 8443]

os.makedirs(Config.EXPORTS_DIR, exist_ok=True)
os.makedirs(Config.LOGS_DIR, exist_ok=True)
