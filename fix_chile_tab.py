import re

dashboard_path = "dashboard.py"
tab_chile_path = "tab_chile_nuevo.py"

with open(dashboard_path, "r") as f:
    content = f.read()

# 1. Agregar imports si no existen
if "bcch_completo" not in content:
    content = content.replace(
        "from data.macro_usa import get_macro_usa, get_correlaciones_chile",
        "from data.macro_usa import get_macro_usa, get_correlaciones_chile\n"
        "from data.bcch_completo import get_macro_chile_completo, get_contexto_macro, get_precios_cochilco"
    )
    print("✅ Import agregado")
else:
    print("ℹ️  Import ya existe")

# 2. Leer nuevo tab Chile
with open(tab_chile_path, "r") as f:
    nuevo_tab = f.read()

# 3. Reemplazar el bloque del tab Chile
# Buscar desde "# ── TAB CHILE" hasta "# ── TAB USA"
patron = r'# ── TAB CHILE ─+\nwith tab_chile:.*?(?=\n# ── TAB USA)'
match = re.search(patron, content, re.DOTALL)

if match:
    content = content[:match.start()] + nuevo_tab + "\n" + content[match.end():]
    print(f"✅ Tab Chile reemplazado (chars: {match.end() - match.start()} → {len(nuevo_tab)})")
else:
    print("❌ No se encontró el patrón del tab Chile")
    # Fallback: buscar por líneas
    lines = content.split('\n')
    start = None
    end = None
    for i, line in enumerate(lines):
        if '# ── TAB CHILE' in line:
            start = i
        if start and '# ── TAB USA' in line:
            end = i
            break
    if start and end:
        nuevo_lines = nuevo_tab.split('\n')
        lines[start:end] = nuevo_lines
        content = '\n'.join(lines)
        print(f"✅ Tab Chile reemplazado por líneas ({start}-{end})")
    else:
        print(f"❌ start={start} end={end}")

# 4. Guardar
with open(dashboard_path, "w") as f:
    f.write(content)

print("✅ Dashboard actualizado")
