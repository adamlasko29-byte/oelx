import os
import requests
from bs4 import BeautifulSoup
import time
from discord_webhook import DiscordWebhook, DiscordEmbed
import re

# --- KONFIGURACJA ---

# Pobiera URL webhooka z ustawień Render.com
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK') 

# URL wyszukiwania na OLX z filtrami
# - q=iphone (filtr ogólny)
# - search[filter_float_price:to]=900 (Max cena 900 zł)
# - search[city_id]=14728 (Jaroszów)
# UWAGA: Filtr odległości '50km' jest trudny do zakodowania w statycznym URL, 
# OLX automatycznie stosuje promień dla danego miasta.
OLX_URL = "https://www.olx.pl/elektronika/telefony/q-iphone/?search%5Bfilter_float_price%3Ato%5D=900&search%5Bcity_id%5D=14728" 

# Modele, które muszą znaleźć się w tytule (dla podwójnej pewności)
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

def sprawdz_olx():
    """Pobiera dane z OLX, parsuje je i wysyła powiadomienia o nowych ofertach."""
    global scraped_post_ids
    print(f"Sprawdzam OLX na URL: {OLX_URL}")
    
    # Nagłówki, które symulują przeglądarkę i akceptują język
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        # Dodanie nagłówka Cookie, który akceptuje podstawowe ciasteczka (może pomóc)
        'Cookie': 'gdpr_consent=true; cookies_consent=1'
    }
    
    try:
        response = requests.get(OLX_URL, headers=headers)
        response.raise_for_status() # Wyrzuci wyjątek dla błędów 4xx/5xx
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania strony lub połączenia: {e}")
        return

    znalezione_ogloszenia = []
    
    # Najbardziej stabilne podejście: szukanie po atrybucie 'data-cy'
    ogloszenia_html = soup.find_all('div', {'data-cy': 'l-card'})

    for card in ogloszenia_html:
        link_el = card.find('a', href=True)
        title_el = card.find('h6')
        # Klasa ceny często zawiera frazę 'price'
        price_el = card.find('p', class_=lambda x: x and 'price' in x) 

        if link_el and title_el:
            link = "https://www.olx.pl" + link_el['href']
            tytul = title_el.text.strip()
            cena = price_el.text.strip() if price_el else 'Nie podano'
            ogloszenie_id = pobierz_id_z_linku(link)
            
            if ogloszenie_id:
                znalezione_ogloszenia.append({
                    'id': ogloszenie_id,
                    'title': tytul,
                    'price': cena,
                    'url': link
                })
    
    powiadomienia_wyslane = 0
    
    for ogloszenie in znalezione_ogloszenia:
        
        # 1. Deduplikacja: pomiń już widziane ogłoszenia
        if ogloszenie['id'] in scraped_post_ids:
            continue

        # 2. Filtr modeli: Sprawdź, czy tytuł pasuje do szukanych modeli
        tytul_lower = ogloszenie['title'].lower()
        jest_pasujace = any(model in tytul_lower for model in IPHONE_MODELS)
        
        if jest_pasujace:
            # 3. Wysyłanie powiadomienia
            print(f"NOWE OGŁOSZENIE: {ogloszenie['title']} ({ogloszenie['price']})")
            wyslij_powiadomienie(ogloszenie)
            powiadomienia_wyslane += 1

        # Zawsze dodaj ID do zbioru, aby je zapamiętać
        scraped_post_ids.add(ogloszenie['id'])

    print(f"Zakończono sprawdzanie. Wysłałem {powiadomienia_wyslane} nowych powiadomień. Znanych ID: {len(scraped_post_ids)}")

# --- GŁÓWNA PĘTLA URUCHAMIAJĄCA BOTA ---

if __name__ == "__main__":
    print("--- Startuję OLX Monitor ---")
    
    # 1. Sprawdzenie kluczowej zmiennej środowiskowej
    if not DISCORD_WEBHOOK:
        print("BŁĄD KRYTYCZNY: Zmienna środowiskowa 'DISCORD_WEBHOOK' nie jest ustawiona. Zakończenie programu.")
        exit(1)
        
    # 2. Testowanie połączenia z Discordem
    if not test_discord_connection():
         print("BŁĄD KRYTYCZNY: Połączenie z Discordem nieudane. Sprawdź poprawność URL webhooka.")
         # Zakończ działanie, jeśli nie można wysłać wiadomości
         exit(1) 

    # 3. Rozpoczęcie monitorowania
    print("Test Discord OK. Pierwsze uruchomienie: zapamiętuję istniejące ogłoszenia...")
    sprawdz_olx() 
    print("Gotowe. Rozpoczynam monitorowanie w pętli.")
    
    while True:
        try:
            sprawdz_olx()
        except Exception as e:
            print(f"Wystąpił nieoczekiwany błąd w pętli: {e}")
        
        # Czekanie 5 minut
        print("Czekam 5 minut...")
        time.sleep(5 * 60)
