import asyncio
import nest_asyncio
import os
import random
import io
import datetime
import pytz
import re 
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. WEB SUNUCUSU ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Gerçekçi Falcı Teyze Devrede)"

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

# --- 4. DİĞER KOMUTLAR ---

async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or (not update.message.reply_to_message and not update.message.photo):
        return
    
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    
    if target.photo:
        status_msg = await update.message.reply_text("🖼️ Görsel inceleniyor...")
        try:
            photo_file = await target.photo[-1].get_file()
            f = io.BytesIO()
            await photo_file.download_to_memory(f)
            f.seek(0)
            image_bytes = f.read()
            res = client.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle. Maks 50 kelime.", types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")])
            await status_msg.edit_text(f"📝GÖRSEL ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Hata oluştu.")

    elif target.text or target.caption:
        content = target.text or target.caption
        status_msg = await update.message.reply_text("📝 Metin özetleniyor...")
        try:
            res = client.models.generate_content(model=MODEL_NAME, contents=f"Özetle: {content}")
            await status_msg.edit_text(f"📝 METİN ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Hata oluştu.")

# --- ☕ GERÇEKÇİ KAHVE FALI MOTORU ---
async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID:
        return

    if update.message.photo:
        photo_obj = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo_obj = update.message.reply_to_message.photo[-1]
    else:
        await update.message.reply_text("☕ Fal bakmam için fincan fotosu atman veya fotoya yanıt vermen lazım canım.")
        return

    status_msg = await update.message.reply_text("☕ Kahvenin buğusu dağılıyor, telveler şekilleniyor...")

    try:
        photo_file = await photo_obj.get_file()
        f = io.BytesIO()
        await photo_file.download_to_memory(f)
        f.seek(0)
        image_bytes = f.read()

        # Sertleştirilmiş ve Detaycı Prompt
        prompt_text = (
            "Sen geleneksel, dobra, her şeyi olduğu gibi söyleyen eski bir Türk falcı teyzesisin. "
            "Görsele çok dikkatli bak. Sadece 'ne güzel fal' diyerek geçiştirme, gerçek bir falcı gibi eleştir. "
            "GÖREVLERİN: "
            "1. Fincandaki lekeleri analiz et. Örneğin; 'Kenarda bir kuş kabarmış', 'Dibe doğru bir karartı çökmüş', 'Şurada bir E harfi gördüm' gibi spesifik konuş. "
            "2. Gördüğün bu şekilleri; Aşk, Para, Yol ve Hanedeki huzur ile ilişkilendir. "
            "3. Eğer fincan çok karışıksa 'Ay için çok şişmiş, dertlerin üst üste binmiş' de. "
            "4. 'Nazar var sende evladım', 'Yolun kapalı ama bir haber bekliyorsun' gibi geleneksel ve gizemli tabirler kullan. "
            "5. Samimi ama ciddi ol. Maksimum 150 kelime. "
            "6. Eğer görsel kahve fincanı değilse 'Evladım bu kahve değil ki ben buna nasıl bakayım?' diyerek sitem et."
        )

        res = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_text(text=prompt_text),
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                    ]
                )
            ],
            config=types.GenerateContentConfig(safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')])
        )

        await status_msg.edit_text(f"☕ Falcı Teyze diyor ki:\n\n{res.text}")

    except Exception as e:
        print(f"Fal hatası: {e}")
        await status_msg.edit_text("⚠️ Enerjin çok ağır geldi evladım, fincanı okuyamadım.")

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID: return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    prompt = f"Tarot falı yorumla. Kartlar: Geçmiş: {secilenler[0]}, Şimdi: {secilenler[1]}, Gelecek: {secilenler[2]}. Mistik ve samimi dille maks 100 kelime."
    try:
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        await status.edit_text(f"🔮 TAROT FALI:\n\n🃏 Kartlar: {', '.join(secilenler)}\n\n📜 Yorum:\n{res.text}")
    except: await status.edit_text("Ruhlar alemine ulaşılamadı.")

# --- ✨ DİNAMİK BURÇ MOTORU ---
async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID: return
    metin = update.message.text.lower()
    temiz_metin = re.sub(r'^/burcyorumla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    args = temiz_metin.split()
    
    if not args:
        await update.message.reply_text("❗ Örnek kullanım: /burcyorumla koc")
        return
    
    burc = args[0]
    mapping = {"koc": "koç", "boga": "boğa", "yengec": "yengeç", "basak": "başak", "oglak": "oğlak", "balik": "balık"}
    if burc in mapping: burc = mapping[burc]
    if burc not in ZODIAC_EMOJIS:
        await update.message.reply_text("❗ Geçerli bir burç yazmalısın evladım.")
        return
    
    tur = "günlük"
    if len(args) > 1 and args[1] in ["haftalik", "haftalık"]: tur = "haftalık"

    status_msg = await update.message.reply_text(f"{ZODIAC_EMOJIS[burc]} {burc.capitalize()} için yıldızlar sorgulanıyor...")

    try:
        tz = pytz.timezone("Europe/Istanbul")
        date_str = datetime.datetime.now(tz).strftime("%d-%m-%Y")
        prompt = (f"Tarih: {date_str}. {burc} burcu için {tur} astrolojik yorum yap. "
                  "Güncel gezegen dizilimlerini düşün. Maks 80 kelime. Her gün benzersiz yorum yap.")
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        await status_msg.edit_text(f"✨ {burc.upper()} {tur.upper()} YORUMU ({date_str}):\n\n{res.text}")
    except: await status_msg.edit_text("❌ Yıldızlar bugün görünmüyor.")

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Tüm Komutları Regex İle Yakalıyoruz (Çoklu Bot Engelini Aşar)
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
    # Sticker Engelleyici
    application.add_handler(MessageHandler(filters.Sticker.ALL, delete_forbidden_stickers))
    
    print("Services Bot Başlatıldı...")
    await application.initialize(); await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
