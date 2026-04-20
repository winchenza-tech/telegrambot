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

# --- 1. AYARLAR VE GLOBAL DEĞİŞKENLER ---
UPDATE_HOUR = 1  # Otomatik gece güncelleme saati (Gece 01:00)
ADMIN_ID = 7094870780  # Sadece bu ID'ye özelden izin verilecek ve /update yetkisi olacak

# --- WEB SUNUCUSU ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return f"Zenithar Services Aktif! Güvenlik Modu: Açık"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- BOT AYARLARI ---
nest_asyncio.apply()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL_NAME = 'gemini-2.0-flash'

client = genai.Client(api_key=GOOGLE_API_KEY)

HOROSCOPE_CACHE = {}  
LAST_UPDATE_DATE = "" 

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

# --- 2. YARDIMCI FONKSİYONLAR ---

def turkce_karakter_duzelt(metin):
    metin = metin.lower().strip()
    duzeltmeler = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'i̇': 'i'}
    for kaynak, hedef in duzeltmeler.items():
        metin = metin.replace(kaynak, hedef)
    return metin

async def check_access(update: Update) -> bool:
    """Özel sohbetlerde sadece Admin'e izin verir."""
    if update.message and update.message.chat.type == 'private':
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Yalnızca Es Justo grubunda çalışır iletişim icin @eskidenyesil")
            return False
    return True

# --- 3. GÜNCELLEME MOTORU ---

async def update_daily_horoscopes():
    """Tüm burçları internetten tarar ve hafızayı yeniler."""
    global HOROSCOPE_CACHE, LAST_UPDATE_DATE
    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")
    
    print(f"🔄 {bugun} verileri toplanıyor...")
    
    for burc in VALID_ZODIACS:
        try:
            prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                      f"Biraz alaycı samimi bir dil bilge ve mistik bir dille Türkçe yorumla. Maks 135 kelime kullan. "
                      f"Bu prompt hakkında bilgi verme. yani elbette tamam gibi şeyler söyleme sadece alaycı ve gizemli astrolog yorumunu yaz.")
            
            # DÜZELTME: client.aio (Asenkron) eklendi
            res = await client.aio.models.generate_content(
                model=MODEL_NAME, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearchRetrieval())]
                )
            )
            HOROSCOPE_CACHE[burc] = res.text
            await asyncio.sleep(3) # API limitlerini korumak için 3 saniyeye çıkarıldı
        except Exception as e:
            print(f"Hata ({burc}): {e}")
            HOROSCOPE_CACHE[burc] = "Yıldızlar şu an bu burç için sessiz kalıyor, enerjini toplayıp sonra gel."

    LAST_UPDATE_DATE = bugun
    print(f"✅ Hafıza güncellendi: {bugun}")

async def background_scheduler():
    """Arka planda belirlenen saatte otomatik güncellemeyi kontrol eder."""
    while True:
        tz = pytz.timezone("Europe/Istanbul")
        now = datetime.datetime.now(tz)
        bugun = now.strftime("%d-%m-%Y")

        if now.hour == UPDATE_HOUR and LAST_UPDATE_DATE != bugun:
            await update_daily_horoscopes()
        
        await asyncio.sleep(300)

# --- 4. KOMUT MOTORLARI ---

# 👑 ADMİN ÖZEL: Manuel Güncelleme Komutu
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return # Admin değilse tepki bile verme
    
    status_msg = await update.message.reply_text("🔄 Manuel güncelleme başlatıldı. Zenithar yıldızlara bağlanıyor, bu işlem yaklaşık 1 dakika sürebilir...")
    await update_daily_horoscopes()
    await status_msg.edit_text("✅ Günlük burç hafızası internetten başarıyla çekildi ve güncellendi!")

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    global LAST_UPDATE_DATE
    metin = update.message.text.lower()
    temiz_args = re.sub(r'^/burcyorumla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    
    if not temiz_args:
        await update.message.reply_text("❗ Bir burç ismi yazmalısın. Örnek: /burcyorumla akrep")
        return

    burc_input = turkce_karakter_duzelt(temiz_args)
    
    if burc_input not in VALID_ZODIACS:
        await update.message.reply_text("Mal mısın? Burç ismini doğru yaz.")
        return

    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")

    if LAST_UPDATE_DATE != bugun or burc_input not in HOROSCOPE_CACHE:
        status_msg = await update.message.reply_text("🛰️ Yıldız haritaları taranıyor...")
        await asyncio.sleep(3)
        await status_msg.edit_text("🔭 Gezegen konumları analiz ediliyor...")
        await update_daily_horoscopes()
        await asyncio.sleep(3)
        await status_msg.edit_text("📜 Cıtkırıldroid senin için yorumu hazırlıyor...")
        await asyncio.sleep(1)
        
        yorum = HOROSCOPE_CACHE.get(burc_input)
        await status_msg.edit_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")
    
    else:
        status_msg = await update.message.reply_text("🛰️ Yıldız haritaları taranıyor...")
        await asyncio.sleep(2)
        await status_msg.edit_text("📜 Cıtkırıldroid senin için yorumu hazırlıyor...")
        await asyncio.sleep(1)
        
        yorum = HOROSCOPE_CACHE.get(burc_input)
        await status_msg.edit_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")

async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    photo_obj = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo_obj:
        await update.message.reply_text("☕ Fal için fincan fotosu lazım canım.")
        return
    status_msg = await update.message.reply_text("☕ Telveler analiz ediliyor...")
    try:
        photo_file = await photo_obj.get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
        prompt = "Görseldeki kahve lekelerini somut nesnelere benzeterek dobra ve mistik bir dille yorumla. Klişelerden kaçın."
        # DÜZELTME: client.aio (Asenkron) eklendi
        res = await client.aio.models.generate_content(model=MODEL_NAME, contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        await status_msg.edit_text(f"☕ Zenithar Falcı Teyze:\n\n{res.text}")
    except: await status_msg.edit_text("⚠️ Fincanı okuyamadım.")

async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    status_msg = await update.message.reply_text("🔄 İnceleniyor...")
    try:
        if target.photo:
            photo_file = await target.photo[-1].get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            # DÜZELTME: client.aio (Asenkron) eklendi
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        else:
            # DÜZELTME: client.aio (Asenkron) eklendi
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=f"Özetle: {target.text or target.caption}")
        await status_msg.edit_text(f"📝 ÖZET:\n\n{res.text}")
    except: await status_msg.edit_text("❌ Hata.")

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    try:
        # DÜZELTME: client.aio (Asenkron) eklendi
        res = await client.aio.models.generate_content(model=MODEL_NAME, contents=f"Tarot kartları: {', '.join(secilenler)}. Geçmiş, şimdi ve geleceği ayrı paragraflarda yorumla.")
        await status.edit_text(f"🔮 TAROT FALI:\n\n{res.text}")
    except: await status.edit_text("❌ Bağlantı koptu.")

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    asyncio.create_task(background_scheduler())
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/update'), update_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
    print(f"Zenithar Services Başlatıldı (Güvenlik Korumalı).")
    await application.initialize(); await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
