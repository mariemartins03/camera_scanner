# Camera Scanner

Aplicação web para varredura automática de câmeras IP em redes locais. Identifica fabricante, modelo e endereço MAC de câmeras Hikvision, Dahua e Intelbras via suas APIs HTTP nativas.

![Python](https://img.shields.io/badge/Python-3.13+-blue) ![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Funcionalidades

- **Varredura por faixa de IPs** — informe IP inicial e final e a ferramenta varre todo o intervalo
- **Importar lista CSV** — suba um arquivo com os IPs e informe apenas usuário e senha
- **Progresso em tempo real** — atualizações via Server-Sent Events (SSE) sem polling
- **Detecção automática de fabricante** — identifica Hikvision, Dahua e Intelbras
- **Exportação Excel** — exporta os resultados com um clique
- **Multithreading** — até 50 threads simultâneas para varreduras rápidas

---

## Fabricantes suportados

| Fabricante | Protocolo | Autenticação |
|---|---|---|
| Hikvision | ISAPI (HTTP/XML) | Digest |
| Dahua | CGI (HTTP/Key=Value) | Digest |
| Intelbras | CGI compatível Dahua | Digest / Basic |

---

## Requisitos

- Python 3.13+
- Acesso de rede às câmeras (HTTP porta 80, 8080, 443 ou 8443)

---

## Instalação

```bash
git clone https://github.com/mariemartins03/camera_scanner.git
cd camera_scanner/camera-scanner

# Crie e ative o virtualenv
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Instale as dependências
pip install -r requirements.txt
```

---

## Execução

```bash
python app.py
```

Acesse: http://localhost:5000

Para disponibilizar na rede local (outras máquinas acessarem):

```bash
python app.py  # já escuta em 0.0.0.0:5000
```

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `MAX_THREADS` | `50` | Threads simultâneas na varredura |
| `SCAN_TIMEOUT` | `3` | Timeout de conexão TCP (segundos) |
| `API_TIMEOUT` | `5` | Timeout de chamadas à API (segundos) |
| `FLASK_DEBUG` | `false` | Ativa modo debug do Flask |
| `SECRET_KEY` | *(interno)* | **Defina esta variável em produção** |

Exemplo de `.env`:

```env
SECRET_KEY=sua-chave-secreta-aqui
MAX_THREADS=30
SCAN_TIMEOUT=5
```

---

## Formato do CSV

O arquivo pode ter IPs em qualquer coluna — o parser extrai automaticamente:

```
192.168.1.10
192.168.1.25
10.0.0.50
```

Ou com colunas extras:

```
nome,ip,local
Camera 01,192.168.1.10,Recepção
Camera 02,192.168.1.25,Corredor
```

---

## Estrutura do projeto

```
camera-scanner/
├── app.py              # Aplicação Flask (rotas, SSE)
├── config.py           # Configurações centralizadas
├── scanner.py          # Engine de varredura (multithreading)
├── export.py           # Exportação Excel
├── database.py         # Banco SQLite (estrutura reservada)
├── utils.py            # Utilitários (IP range, CSV parser, logging)
├── requirements.txt
├── fabricantes/
│   ├── __init__.py     # CameraBase, CameraInfo, registro
│   ├── hikvision.py
│   ├── dahua.py
│   └── intelbras.py
└── templates/
    └── index.html
```

---

## Adicionando um novo fabricante

1. Crie `fabricantes/novo_fabricante.py`:

```python
from fabricantes import CameraBase, CameraInfo

class NovaMarcaCamera(CameraBase):
    FABRICANTE = "NovaMarca"

    def detectar(self, ip, timeout=None):
        # Consulta um endpoint característico da marca
        return False

    def get_info(self, ip, usuario, senha):
        return CameraInfo(ip=ip, fabricante=self.FABRICANTE, ...)
```

2. Registre em `fabricantes/__init__.py`:

```python
FABRICANTES_REGISTRY = [
    HikvisionCamera,
    DahuaCamera,
    IntelbrasCamera,
    NovaMarcaCamera,  # ← adicione aqui
]
```

Nenhuma outra parte do código precisa ser alterada.

---

## Evoluções planejadas

- [ ] Histórico de varreduras (banco de dados)
- [ ] Campos adicionais: firmware, serial, gateway, máscara, DHCP
- [ ] Dashboard com estatísticas
- [ ] Suporte ONVIF genérico
- [ ] Snapshot e teste de vídeo
- [ ] Docker / Docker Compose
- [ ] API REST documentada (OpenAPI)
