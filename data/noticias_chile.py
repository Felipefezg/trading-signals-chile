import requests
import feedparser

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

KEYWORDS_CRITICOS = {
    "cobre": 5, "litio": 5, "sqm": 5, "codelco": 5,
    "tasa": 4, "banco central": 4, "ipsa": 4,
    "royalty": 4, "huelga": 4, "escondida": 4,
    "copec": 3, "falabella": 3, "entel": 3, "cmpc": 3,
    "tipo de cambio": 3, "dolar": 3, "cochilco": 4,
    "sequia": 3, "embalse": 3, "energia": 2,
    "dividendo": 2, "fusion": 3, "adquisicion": 3,
    "bce": 2, "fed": 2, "recesion": 4, "aranceles": 3,
}

TERMINOS_BUSQUEDA = [
    "SQM litio Chile",
    "cobre Chile precio",
    "Banco Central Chile tasa",
    "IPSA bolsa Santiago",
    "Codelco produccion",
    "Cochilco cobre litio",
    "economia Chile hoy",
    "dolar peso chileno",
    "Copec energia Chile",
    "mineria Chile royalty",
]

def score_noticia(titulo):
    contenido = titulo.lower()
    score = 0
    keywords_encontrados = []
    for kw, peso in KEYWORDS_CRITICOS.items():
        if kw in contenido:
            score += peso
            keywords_encontrados.append(kw)
    return score, keywords_encontrados

def get_noticias_google():
    noticias = []
    for termino in TERMINOS_BUSQUEDA:
        try:
            url = f"https://news.google.com/rss/search?q={termino.replace(' ', '+')}&hl=es-419&gl=CL&ceid=CL:es-419"
            r = requests.get(url, headers=HEADERS, timeout=8)
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:3]:
                titulo = entry.get("title", "")
                score, kws = score_noticia(titulo)
                noticias.append({
                    "fuente": "Google News",
                    "titulo": titulo,
                    "url": entry.get("link", ""),
                    "fecha": entry.get("published", ""),
                    "score": score,
                    "keywords": kws,
                    "termino": termino,
                })
        except Exception as e:
            print(f"Error Google News [{termino}]: {e}")
    # Deduplicar por titulo
    vistos = set()
    unicas = []
    for n in noticias:
        if n["titulo"] not in vistos:
            vistos.add(n["titulo"])
            unicas.append(n)
    return sorted(unicas, key=lambda x: x["score"], reverse=True)

def get_noticias_relevantes(min_score=1):
    todas = get_noticias_google()
    return [n for n in todas if n["score"] >= min_score][:20]

if __name__ == "__main__":
    print("=== NOTICIAS CHILE ===")
    noticias = get_noticias_relevantes()
    for n in noticias[:10]:
        print(f"[Score:{n['score']}] [{','.join(n['keywords'])}]")
        print(f"  {n['titulo'][:90]}")
        print()
