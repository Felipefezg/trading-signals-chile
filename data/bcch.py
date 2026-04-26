
import requests
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# mindicador.cl — API publica chilena sin autenticacion
BASE_URL = "https://mindicador.cl/api"

def get_clp_usd():
    try:
        r = requests.get(f"{BASE_URL}/dolar", timeout=10)
        r.raise_for_status()
        data = r.json()
        serie = data.get("serie", [])
        if not serie:
            return None, None
        ultimo = serie[0]
        return float(ultimo["valor"]), ultimo["fecha"][:10]
    except Exception as e:
        print(f"Error CLP/USD: {e}")
        return None, None

def get_tpm():
    try:
        r = requests.get(f"{BASE_URL}/tpm", timeout=10)
        r.raise_for_status()
        data = r.json()
        serie = data.get("serie", [])
        if not serie:
            return None, None
        ultimo = serie[0]
        return float(ultimo["valor"]), ultimo["fecha"][:10]
    except Exception as e:
        print(f"Error TPM: {e}")
        return None, None

def get_ipc():
    try:
        r = requests.get(f"{BASE_URL}/ipc", timeout=10)
        r.raise_for_status()
        data = r.json()
        serie = data.get("serie", [])
        if not serie:
            return None, None
        ultimo = serie[0]
        return float(ultimo["valor"]), ultimo["fecha"][:10]
    except Exception as e:
        print(f"Error IPC: {e}")
        return None, None

def get_uf():
    try:
        r = requests.get(f"{BASE_URL}/uf", timeout=10)
        r.raise_for_status()
        data = r.json()
        serie = data.get("serie", [])
        if not serie:
            return None, None
        ultimo = serie[0]
        return float(ultimo["valor"]), ultimo["fecha"][:10]
    except Exception as e:
        print(f"Error UF: {e}")
        return None, None

def get_resumen_bcch():
    clp, fecha_clp = get_clp_usd()
    tpm, fecha_tpm = get_tpm()
    ipc, fecha_ipc = get_ipc()
    uf,  fecha_uf  = get_uf()
    return {
        "CLP/USD":   clp,
        "fecha_clp": fecha_clp,
        "TPM_%":     tpm,
        "fecha_tpm": fecha_tpm,
        "IPC_%":     ipc,
        "fecha_ipc": fecha_ipc,
        "UF":        uf,
        "fecha_uf":  fecha_uf,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }

if __name__ == "__main__":
    print("=== INDICADORES CHILE (mindicador.cl) ===")
    resumen = get_resumen_bcch()
    for k, v in resumen.items():
        print(f"  {k}: {v}")
