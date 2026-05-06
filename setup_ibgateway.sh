#!/bin/bash
# =============================================================================
# setup_ibgateway.sh
# Configura IB Gateway para operar 24/7 en macOS
#
# LO QUE HACE ESTE SCRIPT:
#   1. Descarga IB Gateway (latest stable)
#   2. Abre el instalador (tú haces clic en Next/Install)
#   3. Configura jts.ini → habilita API en puerto 7497
#   4. Crea launchd: auto-start IB Gateway al login
#   5. Crea launchd: restart automático a las 23:45 ET (antes del corte IB)
#
# USO:
#   chmod +x setup_ibgateway.sh
#   ./setup_ibgateway.sh
#
# REQUIERE (manual, antes de correr este script):
#   - Primera vez: abrir IB Gateway, hacer login con tu cuenta IB
#   - En IB Gateway GUI: Configure → API → Enable ActiveX and Socket Clients ✓
#     (solo la primera vez; el script conserva esa config en lo sucesivo)
# =============================================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "\n${BLUE}══════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}══════════════════════════════════════${NC}"; }

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
IB_PORT=7497
IB_INSTALL_DIR="$HOME/Applications/IBGateway"   # destino típico del instalador
JTS_DIR="$HOME/Jts"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
PLIST_START="com.ibgateway.start"
PLIST_RESTART="com.ibgateway.nightly-restart"
RESTART_SCRIPT="$HOME/trading_signals/restart_ibgateway.sh"

# URL del instalador (stable standalone para macOS ARM/x64)
# Si cambia, buscar en https://www.interactivebrokers.com/en/trading/ibgateway.php
IB_DOWNLOAD_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-macosx-arm64.sh"
IB_DOWNLOAD_URL_X64="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-macosx-x64.sh"
IB_INSTALLER="/tmp/ibgateway_installer.sh"

# ── PASO 1: DETECTAR ARQUITECTURA Y DESCARGAR ─────────────────────────────────
step "PASO 1 — Descargando IB Gateway"

ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    DOWNLOAD_URL="$IB_DOWNLOAD_URL"
    info "Detectado Mac Apple Silicon (ARM64)"
else
    DOWNLOAD_URL="$IB_DOWNLOAD_URL_X64"
    info "Detectado Mac Intel (x64)"
fi

# Verificar si ya está instalado
IBGATEWAY_APP=$(find "$HOME/Applications" /Applications -name "ibgateway" -type f 2>/dev/null | head -1)
if [ -n "$IBGATEWAY_APP" ]; then
    ok "IB Gateway ya instalado en: $IBGATEWAY_APP"
    warn "Saltando descarga e instalación. Borrando si quieres reinstalar."
else
    info "Descargando desde $DOWNLOAD_URL..."
    curl -L --progress-bar "$DOWNLOAD_URL" -o "$IB_INSTALLER" || {
        warn "Falló descarga ARM64, intentando x64..."
        curl -L --progress-bar "$IB_DOWNLOAD_URL_X64" -o "$IB_INSTALLER" || error "No se pudo descargar el instalador"
    }
    chmod +x "$IB_INSTALLER"
    ok "Descarga completa: $IB_INSTALLER"

    # ── PASO 2: ABRIR INSTALADOR ──────────────────────────────────────────────
    step "PASO 2 — Instalando IB Gateway"
    echo ""
    warn "Se abrirá el instalador gráfico. Sigue los pasos:"
    echo "  1. Click en 'Next' en todas las pantallas"
    echo "  2. Acepta los términos"
    echo "  3. Usa el directorio de instalación por defecto"
    echo "  4. Click en 'Install' y luego 'Finish'"
    echo ""
    read -p "Presiona ENTER para abrir el instalador..."
    open "$IB_INSTALLER"
    echo ""
    read -p "Cuando termines la instalación, presiona ENTER para continuar..."
fi

# ── PASO 3: CONFIGURAR jts.ini ─────────────────────────────────────────────────
step "PASO 3 — Configurando API en jts.ini"

mkdir -p "$JTS_DIR"
JTS_INI="$JTS_DIR/jts.ini"

# Leer config existente si hay
if [ -f "$JTS_INI" ]; then
    info "jts.ini existente encontrado — actualizando sin borrar tu config"
    # Hacer backup
    cp "$JTS_INI" "${JTS_INI}.backup_$(date +%Y%m%d_%H%M%S)"
    ok "Backup guardado en ${JTS_INI}.backup_*"
else
    info "Creando jts.ini nuevo"
    touch "$JTS_INI"
fi

# Función para set/update una key en jts.ini
set_ini_key() {
    local section="$1"
    local key="$2"
    local value="$3"
    local file="$JTS_INI"

    if grep -q "^\[$section\]" "$file" 2>/dev/null; then
        # La sección existe — buscar y reemplazar la key
        if grep -q "^$key=" "$file" 2>/dev/null; then
            sed -i '' "s/^$key=.*/$key=$value/" "$file"
        else
            # Agregar la key después del header de sección
            sed -i '' "/^\[$section\]/a\\
$key=$value" "$file"
        fi
    else
        # Crear la sección
        echo "" >> "$file"
        echo "[$section]" >> "$file"
        echo "$key=$value" >> "$file"
    fi
}

# Configurar API
set_ini_key "Communication" "UseSSL" "false"
set_ini_key "API" "UseSSL" "false"
set_ini_key "API" "Port" "$IB_PORT"
set_ini_key "API" "SocketPort" "$IB_PORT"
set_ini_key "API" "AllowConnections" "true"
set_ini_key "API" "TrustedIPs" "127.0.0.1"
set_ini_key "API" "MasterApiClientID" "0"

ok "jts.ini configurado:"
echo "  Port: $IB_PORT"
echo "  AllowConnections: true"
echo "  TrustedIPs: 127.0.0.1"
echo "  UseSSL: false"

# ── PASO 4: LAUNCHD — AUTO-START AL LOGIN ─────────────────────────────────────
step "PASO 4 — Configurando auto-start al login (launchd)"

# Buscar el ejecutable de IB Gateway
IBGATEWAY_BIN=$(find "$HOME/Applications" /Applications -name "ibgateway" -type f 2>/dev/null | head -1)
if [ -z "$IBGATEWAY_BIN" ]; then
    # Buscar el wrapper .sh que genera el instalador
    IBGATEWAY_BIN=$(find "$HOME" -name "ibgateway" -maxdepth 5 2>/dev/null | grep -v ".sh$" | head -1)
fi
if [ -z "$IBGATEWAY_BIN" ]; then
    warn "No se encontró el ejecutable ibgateway. Buscando en rutas comunes..."
    for path in \
        "$HOME/Applications/IBGateway/ibgateway" \
        "/Applications/IBGateway/ibgateway" \
        "$HOME/ibgateway/ibgateway" \
        "/opt/IBGateway/ibgateway"; do
        if [ -f "$path" ]; then
            IBGATEWAY_BIN="$path"
            break
        fi
    done
fi

if [ -z "$IBGATEWAY_BIN" ]; then
    warn "No se encontró el ejecutable. Usando path genérico — editar el plist después si es necesario."
    IBGATEWAY_BIN="$HOME/Applications/IBGateway/ibgateway"
fi

ok "Ejecutable IB Gateway: $IBGATEWAY_BIN"

mkdir -p "$LAUNCHAGENTS"

cat > "$LAUNCHAGENTS/${PLIST_START}.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_START}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${IBGATEWAY_BIN}</string>
    </array>

    <!-- Arrancar al login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- NO usar KeepAlive aquí: IB Gateway maneja sus propios crashes -->
    <key>KeepAlive</key>
    <false/>

    <key>WorkingDirectory</key>
    <string>${HOME}/Jts</string>

    <key>StandardOutPath</key>
    <string>/tmp/ibgateway_start.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ibgateway_start_err.log</string>

    <!-- Esperar 10s entre reinicios si falla (evita bucle de crashes) -->
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

ok "Plist de auto-start creado: $LAUNCHAGENTS/${PLIST_START}.plist"

# ── PASO 5: LAUNCHD — RESTART NOCTURNO A LAS 23:45 ET ─────────────────────────
step "PASO 5 — Configurando restart nocturno (23:45 ET → 04:45 UTC+1 / 03:45 UTC)"

# Script que mata IB Gateway y lo relanza
cat > "$RESTART_SCRIPT" << 'RESTART_EOF'
#!/bin/bash
# Restart IB Gateway en el horario nocturno (antes del corte de IB a medianoche ET)
LOG="/tmp/ibgateway_restart.log"
echo "$(date): Iniciando restart nocturno de IB Gateway" >> "$LOG"

# Matar IB Gateway de forma limpia
pkill -f "ibgateway" && echo "$(date): IB Gateway detenido" >> "$LOG"
sleep 10

# Recargar launchd para relanzar
launchctl kickstart -k "gui/$(id -u)/com.ibgateway.start" 2>/dev/null || \
    launchctl start com.ibgateway.start 2>/dev/null || \
    echo "$(date): WARN: no se pudo relanzar via launchctl — IB Gateway iniciará solo al siguiente login" >> "$LOG"

echo "$(date): Restart nocturno completado" >> "$LOG"
RESTART_EOF

chmod +x "$RESTART_SCRIPT"
ok "Script de restart creado: $RESTART_SCRIPT"

# IB Gateway tiene un corte diario a medianoche ET.
# Hora local macOS en Chile (ET+1h verano / ET+2h invierno):
#   - 11:45 PM ET = 12:45 AM Chile verano (hora 0, min 45)
#   - 11:45 PM ET = 01:45 AM Chile invierno (hora 1, min 45)
# Para cubrir ambos, usar UTC: 11:45 PM ET = 04:45 AM UTC
# launchd usa hora local del sistema. Usar 04:45 UTC (asumiendo Mac en Chile UTC-3):
# 04:45 UTC = 01:45 hora Chile verano (UTC-3)
# Ajustar si tu Mac tiene otra zona horaria.

cat > "$LAUNCHAGENTS/${PLIST_RESTART}.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_RESTART}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${RESTART_SCRIPT}</string>
    </array>

    <!-- Ejecutar a las 01:45 hora Chile (= 23:45 ET aprox) -->
    <!-- AJUSTA la hora si tu Mac usa otra zona horaria -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>1</integer>
        <key>Minute</key>
        <integer>45</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/ibgateway_restart_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ibgateway_restart_err.log</string>
</dict>
</plist>
EOF

ok "Plist de restart nocturno creado"

# ── PASO 6: CARGAR LAUNCHD ────────────────────────────────────────────────────
step "PASO 6 — Cargando en launchd"

# Descargar versiones previas si existen
launchctl unload "$LAUNCHAGENTS/${PLIST_START}.plist" 2>/dev/null || true
launchctl unload "$LAUNCHAGENTS/${PLIST_RESTART}.plist" 2>/dev/null || true

# Cargar las nuevas
launchctl load "$LAUNCHAGENTS/${PLIST_START}.plist" && ok "Auto-start cargado" || warn "Error cargando auto-start"
launchctl load "$LAUNCHAGENTS/${PLIST_RESTART}.plist" && ok "Restart nocturno cargado" || warn "Error cargando restart"

# ── PASO 7: VERIFICACIÓN ──────────────────────────────────────────────────────
step "PASO 7 — Verificación"

echo ""
echo "Estado launchd:"
launchctl list | grep ibgateway | awk '{printf "  %-10s %-10s %s\n", $1, $2, $3}' || echo "  (no encontrado — normal si IB Gateway aún no está instalado)"

echo ""
echo "Archivos configurados:"
[ -f "$JTS_INI" ]                                    && echo "  ✓ $JTS_INI" || echo "  ✗ $JTS_INI"
[ -f "$LAUNCHAGENTS/${PLIST_START}.plist" ]          && echo "  ✓ ${PLIST_START}.plist" || echo "  ✗"
[ -f "$LAUNCHAGENTS/${PLIST_RESTART}.plist" ]        && echo "  ✓ ${PLIST_RESTART}.plist" || echo "  ✗"
[ -f "$RESTART_SCRIPT" ]                             && echo "  ✓ $RESTART_SCRIPT" || echo "  ✗"

# ── RESUMEN FINAL ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  CONFIGURACIÓN COMPLETADA${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo "  ✓ jts.ini configurado (API puerto $IB_PORT)"
echo "  ✓ Auto-start al login: ${PLIST_START}"
echo "  ✓ Restart nocturno 01:45h: ${PLIST_RESTART}"
echo ""
echo -e "${YELLOW}PASOS MANUALES RESTANTES (solo una vez):${NC}"
echo ""
echo "  1. Abre IB Gateway y haz LOGIN con tu cuenta IB"
echo "     (usa 'Paper Trading' si quieres seguir en paper)"
echo ""
echo "  2. En IB Gateway → Edit → Global Configuration → API:"
echo "     ☑ Enable ActiveX and Socket Clients"
echo "     Port: $IB_PORT"
echo "     ☑ Allow connections from localhost only"
echo "     → Click OK"
echo ""
echo "  3. En IB Gateway → Edit → Global Configuration → Auto-restart:"
echo "     ☑ Auto restart"
echo "     Hora: 11:45 PM (ET)"
echo "     → Click OK"
echo ""
echo "  4. Verificar que el trigger ve IB (en el dashboard:"
echo "     Tab Ejecución → Motor Automático → Estado conexión IB)"
echo ""
echo -e "${BLUE}Logs útiles:${NC}"
echo "  tail -f /tmp/ibgateway_start.log"
echo "  tail -f /tmp/ibgateway_restart.log"
echo "  tail -f ~/trading_signals/trigger.log"
echo ""
