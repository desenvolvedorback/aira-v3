import sqlite3

conn = sqlite3.connect('aira.db')
c = conn.cursor()

# Adiciona a coluna feedback (se não existir)
try:
    c.execute("ALTER TABLE qa ADD COLUMN feedback TEXT;")
    print("Coluna 'feedback' adicionada com sucesso!")
except Exception as e:
    print("Erro:", e)

conn.commit()
conn.close()
