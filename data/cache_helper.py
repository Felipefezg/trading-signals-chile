
import json, os, time
from datetime import datetime

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_get(key, max_age_min=30):
    """Retorna datos del cache si son recientes, None si expiraron"""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    age = (time.time() - os.path.getmtime(path)) / 60
    if age > max_age_min:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

def cache_set(key, data):
    """Guarda datos en cache"""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, default=str)
        return True
    except:
        return False
