#!/bin/bash
TRADING_DIR="/Users/felipefernandez/trading_signals"
PYTHON="$TRADING_DIR/venv/bin/python3"
STREAMLIT="$TRADING_DIR/venv/bin/streamlit"

if lsof -i :8501 > /dev/null 2>&1; then
    open http://localhost:8501
    exit 0
fi

nohup "$PYTHON" "$TRADING_DIR/websocket_ib.py" > /tmp/websocket.log 2>&1 &
echo "WebSocket IB iniciado (PID: $!)"

nohup "$PYTHON" "$TRADING_DIR/trigger.py" > /tmp/trigger.log 2>&1 &
echo "Trigger iniciado (PID: $!)"

nohup "$STREAMLIT" run "$TRADING_DIR/dashboard.py" > /tmp/streamlit.log 2>&1 &
sleep 4
open http://localhost:8501
echo "Dashboard iniciado"
