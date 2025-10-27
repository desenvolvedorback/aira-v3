# search_engine.py
# Módulo de busca gratuito: Wikipedia -> YouTube -> Google (scraping leve)
# Dependências: wikipedia, youtube-search-python, googlesearch-python, requests, beautifulsoup4

import time
import requests
from bs4 import BeautifulSoup

# lib wikipedia (usa API)
try:
    import wikipedia
    wikipedia.set_lang("pt")
    WIKI_AVAILABLE = True
except Exception:
    WIKI_AVAILABLE = False

# youtube-search-python (sem API key)
try:
    from youtubesearchpython import VideosSearch
    YT_AVAILABLE = True
except Exception:
    YT_AVAILABLE = False

# googlesearch (pega URLs)
try:
    from googlesearch import search as googlesearch
    GOOGLE_SEARCH_AVAILABLE = True
except Exception:
    GOOGLE_SEARCH_AVAILABLE = False

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 8  # segundos

def search_wikipedia(query, sentences=4):
    """Tenta obter resumo da Wikipedia (pt)."""
    if not WIKI_AVAILABLE:
        return None
    try:
        # busca por página mais relevante
        results = wikipedia.search(query, results=5)
        if not results:
            return None
        # pegar a primeira página e extrair resumo
        page = results[0]
        summary = wikipedia.summary(page, sentences=sentences)
        return {"source": "wikipedia", "title": page, "text": summary, "url": f"https://pt.wikipedia.org/wiki/{page.replace(' ', '_')}"}
    except Exception:
        return None

def search_youtube(query, max_results=2):
    """Busca vídeos no YouTube e tenta extrair descrição curta."""
    if not YT_AVAILABLE:
        return None
    try:
        videosSearch = VideosSearch(query, limit=max_results)
        res = videosSearch.result()
        items = res.get("result", []) if isinstance(res, dict) else res
        if not items:
            return None
        # pegar primeiro vídeo e montar resumo curto
        vid = items[0]
        title = vid.get("title")
        link = vid.get("link")
        desc = vid.get("descriptionSnippet")
        # descriptionSnippet é lista de dicts; transformar em texto
        if isinstance(desc, list):
            desc_text = " ".join([p.get("text","") for p in desc])
        else:
            desc_text = vid.get("description", "") or ""
        text = (desc_text[:800] + "...") if desc_text else f"Vídeo: {title}"
        return {"source": "youtube", "title": title, "text": text, "url": link}
    except Exception:
        return None

def fetch_text_from_url(url, max_chars=1500):
    """Busca uma URL e tenta extrair um parágrafo útil do conteúdo (scraping leve)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # tentar encontrar o primeiro parágrafo relevante
        for tag in ["article", "main", "div", "body"]:
            container = soup.find(tag)
            if container:
                p = container.find("p")
                if p and p.get_text(strip=True):
                    text = p.get_text(separator=" ", strip=True)
                    return text[:max_chars] + ("..." if len(text) > max_chars else "")
        # fallback: pegar primeiro <p> da página inteira
        p = soup.find("p")
        if p and p.get_text(strip=True):
            text = p.get_text(separator=" ", strip=True)
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception:
        return None
    return None

def search_google_snippet(query, num=5):
    """Usa googlesearch para obter URLs e retorna o snippet do primeiro resultado útil."""
    if not GOOGLE_SEARCH_AVAILABLE:
        return None
    try:
        results = googlesearch(query, num_results=num, lang='pt')  # alguns wrappers usam parâmetros diferentes
        # older googlesearch returns generator - safeguard
        if results is None:
            return None
        # garantir lista
        if not isinstance(results, (list, tuple)):
            results = list(results)
        for url in results:
            snippet = fetch_text_from_url(url)
            if snippet:
                return {"source": "web", "title": url, "text": snippet, "url": url}
        return None
    except TypeError:
        # algumas versões expõem func com assinatura (query, tld, lang, num, start, stop, pause)
        try:
            results = googlesearch(query, lang='pt', num=5, stop=5)
            for url in results:
                snippet = fetch_text_from_url(url)
                if snippet:
                    return {"source": "web", "title": url, "text": snippet, "url": url}
        except Exception:
            return None
    except Exception:
        return None

def smart_search(query):
    """Fluxo principal: wikipedia -> youtube -> google -> fallback."""
    # 1) Wikipédia
    w = search_wikipedia(query)
    if w:
        return w

    # 2) YouTube
    y = search_youtube(query)
    if y:
        return y

    # 3) Google / pesquisa geral
    g = search_google_snippet(query)
    if g:
        return g

    # 4) fallback simples: retornar None
    return None

if __name__ == "__main__":
    # teste rápido
    q = "Quem foi Santos Dumont?"
    print("WIKI:", search_wikipedia(q))
    print("YOUTUBE:", search_youtube(q))
    print("GOOGLE:", search_google_snippet(q))
