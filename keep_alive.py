# Zawartość pliku keep_alive.py (dla Rendera)

from flask import Flask

# To jest instancja Flask, którą Gunicorn znajdzie jako 'app'
# Musimy zmienić nazwę, aby pasowała do komendy: gunicorn main:app lub keep_alive:app
app = Flask(__name__) # Użyj __name__ to dobra praktyka 

@app.route('/')
def home():
    # Odpowiedź dla pingera (np. UptimeRobot)
    return "Bot jest aktywny i czuwa."

# WAŻNE: Cały kod do uruchamiania wątków (run, keep_alive, Thread) musi zniknąć!
