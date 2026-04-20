#!/usr/bin/with-contenv bashio

echo "Iniciando FocusGuard Add-on..."

# O add-on salva os dados em /data para persistência
export DATA_DIR="/data/focusguard"
mkdir -p $DATA_DIR

# O banco de dados e os tokens ficarão na pasta do Home Assistant (visível pelo Samba)
# para que você possa colocar o credentials.json lá.
export CONFIG_DIR="/config/focusguard"
mkdir -p $CONFIG_DIR

export DATA_DIR="/data/focusguard"
mkdir -p $DATA_DIR

echo "=== Starting FocusGuard Backend ==="

cd /app
exec python3 -u -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info
