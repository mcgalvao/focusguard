#!/usr/bin/with-contenv bashio

echo "=== run.sh iniciado ==="

export CONFIG_DIR="/config/focusguard"
mkdir -p $CONFIG_DIR

export DATA_DIR="/data/focusguard"
mkdir -p $DATA_DIR

cd /app
echo "=== Testando Python ==="
python3 --version 2>&1 || echo "ERRO: python3 nao encontrado"

echo "=== Testando uvicorn ==="
python3 -c "import uvicorn; print('uvicorn OK')" 2>&1 || echo "ERRO: uvicorn nao instalado"

echo "=== Testando imports do backend ==="
python3 -c "from backend.config import AppConfig; print('config OK')" 2>&1 || echo "ERRO: import backend falhou"

echo "=== Iniciando servidor ==="
exec python3 -u -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    2>&1
