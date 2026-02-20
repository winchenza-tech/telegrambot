import asyncio
import nest_asyncio
import os
import random
import io
import datetime
import pytz
import re 
import requests 
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. WEB SUNUCUSU ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Tam Erişim Modu)"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- 2. AYARLAR ---
nest_asyncio.apply()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
AUTHORIZED_GROUP_ID = -1003297262036 

MODEL_NAME = 'gemini-2.0-flash'

# --- 🚫 YASAKLI STICKER PAKETLERİ ---
YASAKLI_PAKETLER = [
    "OldiesButGoldies5",
    "ino8723",
    "gq0bpksh8_1003369169896_by_QuotLyBot"
]

client = genai.Client(api_key=GOOGLE_API_KEY)

ZODIAC_EMOJIS = {
    "koç": "♈", "boğa": "♉", "ikizler": "♊", "yengeç": "♋", "aslan": "♌", 
    "başak": "♍", "terazi": "♎", "akrep": "♏", "yay": "♐", "oğlak": "♑", 
    "kova": "♒", "balık": "♓"
}

TAROT_CARDS = [
    "Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz",
    "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet",
    "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız",
    "Ay", "Güneş", "Mahkeme", "Dünya"
]

# --- 3. STICKER ENGELLEME MOTORU ---
async def delete_forbidden_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.sticker:
        return
    
    gelen_paket = update.message.sticker.set_name
    
    if gelen_paket in YASAKLI_PAKETLER:
        try:
            user = update.effective_user.username or update.effective_user.first_name
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"🚫 @{user}, bu sticker paketi yasaklı olduğu için mesajın silindi!"
            )
        except Exception as e:
            print(f"Sticker silme hatası: {e}")

# --- 4. KOMUT MOTORLARI ---

async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    if not target: return

    if target.photo:
        status_msg = await update.message.reply_text("🖼️ Görsel inceleniyor...")
        try:
            photo_file = await target.photo[-1].get_file()
            f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = client.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle. Maks 50 kelime.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
            await status_msg.edit_text(f"📝GÖRSEL ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Hata.")
    elif target.text or target.caption:
        status_msg = await update.message.reply_text("📝 Metin özetleniyor...")
        try:
            res = client.models.generate_content(model=MODEL_NAME, contents=f"Özetle: {target.text or target.caption}")
            await status_msg.edit_text(f"📝 METİN ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Hata.")

async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_obj = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo_obj:
        await update.message.reply_text("☕ Fal için fincan fotosu lazım canım.")
        return

    status_msg = await update.message.reply_text("☕ Telveler analiz ediliyor, sakın ayrılma...")
    try:
        photo_file = await photo_obj.get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
        prompt = "Sen dobra, detaycı eski bir Türk falcı teyzesisin. Görseldeki fincan lekelerini analiz et, 'kuş var', 'yolun kapalı' gibi spesifik ol. Maks 150 kelime."
        res = client.models.generate_content(model=MODEL_NAME, contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        await status_msg.edit_text(f"☕ Falcı Teyze diyor ki:\n\n{res.text}")
    except: await status_msg.edit_text("⚠️ Fincanı okuyamadım, enerjin çok ağır.")

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    try:
        res = client.models.generate_content(model=MODEL_NAME, contents=f"Tarot: {', '.join(secilenler)} yorumla. Maks 100 kelime.")
        await status.edit_text(f"🔮 TAROT FALI:\n\n🃏 Kartlar: {', '.join(secilenler)}\n\n📜 Yorum:\n{res.text}")
    except: await status.edit_text("Ruhlar alemine ulaşılamadı.")

# --- ✨ GÜNCEL VERİ DESTEKLİ BURÇ MOTORU ---
def get_daily_horoscope_data(burc):
    try:
        url = f"https://burc-api.vercel.app/api/{burc}"
        response = requests.get(url, timeout=5)
        return response.json().get("yorum", "") if response.status_code == 200 else ""
    except: return ""

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = update.message.text.lower()
    # Bot adını ve komutu temizle, sadece argümanları al
    temiz_args = re.sub(r'^/burcyorumla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip().split()
    
    if not temiz_args:
        await update.message.reply_text("❗ Örnek: /burcyorumla akrep")
        return
    
    burc_input = temiz_args[0]
    mapping = {"koc": "koc", "boga": "boga", "yengec": "yengec", "basak": "basak", "oglak": "oglak", "balik": "balik"}
    api_burc = mapping.get(burc_input, burc_input)
    
    status_msg = await update.message.reply_text(f"🛰️ {api_burc.capitalize()} için yıldız haritası çekiliyor...")

    try:
        raw_data = await asyncio.to_thread(get_daily_horoscope_data, api_burc)
        tz = pytz.timezone("Europe/Istanbul")
        date_str = datetime.datetime.now(tz).strftime("%d-%m-%Y")
        prompt = (f"Tarih: {date_str}. Kaynak veri: '{raw_data}'. {api_burc} burcunu bu veriye dayanarak "
                  "kendi tarzınla, derin ve güncel şekilde yeniden yorumla. Maks 100 kelime.")
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        await status_msg.edit_text(f"✨ {api_burc.upper()} YORUMU ({date_str}):\n\n{res.text}")
    except: await status_msg.edit_text("❌ Veriye ulaşılamadı.")

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # MessageHandler kullanarak bot adı zorunluluğunu siliyoruz (Regex ile yakalama)
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
    # Sticker Engelleyici ve Diğer Mesajlar
    application.add_handler(MessageHandler(filters.Sticker.ALL, delete_forbidden_stickers))
    
    print("Services Bot Tam Erişim Modunda Başlatıldı...")
    await application.initialize(); await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
