import os
import re 
import io
import random
import asyncio
import nest_asyncio
import datetime
import pytz
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. WEB SUNUCUSU ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Güncel Hafıza Sistemi)"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. AYARLAR VE GLOBAL HAFIZA ---
nest_asyncio.apply()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL_NAME = 'gemini-2.0-flash'

client = genai.Client(api_key=GOOGLE_API_KEY)

# Hafıza Değişkenleri
HOROSCOPE_CACHE = {}  # Burç yorumları burada tutulacak
LAST_UPDATE_DATE = "" # "DD-MM-YYYY" formatında son güncelleme tarihi

VALID_ZODIACS = [
    "koc", "boga", "ikizler", "yengec", "aslan", "basak", 
    "terazi", "akrep", "yay", "oglak", "kova", "balik"
]

TAROT_CARDS = [
    "Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz",
    "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet",
    "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız",
    "Ay", "Güneş", "Mahkeme", "Dünya"
]

# --- 3. YARDIMCI FONKSİYONLAR ---

def turkce_karakter_duzelt(metin):
    metin = metin.lower().strip()
    duzeltmeler = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'i̇': 'i'}
    for kaynak, hedef in duzeltmeler.items():
        metin = metin.replace(kaynak, hedef)
    return metin

# --- 4. GÜNCELLEME MOTORU ---

async def update_daily_horoscopes():
    """Tüm burçları internetten tarar ve hafızayı yeniler."""
    global HOROSCOPE_CACHE, LAST_UPDATE_DATE
    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")
    
    print(f"🔄 Zenithar için {bugun} verileri internetten toplanıyor...")
    
    for burc in VALID_ZODIACS:
        try:
            # Google Search kullanarak her burç için taze veri çekiyoruz
            prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                      f"Bu gelişmelere dayanarak Zenithar tarzında, derin ve etkileyici bir Türkçe yorum yap. "
                      f"Maksimum 100 kelime.")
            
            res = client.models.generate_content(
                model=MODEL_NAME, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearchRetrieval())]
                )
            )
            HOROSCOPE_CACHE[burc] = res.text
            # API'yi yormamak için burçlar arası çok kısa bekleme
            await asyncio.sleep(1) 
        except Exception as e:
            print(f"Hata ({burc}): {e}")
            HOROSCOPE_CACHE[burc] = "Yıldızlar şu an bu burç için sessiz kalıyor, daha sonra tekrar dene."

    LAST_UPDATE_DATE = bugun
    print("✅ Günlük hafıza başarıyla güncellendi.")

# --- 5. KOMUT MOTORLARI ---

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_UPDATE_DATE
    metin = update.message.text.lower()
    temiz_args = re.sub(r'^/burcyorumla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    
    if not temiz_args:
        await update.message.reply_text("❗ Bir burç ismi yazmalısın. Örnek: /burcyorumla akrep")
        return

    # Başak/Basak düzeltmesi
    burc_input = turkce_karakter_duzelt(temiz_args)
    
    if burc_input not in VALID_ZODIACS:
        await update.message.reply_text("Mal mısın? Burç ismini doğru yaz.")
        return

    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")

    # --- DURUM 1: HAFIZA ESKİ VEYA YOK ---
    if LAST_UPDATE_DATE != bugun or burc_input not in HOROSCOPE_CACHE:
        status_msg = await update.message.reply_text("🛰️ Yıldız haritaları taranıyor...")
        await asyncio.sleep(3)
        
        await status_msg.edit_text("🔭 Gezegen konumları analiz ediliyor...")
        # Bu aşamada arka planda güncellemeyi başlatıyoruz
        await update_daily_horoscopes()
        await asyncio.sleep(3)
        
        await status_msg.edit_text("📜 Cıtkırıldroid senin için yorumu hazırlıyor...")
        await asyncio.sleep(1)
        
        yorum = HOROSCOPE_CACHE.get(burc_input)
        await status_msg.edit_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")
    
    # --- DURUM 2: HAFIZA ZATEN GÜNCEL ---
    else:
        # Hafıza güncel olsa bile istediğin o "bekleme" havasını veriyoruz
        status_msg = await update.message.reply_text("🛰️ Yıldız haritaları taranıyor...")
        await asyncio.sleep(2)
        await status_msg.edit_text("📜 Zenithar senin için yorumu hazırlıyor...")
        await asyncio.sleep(1)
        
        yorum = HOROSCOPE_CACHE.get(burc_input)
        await status_msg.edit_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")

# ☕ GELİŞMİŞ KAHVE FALI
async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_obj = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo_obj:
        await update.message.reply_text("☕ Fal için fincan fotosu lazım canım.")
        return

    status_msg = await update.message.reply_text("☕ Telveler analiz ediliyor, sakın ayrılma...")
    try:
        photo_file = await photo_obj.get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
        # Fal yorumunda klişeleri yasaklayıp görsel detay istiyoruz
        prompt = ("Görseldeki kahve lekelerini incele. Lekeleri somut nesnelere benzet (örneğin: şahlanmış at, kedi silüeti, anahtar). "
                  "Klişe sözler kullanma. Zenithar Falcı Teyze olarak dobra ve mistik bir dille yorumla.")
        res = client.models.generate_content(model=MODEL_NAME, contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        await status_msg.edit_text(f"☕ Zenithar Falcı Teyze Diyor Ki:\n\n{res.text}")
    except: await status_msg.edit_text("⚠️ Enerjin çok ağır, fincanı okuyamadım.")

# 📝 ÖZETLEME
async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    if not target: return
    status_msg = await update.message.reply_text("🔄 İnceleniyor...")
    try:
        if target.photo:
            photo_file = await target.photo[-1].get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = client.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        else:
            res = client.models.generate_content(model=MODEL_NAME, contents=f"Özetle: {target.text or target.caption}")
        await status_msg.edit_text(f"📝 ÖZET:\n\n{res.text}")
    except: await status_msg.edit_text("❌ Hata.")

# 🃏 TAROT
async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    try:
        res = client.models.generate_content(model=MODEL_NAME, contents=f"Tarot kartları: {', '.join(secilenler)}. Geçmiş, şimdi ve geleceği ayrı paragraflarda yorumla.")
        await status.edit_text(f"🔮 TAROT FALI:\n\n{res.text}")
    except: await status.edit_text("❌ Bağlantı koptu.")

# --- 6. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Komut Kayıtları
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
    print("Zenithar Services (Güncel Hafıza Modu) Başlatıldı...")
    await application.initialize(); await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
