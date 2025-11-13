import os
import requests
from bs4 import BeautifulSoup
import time
from discord_webhook import DiscordWebhook, DiscordEmbed
import re

# --- KONFIGURACJA ---

# 🚨 TUTAJ WKLEJ SWÓJ GOTOWY LINK Z FILTROWANIEM 
# PRZYKLAD: "https://www.olx.pl/elektronika/telefony/q-iphone-13-14/?search%5Bfilter_float_price%3Ato%5D=900&search%5Bcity_id%5D=14728"
OLX_SEARCH_URL = "Wklej tutaj Twój link do OLX z filtrami" 

# Pobiera URL webhooka z ustawień Render.com (Zmienna środowiskowa DISCORD_WEBHOOK)
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK') 

# Pamięć: ZBIÓR ID ogłoszeń, które już przetworzyliśmy w tej sesji (RAM)
scraped_post_ids = set()

# Modele, które muszą znaleźć się w tytule (dla podwójnej pewności)
IPHONE_MODELS = [
    "13 mini", "13 pro", "13 pro max", 
    "14", "14 pro", "14 pro max"
]
# --------------------

# --- FUNKCJE KOMUNIKACYJNE ---

def pobierz_id_z_linku(link):
    """Wyodrębnia unikalny identyfikator (ID) z linku OLX."""
    match = re.search(r'-ID(\d+)\.html$', link)
    if match:
        return match.group(1)
    return None

def wyslij_status_discord(wiadomosc, kolor='ffcc00'):
    """Wysyła krótką wiadomość statusu na Discorda ('nic nowego' lub błędy)."""
    global DISCORD_WEBHOOK
    if not DISCORD_WEBHOOK:
        return

    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK)
        embed = DiscordEmbed(
            title=f"⏳ RAPORT STATUSU",
            description=wiadomosc,
            color=kolor # Żółty/Pomarańczowy dla statusu, Czerwony dla błędów
        )
        embed.set_timestamp()
        webhook.execute() 
    except Exception as e:
        print(f"Błąd podczas wysyłania statusu na Discord: {e}")

def wyslij_powiadomienie(ogloszenie):
    """Wysyła szczegółowe powiadomienie o nowym ogłoszeniu."""
    global DISCORD_WEBHOOK
    
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK)
    
    embed = DiscordEmbed(
        title=f"🚨 NOWE OGŁOSZENIE: {ogloszenie['title']}",
        description=f"**Cena:** {ogloszenie['price']}\n[Zobacz ogłoszenie na OLX]({ogloszenie['url']})",
        color='00ff00' # Zielony
    )
    
    embed.set_timestamp()
    embed.set_footer(text="OLX Monitor | Nowa Oferta")
    
    webhook.add_embed(embed)
    response = webhook.execute()
    
    if response.status_code not in [200, 204]:
        print(f"Błąd Discord: {response.status_code}")
        
def test_discord_connection():
    """Wysyła test, aby potwierdzić działanie webhooka."""
    global DISCORD_WEBHOOK
    if not DISCORD_WEBHOOK:
        return False
        
    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK)
        embed = DiscordEmbed(
            title="✅ BOT ONLINE",
            description="Bot wystartował i jest gotowy do monitorowania OLX.",
            color='0099ff'
        )
        webhook.add_embed(embed)
        return webhook.execute().status_code in [200, 204]
    except Exception:
        return False

# --- GŁÓWNA FUNKCJA MONITORUJĄCA ---

def sprawdz_olx():
    """Pobiera i parsuje dane, zwraca liczbę znalezionych nowych ofert."""
    global scraped_post_ids
    print(f"Sprawdzam OLX na URL: {OLX_SEARCH_URL}")
    
    # Nagłówki symulujące przeglądarkę (pomocne przy cookies)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'pl-PL,pl;q=0.9',
        'Cookie': 'gdpr_consent=true; cookies_consent=1' 
    }
    
    try:
        response = requests.get(OLX_SEARCH_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Błąd pobierania: {e}")
        wyslij_status_discord(f"Wystąpił błąd połączenia z OLX: {e}", kolor='ff0000')
        return 0

    znalezione_ogloszenia = []
    
    # Używamy stabilnego selektora 'data-cy'
    ogloszenia_html = soup.find_all('div', {'data-cy': 'l-card'})

    for card in ogloszenia_html:
        # Używamy stabilnych selektorów 'data-testid'
        link_title_el = card.find('a', {'data-testid': 'ad-card-title'})
        price_el = card.find('p', {'data-testid': 'ad-price'})
        
        if link_title_el and price_el:
            link = "https://www.olx.pl" + link_title_el['href']
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
    
    powiadomienia_wyslane = 0
    
    for ogloszenie in znalezione_ogloszenia:
        
        # 1. Deduplikacja: pomiń już widziane
        if ogloszenie['id'] in scraped_post_ids:
            continue

        # 2. Filtr: czy pasuje do listy modeli?
        tytul_lower = ogloszenie['title'].lower()
        jest_pasujace = any(model.lower() in tytul_lower for model in IPHONE_MODELS)
        
        if jest_pasujace:
            # 3. Wysyłanie powiadomienia
            print(f"NOWE: {ogloszenie['title']}")
            wyslij_powiadomienie(ogloszenie)
            powiadomienia_wyslane += 1

        # Zawsze dodaj ID, aby je zapamiętać na tę sesję
        scraped_post_ids.add(ogloszenie['id'])

    return powiadomienia_wyslane

# --- GŁÓWNA PĘTLA URUCHAMIAJĄCA BOTA ---

if __name__ == "__main__":
    print("--- Startuję OLX Monitor ---")
    
    # Sprawdzenie konfiguracji
    if OLX_SEARCH_URL == "Wklej tutaj Twój link do OLX z filtrami":
        print("BŁĄD KRYTYCZNY: Nie skonfigurowano OLX_SEARCH_URL. Zakończenie.")
        exit(1)
    if not DISCORD_WEBHOOK:
        print("BŁĄD KRYTYCZNY: Webhook nieustawiony. Zakończenie.")
        exit(1)
        
    # Test połączenia Discord
    if not test_discord_connection():
         print("BŁĄD KRYTYCZNY: Webhook nie działa. Zakończenie.")
         exit(1) 

    # Pierwsze uruchomienie: zapamiętujemy istniejące oferty bez wysyłania powiadomień.
    print("Pierwsze uruchomienie: zapamiętuję istniejące ogłoszenia.")
    sprawdz_olx() 
    
    print("Gotowe. Rozpoczynam monitorowanie w pętli.")
    
    while True:
        try:
            # Oczekiwanie 5 minut (ten time.sleep jest na końcu poprzedniej pętli)
            time.sleep(5 * 60)
            print("Budzę się i sprawdzam OLX...")
            
            # Właściwe sprawdzenie OLX
            nowe_ogloszenia = sprawdz_olx()
            
            # Wysyłanie raportu statusu co 5 minut
            if nowe_ogloszenia == 0:
                wyslij_status_discord("Nic nowego. Sprawdzam ponownie za 5 minut.", kolor='3498db') # Niebieski
            else:
                # Jeśli są nowe, powiadomienia zostały już wysłane przez sprawdz_olx
                wyslij_status_discord(f"🎉 ZNALEZIONO {nowe_ogloszenia} nowych ogłoszeń!", kolor='00ff00') # Zielony
                
        except Exception as e:
            print(f"Wystąpił nieoczekiwany błąd w pętli: {e}")
            wyslij_status_discord(f"BŁĄD: Wystąpił błąd w pętli: {e}", kolor='ff0000') # Czerwony
