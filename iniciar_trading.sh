#!/bin/bash
TRADING_DIR="/Users/felipefernandez/trading_signals"
STREAMLIT="$TRADING_DIR/venv/bin/streamlit"
PYTHON="$TRADING_DIR/venv/bin/python3"

# Verificar si dashboard ya corre
if lsof -i :8501 > /dev/null 2>&1; then
    open http://localhost:8501
    exit 0
fi

# Iniciar trigger en background
nohup "$PYTHON" "$TRADING_DIR/trigger.py" > /tmp/trigger.log 2>&1 &
echo "Trigger iniciado (PID: $!)"

# Iniciar dashboard
nohup "$STREAMLIT" run "$TRADING_DIR/dashboard.py" > /tmp/streamlit.log 2>&1 &
sleep 4
open http://localhost:8501
echo "Dashboard iniciado"
