import warnings
warnings.filterwarnings("ignore", category=FutureWarning)



import os
import json
import time
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from search_engine import smart_search
import requests
import bcrypt

# Tentar carregar sentence-transformers, mas preparar fallback para TF-IDF
try:
    from sentence_transformers import SentenceTransformer, util
    EMBED_AVAILABLE = True
except Exception as e:
    print("[WARN] sentence-transformers não disponível, usando fallback TF-IDF. Erro:", e)
    EMBED_AVAILABLE = False
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

# ---------------- Config ----------------
DB_PATH = os.getenv("AIRA_DB", "aira.db")
WIKI_API = "https://pt.wikipedia.org/w/api.php"
EMBED_MODEL_NAME = os.getenv("AIRA_EMBED_MODEL", "all-MiniLM-L6-v2")
ADMIN_CODES = os.getenv("AIRA_ADMIN_CODES", "1234,4321,9999").split(",")
ADMIN_NICKS = os.getenv("AIRA_ADMIN_NICKS", "admin1,admin2,admin3").split(",")
SECRET_KEY = os.getenv("AIRA_SECRET_KEY", "troca_essa_senha_para_deploy")

# ---------------- DB ----------------
Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class QA(Base):
    __tablename__ = "qa"
    id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    embedding = Column(Text, nullable=True)  # json array or None

Base.metadata.create_all(engine)

# ---------------- Embeddings setup ----------------
if EMBED_AVAILABLE:
    print("Carregando modelo de embeddings:", EMBED_MODEL_NAME)
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
else:
    tfidf_vectorizer = TfidfVectorizer()
    # prepararemos o TF-IDF no primeiro uso

# ---------------- App ----------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Helper: hashing admin numeric codes (we store hashed versions in memory)
def hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()

# Inicializar admin list (in-memory hashed codes) - também exibirá nick quando logar
ADMIN_STORE = []
for i, code in enumerate(ADMIN_CODES):
    nick = ADMIN_NICKS[i] if i < len(ADMIN_NICKS) else f"admin{i+1}"
    ADMIN_STORE.append({"nick": nick, "code_hash": bcrypt.hashpw(code.strip().encode(), bcrypt.gensalt()).decode()})

# Decorator admin required
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ---------------- Utilities ----------------

def embed_text(text: str):
    if EMBED_AVAILABLE:
        vec = embed_model.encode(text, convert_to_numpy=True).tolist()
        return json.dumps(vec)
    else:
        return None

def compute_similarity(question: str, candidates: list):
    # candidates: list of dicts with 'id', 'question', 'answer', 'embedding'
    if not candidates:
        return None
    if EMBED_AVAILABLE:
        q_vec = embed_model.encode(question, convert_to_numpy=True).tolist()
        best = None
        best_score = -1
        for c in candidates:
            if not c.get('embedding'):
                continue
            score = util.cos_sim(q_vec, json.loads(c['embedding'])).item()
            if score > best_score:
                best_score = score
                best = c
        return {'score': float(best_score) if best is not None else 0.0, 'qa': best}
    else:
        # TF-IDF fallback: build matrix with question + candidates
        docs = [question] + [c['question'] for c in candidates]
        X = tfidf_vectorizer.fit_transform(docs)
        sims = cosine_similarity(X[0:1], X[1:]).flatten()
        idx = sims.argmax()
        return {'score': float(sims[idx]), 'qa': candidates[idx]}


def search_wikipedia_pt(query, sentences=3):
    try:
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": query,
            "redirects": 1,
            "formatversion": 2
        }
        r = requests.get(WIKI_API, params=params, timeout=6)
        data = r.json()
        if "query" in data and data["query"].get("pages"):
            page = data["query"]["pages"][0]
            if page.get("extract"):
                text = page["extract"]
                sents = text.split(". ")
                return ". ".join(sents[:sentences]) + ("" if len(sents)<=sentences else "...")
        # fallback opensearch
        params2 = {"action":"opensearch","search":query,"limit":3,"namespace":0,"format":"json"}
        r2 = requests.get(WIKI_API, params=params2, timeout=6)
        arr = r2.json()
        if len(arr)>=4 and len(arr[1])>0:
            title = arr[1][0]
            return search_wikipedia_pt(title, sentences)
    except Exception as e:
        print("WIKI ERROR:", e)
    return None

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template('index.html')

@app.route("/ask", methods=["POST"])
def ask():
    from sqlalchemy.orm import Session
    from search_engine import smart_search

    data = request.get_json()
    q = data.get("question", "").strip()

    if not q:
        return jsonify({"answer": "Pergunta vazia.", "source": "none", "cached": True})

    # cria sessão do banco
    s = Session(engine)

    try:
        # 1️⃣ Verifica se já existe resposta no banco
        qa = s.query(QA).filter(QA.question == q).first()
        if qa:
            return jsonify({"answer": qa.answer, "source": qa.source, "cached": True})

        # 2️⃣ Faz pesquisa inteligente
        res = smart_search(q)
        if res:
            answer = f"{res.get('title', '')} — {res.get('text', '')}"
            source = res.get("source", "web")
        else:
            answer = "Desculpa, não encontrei nenhuma fonte confiável. Pode reformular sua pergunta?"
            source = "none"

        # 3️⃣ Gera embedding (se modelo disponível)
        try:
            emb = embed_text(q)
        except Exception:
            emb = None

        # 4️⃣ Salva no banco
        qa = QA(question=q, answer=answer, source=source, embedding=emb)
        s.add(qa)
        s.commit()

        # 5️⃣ Retorna resposta
        return jsonify({"answer": answer, "source": source, "cached": False})

    except Exception as e:
        s.rollback()
        print("Erro no /ask:", e)
        return jsonify({"answer": "Erro interno ao processar.", "source": "none", "cached": False})

    finally:
        s.close()

# Admin login page (numeric code)
@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html')
    code = request.form.get('code','').strip()
    if not code:
        return render_template('admin_login.html', error='Código vazio')
    # checar códigos
    for adm in ADMIN_STORE:
        try:
            if bcrypt.checkpw(code.encode(), adm['code_hash'].encode()):
                session['admin'] = True
                session['admin_nick'] = adm['nick']
                return redirect(url_for('admin_panel'))
        except Exception:
            continue
    return render_template('admin_login.html', error='Código inválido')

@app.route('/admin/panel')
@admin_required
def admin_panel():
    s = SessionLocal()
    rows = s.query(QA).order_by(QA.id.desc()).limit(200).all()
    s.close()
    return render_template('admin_panel.html', qas=rows, nick=session.get('admin_nick','admin'))

@app.route('/admin/train', methods=['POST'])
@admin_required
def admin_train():
    q = request.form.get('question','').strip()
    a = request.form.get('answer','').strip()
    if not q or not a:
        return redirect(url_for('admin_panel'))
    s = SessionLocal()
    try:
        emb = embed_text(q)
        qa = QA(question=q, answer=a, source='manual', embedding=emb)
        s.add(qa)
        s.commit()
    except Exception as e:
        s.rollback()
        print('train error', e)
    finally:
        s.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<int:qa_id>', methods=['POST'])
@admin_required
def admin_delete(qa_id):
    s = SessionLocal()
    row = s.query(QA).filter_by(id=qa_id).first()
    if row:
        s.delete(row)
        s.commit()
    s.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    session.pop('admin_nick', None)
    return redirect(url_for('admin_login'))

# ---------------- Run ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render define a porta automaticamente
    app.run(host="0.0.0.0", port=port)
