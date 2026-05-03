#!/bin/bash
# Trading Terminal Chile
# El cron ya corre automáticamente en background.
# Este script solo abre el dashboard para monitorear.

TRADING_DIR="/Users/felipefernandez/trading_signals"
STREAMLIT="$TRADING_DIR/venv/bin/streamlit"

# Verificar si el dashboard ya está corriendo
if lsof -i :8501 > /dev/null 2>&1; then
    echo "Dashboard ya está corriendo — abriendo navegador..."
    open http://localhost:8501
    exit 0
fi

# Iniciar dashboard en background
echo "Iniciando dashboard..."
cd "$TRADING_DIR"
nohup "$STREAMLIT" run dashboard.py > /tmp/streamlit.log 2>&1 &
echo "Dashboard iniciado (PID: $!)"

# Esperar que inicie
sleep 4

# Abrir navegador
open http://localhost:8501
echo "✅ Dashboard en http://localhost:8501"
