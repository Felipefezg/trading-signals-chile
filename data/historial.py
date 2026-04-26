import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "historial.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS senales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            senal TEXT,
            prob_pct REAL,
            direccion TEXT,
            activos TEXT,
            score REAL,
            tesis TEXT,
            resultado TEXT DEFAULT 'pendiente'
        )
    """)
    conn.commit()
    conn.close()

def guardar_senales(df_senales):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    nuevas = 0
    for _, row in df_senales.iterrows():
        # Evitar duplicados del mismo dia
        c.execute("""
            SELECT id FROM senales 
            WHERE senal=? AND fecha LIKE ?
        """, (row["Señal"], fecha[:10] + "%"))
        if not c.fetchone():
            c.execute("""
                INSERT INTO senales (fecha, senal, prob_pct, direccion, activos, score, tesis)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fecha,
                row["Señal"],
                row["Prob %"],
                row["Dirección"],
                row["Activos Chile"],
                row["Score"],
                row["Tesis"],
            ))
            nuevas += 1
    conn.commit()
    conn.close()
    return nuevas

def get_historial(limit=100):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT fecha, senal, prob_pct, direccion, activos, score, tesis, resultado
        FROM senales ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def actualizar_resultado(senal, fecha_dia, resultado):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE senales SET resultado=?
        WHERE senal=? AND fecha LIKE ?
    """, (resultado, senal, fecha_dia + "%"))
    conn.commit()
    conn.close()

def get_estadisticas():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM senales")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM senales WHERE resultado='correcto'")
    correctas = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM senales WHERE resultado='incorrecto'")
    incorrectas = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM senales WHERE resultado='pendiente'")
    pendientes = c.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "correctas": correctas,
        "incorrectas": incorrectas,
        "pendientes": pendientes,
        "tasa_exito": round(correctas / (correctas + incorrectas) * 100, 1) if (correctas + incorrectas) > 0 else 0
    }

if __name__ == "__main__":
    init_db()
    print("DB inicializada en:", DB_PATH)
    print("Estadísticas:", get_estadisticas())
