from keep_alive import keep_alive
keep_alive()
import discord
import os
import requests
import json
import asyncio
from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Wczytanie zmiennych środowiskowych (Sekretów) z Replit
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
CHANNEL_ID = int(os.environ.get('CHANNEL_ID'))

# --- Ustawienia Wyszukiwania OLX ---
# Link do Twojego wyszukiwania na OLX:
# Szukane frazy: iphone 13, 13 mini, 13 pro, 14, 14 pro max
# Cena do 900 zł
# Lokalizacja: Jaroszów, Promień: 50 km
# Pamiętaj, aby UPEWNIĆ SIĘ, że link jest poprawny i zawiera filtry!
OLX_URL = 'https://www.olx.pl/elektronika/telefony/smartfony-telefony-komorkowe/iphone/jaroszow/?search%5Bdist%5D=50&search%5Bfilter_float_price:to%5D=900&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-13-mini&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-13&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-13-pro&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-14-pro&search%5Bfilter_enum_phonemodel%5D%5B4%5D=iphone-14'
# --- KONFIGURACJA OLX ---
# DODANE: Nagłówki ciasteczek do pominięcia banera
COOKIES = {
    # Używamy ciasteczka 'test' z wartością '1'
    'test': '1' 
}
# Uwaga: Konkretny link dla Jaroszowa i 50 km to bardzo trudny do ustawienia filtr URL.
# Używam ogólnego linku i sugeruję, abyś ręcznie ustawił filtry na OLX i SKOPIOWAŁ GOTOWY URL.

# Zbiór na przechowywanie ID już widzianych ogłoszeń (aby nie wysyłać powiadomień wielokrotnie)
# Używamy prostego pliku JSON do zapisu stanu.
SEEN_ADS_FILE = 'seen_ads.json'
seen_ads = set()

# Konfiguracja Bota Discord
intents = discord.Intents.default()
intents.message_content = True # Wymagane dla botów.
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Funkcje Pomocnicze ---

def load_seen_ads():
    """Wczytuje zbiór ID ogłoszeń z pliku."""
    global seen_ads
    if os.path.exists(SEEN_ADS_FILE):
        with open(SEEN_ADS_FILE, 'r') as f:
            # Wczytany JSON to lista, konwertujemy na zbiór (set) dla szybszego sprawdzania
            seen_ads = set(json.load(f))
    else:
        seen_ads = set()
    print(f"Wczytano {len(seen_ads)} zapisanych ogłoszeń.")

def save_seen_ads():
    """Zapisuje zbiór ID ogłoszeń do pliku."""
    with open(SEEN_ADS_FILE, 'w') as f:
        # Zapisujemy zbiór jako listę (set nie jest standardowym typem JSON)
        json.dump(list(seen_ads), f)

def get_olx_ads():
    """Pobiera i parsuje listę ogłoszeń z OLX."""
    # Użycie nagłówka 'User-Agent' symuluje prawdziwą przeglądarkę
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    }

    try:
        response = requests.get(OLX_URL, headers=headers, timeout=10)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania OLX: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    ads_data = []

    # KROK 1: Lokalizacja Głównego Kontenera (POPRAWIONE na podstawie Twoich danych)
    # Znaleziona klasa z Twojego zrzutu: css-1apmciz
    listings = soup.find_all('div', class_='css-1apmciz') 

    if not listings:
        print("Nie znaleziono kart ogłoszeń. Upewnij się, że selektor (css-1apmciz) jest poprawny.")
        return []

    for ad_card in listings:
        try:
            # KROK 2: Link Ogłoszenia (Tag <a>)
            # Klasa z Twojego zrzutu: css-1tqlkj0
            link_tag = ad_card.find('a', class_='css-1tqlkj0') 

            if not link_tag:
                continue

            link_href = link_tag.get('href')

            if not link_href:
                continue

            link = f"https://www.olx.pl{link_href}"

            # Ekstrakcja ID (powinno działać, jeśli link jest poprawny)
            import re
            match = re.search(r'-ID(\d+)\.html', link)
            ad_id = match.group(1) if match else None

            if not ad_id:
                 continue

            # KROK 3: Tytuł Ogłoszenia (Tag <h4>)
            # Klasa z Twojego zrzutu: css-hzlye5
            title_tag = ad_card.find('h4', class_='css-hzlye5') 
            title = title_tag.text.strip() if title_tag else 'Brak Tytułu'

            # KROK 4: Cena Ogłoszenia (Tag <p>)
            # Używamy stabilnego atrybutu 'data-testid="ad-price"'
            price_tag = ad_card.find('p', {'data-testid': 'ad-price'})

            if price_tag:
                # Pobieramy cały tekst (np. "== $0 750 zł")
                full_price_text = price_tag.text.strip()

                # Użyjemy RegEx do oczyszczenia ceny
                import re
                price = re.sub(r'[^\d\s\zł,]', '', full_price_text).strip()
            else:
                price = 'Brak Ceny'

            ads_data.append({
                'id': ad_id,
                'title': title,
                'price': price,
                'link': link
            })

        except Exception as e:
            # print(f"Błąd podczas parsowania ogłoszenia: {e}") # Możesz to odkomentować, żeby zobaczyć, co dokładnie się psuje
            continue

    return ads_data


# --- Pętla Sprawdzania Ogłoszeń ---

@tasks.loop(minutes=2) # Sprawdzaj co 2 minuty
async def check_for_new_ads():
    """Główna pętla sprawdzająca OLX i wysyłająca powiadomienia."""
    print("Rozpoczynam sprawdzanie nowych ogłoszeń OLX...")
    new_ads = []

    # 1. Pobierz aktualne ogłoszenia
    current_ads = get_olx_ads()

    # 2. Porównaj z zapisanymi
    for ad in current_ads:
        if ad['id'] not in seen_ads:
            new_ads.append(ad)
            seen_ads.add(ad['id']) # Dodaj nowe ID do zbioru

    # 3. Zapisz i Wyślij
    if new_ads:
        save_seen_ads() # Zapisz zaktualizowany zbiór ID

        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            print(f"Znaleziono {len(new_ads)} nowych ogłoszeń. Wysyłam na Discord...")
            for ad in new_ads:
                message = (
                    f"🔔 **NOWE OGŁOSZENIE OLX!** 🔔\n"
                    f"**Tytuł:** {ad['title']}\n"
                    f"**Cena:** {ad['price']}\n"
                    f"**Link:** {ad['link']}"
                )
                await channel.send(message)
        else:
            print(f"Błąd: Nie znaleziono kanału o ID {CHANNEL_ID}.")
    else:
        print("Nie znaleziono nowych ogłoszeń.")


@bot.event
async def on_ready():
    """Wykonywane po pomyślnym połączeniu z Discordem."""
    print(f'Zalogowano jako {bot.user.name}')

    # Upewniamy się, że bot jest gotowy zanim zacznie wysyłać wiadomości
    await bot.wait_until_ready() 

    # Wczytaj zapisane ID ogłoszeń
    load_seen_ads()

    # Uruchom pętlę sprawdzającą
    if not check_for_new_ads.is_running():
        check_for_new_ads.start()

# Uruchomienie Bota
if DISCORD_TOKEN:
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Błąd uruchomienia Bota: {e}")
else:
    print("BŁĄD: Brak DISCORD_TOKEN w pliku .env. Uzupełnij go, aby uruchomić Bota.")
