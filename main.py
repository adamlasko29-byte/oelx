import os
import requests
from bs4 import BeautifulSoup
import time
from discord_webhook import DiscordWebhook, DiscordEmbed
import re
from flask import Flask
import threading

# --- KONFIGURACJA Z POBIERANIEM ZMIENNYCH ŚRODOWISKOWYCH ---

# Pobiera URL webhooka z ustawień Render.com (Zmienna środowiskowa DISCORD_WEBHOOK)
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK') 

# URL wyszukiwania na OLX z filtrami:
# - q=iphone (filtr ogólny)
# - search[filter_float_price:to]=900 (Max cena 900 zł)
# - search[city_id]=14728 (Jaroszów)
OLX_URL = "https://www.olx.pl/elektronika/telefony/jaroszow/q-iphone/?search%5Bdist%5D=50&search%5Bfilter_float_price:to%5D=900" 

# Modele, które muszą znaleźć się w tytule
IPHONE_MODELS = [
    "13 mini", "13 pro", "13 pro max", 
    "14", "14 pro", "14 pro max"
]

# Pamięć RAM: ZBIÓR ID ogłoszeń, które już przetworzyliśmy w tej sesji
scraped_post_ids = set()

# --- FUNKCJE POMOCNICZE ---

def pobierz_id_z_linku(link):
    """Wyodrębnia unikalny identyfikator (ID) z linku OLX."""
    # Szukamy ciągu cyfr po ID na końcu linku przed .html
    match = re.search(r'-ID(\d+)\.html$', link)
    if match:
        return match.group(1)
    return None

def wyslij_powiadomienie(ogloszenie):
    """Tworzy i wysyła wiadomość typu Embed na Discorda."""
    global DISCORD_WEBHOOK
    
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK)
    
    embed = DiscordEmbed(
        title=f"🚨 NOWY iPhone OLX: {ogloszenie['title']}",
        description=f"**Cena:** {ogloszenie['price']}\n[Zobacz ogłoszenie na OLX]({ogloszenie['url']})",
        color='03b2f8'
    )
    
    embed.set_timestamp()
    embed.set_footer(text="OLX Monitor | To brzoza")
    
    webhook.add_embed(embed)
    response = webhook.execute()
    
    if response.status_code not in [200, 204]:
        print(f"Błąd podczas wysyłania na Discord: {response.status_code} - Sprawdź Webhook URL.")

def test_discord_connection():
    """Wysyła prostą wiadomość testową na Discorda."""
    global DISCORD_WEBHOOK
    if not DISCORD_WEBHOOK:
        return False
        
    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK)
        embed = DiscordEmbed(
            title="✅ TEST POŁĄCZENIA",
            description="Webhook działa. Rozpoczynam monitorowanie OLX.",
            color='00FF00' # Zielony
        )
        webhook.add_embed(embed)
        response = webhook.execute()

        return response.status_code in [200, 204]
    except Exception:
        return False

# --- GŁÓWNA FUNKCJA MONITORUJĄCA ---

# W pliku main.py, zaktualizuj całą funkcję sprawdz_olx()

def sprawdz_olx():
    """Pobiera dane z OLX, parsuje je i wysyła powiadomienia o nowych ofertach."""
    global scraped_post_ids
    print(f"Sprawdzam OLX na URL: {OLX_URL}")
    
    # Nagłówki (pozostają bez zmian)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cookie': 'gdpr_consent=true; cookies_consent=1' 
    }
    
    try:
        response = requests.get(OLX_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania strony lub połączenia: {e}")
        return

    znalezione_ogloszenia = []
    
    # Krok 1: Znalezienie wszystkich kontenerów ogłoszeń (wydaje się stabilne)
    ogloszenia_html = soup.find_all('div', {'data-cy': 'l-card'})

    for card in ogloszenia_html:
        
        # Krok 2: Użycie nowego, stabilnego atrybutu 'data-testid' dla LINKU i TYTUŁU
        # Link do ogłoszenia jest teraz w elemencie <a> z atrybutem data-testid="ad-card-title"
        link_title_el = card.find('a', {'data-testid': 'ad-card-title'})
        
        # Krok 3: Użycie nowego, stabilnego atrybutu 'data-testid' dla CENY
        price_el = card.find('p', {'data-testid': 'ad-price'})
        
        # Sprawdzenie, czy kluczowe elementy zostały znalezione
        if link_title_el and price_el:
            link = "https://www.olx.pl" + link_title_el['href']
            
            # Tytuł jest tekstem wewnątrz elementu <a>
            tytul = link_title_el.text.strip()
            cena = price_el.text.strip()
            
            ogloszenie_id = pobierz_id_z_linku(link)
            
            if ogloszenie_id:
                znalezione_ogloszenia.append({
                    'id': ogloszenie_id,
                    'title': tytul,
                    'price': cena,
                    'url': link
                })
        
        # Dodanie debugowania, aby sprawdzić, ile ogłoszeń pominięto z powodu błędnego parsowania
        # else:
        #     print("DEBUG: Pominięto kartę ogłoszenia - brak kluczowych atrybutów.")


    # ... (resztę funkcji: pętla deduplikacji i wysyłania powiadomień zostawiamy bez zmian)
    
    powiadomienia_wyslane = 0
    
    # Dodatkowe debugowanie, abyś wiedział, ile ogłoszeń zebrałeś
    print(f"DEBUG: Zbieranie danych zakończone. Znaleziono {len(znalezione_ogloszenia)} potencjalnych ogłoszeń.")
    
    for ogloszenie in znalezione_ogloszenia:
        
        # 1. Deduplikacja: pomiń już widziane ogłoszenia
        if ogloszenie['id'] in scraped_post_ids:
            continue

        # 2. Filtr modeli: Sprawdź, czy tytuł pasuje do szukanych modeli
        tytul_lower = ogloszenie['title'].lower()
        jest_pasujace = any(model.lower() in tytul_lower for model in IPHONE_MODELS)
        
        if jest_pasujace:
            # 3. Wysyłanie powiadomienia
            print(f"NOWE OGŁOSZENIE: {ogloszenie['title']} ({ogloszenie['price']})")
            wyslij_powiadomienie(ogloszenie)
            powiadomienia_wyslane += 1

        # Zawsze dodaj ID do zbioru, aby je zapamiętać
        scraped_post_ids.add(ogloszenie['id'])

    print(f"Zakończono sprawdzanie. Wysłałem {powiadomienia_wyslane} nowych powiadomień. Znanych ID: {len(scraped_post_ids)}")
    
def bot_loop():
    """Główna pętla, która będzie uruchamiana w tle w osobnym wątku."""
    
    # 1. Sprawdzenie i test przy starcie
    if not DISCORD_WEBHOOK:
        print("BŁĄD KRYTYCZNY: Webhook nieustawiony. Bot nie rozpocznie pracy.")
        return
        
    if not test_discord_connection():
         print("BŁĄD KRYTYCZNY: Połączenie z Discordem nieudane. Bot nie rozpocznie pracy.")
         return 

    # 2. Uruchomienie pierwszej kontroli i głównej pętli
    print("Test Discord OK. Pierwsze uruchomienie: zapamiętuję istniejące ogłoszenia...")
    sprawdz_olx() 
    print("Rozpoczynam monitorowanie w pętli.")
    
    while True:
        try:
            sprawdz_olx()
        except Exception as e:
            print(f"Wystąpił nieoczekiwany błąd w pętli: {e}")
        
        # Czekanie 5 minut (300 sekund)
        print("Czekam 5 minut...")
        time.sleep(5 * 60)


# --- APLIKACJA FLASK I START WĄTKU ---

# Tworzymy instancję aplikacji Flask, która będzie obsługiwana przez Gunicorn
app = Flask(__name__)

# Endpoint, który Render będzie pingował (Uptime Robot)
@app.route('/')
def home():
    # Zwraca status i informację o stanie bota
    return f"OLX Monitor Bot jest aktywny i sprawdza ogłoszenia co 5 minut. Znane ID: {len(scraped_post_ids)}", 200

# Uruchomienie pętli bota w osobnym wątku
# To musi nastąpić przed tym, jak Gunicorn zacznie obsługiwać requesty Flask
bot_thread = threading.Thread(target=bot_loop)
# Ustawienie daemon=True pozwala na zamknięcie programu, gdy główny wątek (Flask) się zamknie
bot_thread.daemon = True 
bot_thread.start()
