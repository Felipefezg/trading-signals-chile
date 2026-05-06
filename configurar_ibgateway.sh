#!/bin/bash
# =============================================================================
# configurar_ibgateway.sh
# Configura IB Gateway (ya instalado y con sesión activa) para operar 24/7
#
# Hace:
#   1. Configura jts.ini → API habilitada en puerto 7497
#   2. launchd → auto-start de IB Gateway al login
#   3. launchd → restart automático a las 23:45 ET (01:45 AM Chile / 04:45 UTC)
# =============================================================================

set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
info() { echo -e "${BLUE}  →${NC} $1"; }
warn() { echo -e "${YELLOW}  !${NC} $1"; }

IB_PORT=7497
JTS_DIR="$HOME/Jts"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
RESTART_SCRIPT="$HOME/trading_signals/restart_ibgateway.sh"

# ── ENCONTRAR EJECUTABLE IB GATEWAY ───────────────────────────────────────────
echo ""
echo "Buscando IB Gateway..."
IBGATEWAY_BIN=""
for path in \
    "$HOME/Applications/IBGateway/ibgateway" \
    "/Applications/IBGateway/ibgateway" \
    "$HOME/Applications/IBGateway/IBGateway.app/Contents/MacOS/IBGateway" \
    "/Applications/IBGateway.app/Contents/MacOS/IBGateway" \
    "$HOME/ibgateway/ibgateway"; do
    if [ -f "$path" ]; then
        IBGATEWAY_BIN="$path"
        break
    fi
done

# Búsqueda amplia si no se encontró
if [ -z "$IBGATEWAY_BIN" ]; then
    IBGATEWAY_BIN=$(find "$HOME/Applications" /Applications -name "ibgateway" -o -name "IBGateway" 2>/dev/null | grep -v ".sh$" | head -1)
fi

if [ -z "$IBGATEWAY_BIN" ]; then
    echo ""
    warn "No se encontró el ejecutable automáticamente."
    echo "  Ejecuta: find ~ -name 'ibgateway' -o -name 'IBGateway' 2>/dev/null"
    echo -n "  Pega la ruta aquí: "
    read -r IBGATEWAY_BIN
fi
ok "Ejecutable: $IBGATEWAY_BIN"

# ── 1. CONFIGURAR jts.ini ─────────────────────────────────────────────────────
echo ""
echo "Configurando jts.ini..."
mkdir -p "$JTS_DIR"
JTS_INI="$JTS_DIR/jts.ini"

# Backup si existe
[ -f "$JTS_INI" ] && cp "$JTS_INI" "${JTS_INI}.bak_$(date +%Y%m%d_%H%M)"

set_key() {
    local section="$1" key="$2" value="$3"
    if grep -q "^\[$section\]" "$JTS_INI" 2>/dev/null; then
        if grep -q "^$key=" "$JTS_INI" 2>/dev/null; then
            sed -i '' "s/^$key=.*/$key=$value/" "$JTS_INI"
        else
            sed -i '' "/^\[$section\]/a\\
$key=$value" "$JTS_INI"
        fi
    else
        printf "\n[%s]\n%s=%s\n" "$section" "$key" "$value" >> "$JTS_INI"
    fi
}

set_key "Communication" "UseSSL"            "false"
set_key "API"           "UseSSL"            "false"
set_key "API"           "SocketPort"        "$IB_PORT"
set_key "API"           "AllowConnections"  "true"
set_key "API"           "TrustedIPs"        "127.0.0.1"
set_key "API"           "MasterApiClientID" "0"

ok "jts.ini → API puerto $IB_PORT, localhost only, SSL off"

# ── 2. LAUNCHD — AUTO-START AL LOGIN ─────────────────────────────────────────
echo ""
echo "Configurando auto-start al login..."
mkdir -p "$LAUNCHAGENTS"

cat > "$LAUNCHAGENTS/com.ibgateway.start.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ibgateway.start</string>
    <key>ProgramArguments</key>
    <array>
        <string>${IBGATEWAY_BIN}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>${JTS_DIR}</string>
    <key>StandardOutPath</key>
    <string>/tmp/ibgateway.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ibgateway_err.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

ok "Plist auto-start creado"

# ── 3. SCRIPT DE RESTART NOCTURNO ────────────────────────────────────────────
echo ""
echo "Configurando restart nocturno (23:45 ET)..."

cat > "$RESTART_SCRIPT" << 'SCRIPT'
#!/bin/bash
# Restart IB Gateway antes del corte diario de IB (medianoche ET)
LOG="/tmp/ibgateway_restart.log"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Iniciando restart nocturno" >> "$LOG"

# Cerrar IB Gateway
pkill -f "ibgateway" 2>/dev/null || pkill -f "IBGateway" 2>/dev/null
sleep 12

# Relanzar vía launchd
launchctl kickstart -k "gui/$(id -u)/com.ibgateway.start" 2>/dev/null \
    || launchctl start com.ibgateway.start 2>/dev/null \
    || echo "$(date '+%Y-%m-%d %H:%M:%S') — WARN: relanzar manualmente IB Gateway" >> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') — Restart completado" >> "$LOG"
SCRIPT

chmod +x "$RESTART_SCRIPT"

# Calcular hora local del restart
# IB corta a medianoche ET. Queremos 23:45 ET = 04:45 UTC.
# Chile ART (UTC-3): 01:45 AM | verano (UTC-3): 01:45 AM
# El script usa hora local del sistema macOS. Detectar offset:
UTC_OFFSET=$(date +%z)  # ej: -0300
OFFSET_HOURS=$(echo "$UTC_OFFSET" | cut -c1-3 | sed 's/+//')  # ej: -03
RESTART_UTC_H=4; RESTART_UTC_M=45
RESTART_LOCAL_H=$(( (RESTART_UTC_H + OFFSET_HOURS + 24) % 24 ))

cat > "$LAUNCHAGENTS/com.ibgateway.nightly-restart.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ibgateway.nightly-restart</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${RESTART_SCRIPT}</string>
    </array>
    <!-- ${RESTART_LOCAL_H}:${RESTART_UTC_M} hora local = 23:45 ET -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${RESTART_LOCAL_H}</integer>
        <key>Minute</key>
        <integer>${RESTART_UTC_M}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/ibgateway_restart_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ibgateway_restart_err.log</string>
</dict>
</plist>
EOF

ok "Restart nocturno: ${RESTART_LOCAL_H}:${RESTART_UTC_M} hora local (= 23:45 ET)"

# ── CARGAR EN LAUNCHD ─────────────────────────────────────────────────────────
echo ""
echo "Cargando en launchd..."

launchctl unload "$LAUNCHAGENTS/com.ibgateway.start.plist" 2>/dev/null || true
launchctl unload "$LAUNCHAGENTS/com.ibgateway.nightly-restart.plist" 2>/dev/null || true

launchctl load "$LAUNCHAGENTS/com.ibgateway.start.plist"           && ok "Auto-start cargado"
launchctl load "$LAUNCHAGENTS/com.ibgateway.nightly-restart.plist" && ok "Restart nocturno cargado"

# ── RESUMEN ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  LISTO${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo "  ✓ jts.ini configurado (puerto $IB_PORT)"
echo "  ✓ IB Gateway arranca automáticamente al login"
echo "  ✓ Restart automático a las ${RESTART_LOCAL_H}:${RESTART_UTC_M}h (= 23:45 ET)"
echo ""
echo -e "${YELLOW}Un solo paso manual en IB Gateway GUI:${NC}"
echo ""
echo "  Edit → Global Configuration → API → Settings:"
echo "    ☑  Enable ActiveX and Socket Clients"
echo "    Port: $IB_PORT"
echo "    ☑  Allow connections from localhost only"
echo "    → OK → Reiniciar IB Gateway si te lo pide"
echo ""
echo "Verificar conexión:"
echo "  Dashboard → Tab Ejecución → Motor Automático → Estado conexión IB"
echo ""
echo "Logs:"
echo "  tail -f /tmp/ibgateway.log"
echo "  tail -f /tmp/ibgateway_restart.log"
