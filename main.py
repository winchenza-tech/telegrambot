import asyncio
import nest_asyncio
import os
import random
import io
import datetime
import pytz
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. WEB SUNUCUSU (Port: 8081) ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Tarot, Burç, Özetleme ve Sticker Engelleyici)"

def run_flask():
    port = int(os.environ.get("PORT", 8081))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- 2. AYARLAR ---
nest_asyncio.apply()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  # Services Bot Token
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
AUTHORIZED_GROUP_ID = -1003297262036  # Es Justo Grup ID

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
    if not update.message.reply_to_message:
        await update.message.reply_text("❗ Bir mesaja (metin veya resim) yanıt vererek kullan.")
        return
    
    target = update.message.reply_to_message
    
    if target.photo:
        status_msg = await update.message.reply_text("🖼️ Görsel inceleniyor...")
        try:
            photo_file = await target.photo[-1].get_file()
            f = io.BytesIO()
            await photo_file.download_to_memory(f)
            f.seek(0)
            image_bytes = f.read()

            prompt_text = "Bu resmi Türkçe özetle. Maks 50 kelime."

            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_text(text=prompt_text),
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')]
                )
            )
            await status_msg.edit_text(f"📝GÖRSEL ÖZETİ:\n\n{res.text}")
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Hata: {e}")

    elif target.text or target.caption:
        content = target.text or target.caption
        status_msg = await update.message.reply_text("📝 Metin özetleniyor...")
        try:
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Özetle: {content}",
                config=types.GenerateContentConfig(
                    safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')]
                )
            )
            await status_msg.edit_text(f"📝 METİN ÖZETİ:\n\n{res.text}")
        except:
            pass
    else:
        await update.message.reply_text("❌ Özetlenecek metin veya görsel bulunamadı.")

async def tarot_command(update, context):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID:
        return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    prompt = f"Tarot falı yorumla. Kartlar: Geçmiş: {secilenler[0]}, Şimdi: {secilenler[1]}, Gelecek: {secilenler[2]}. Mistik bir dille maks 100 kelime."
    try:
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')]
            )
        )
        await status.edit_text(f"🔮 TAROT FALI:\n\n🃏 Kartlar: {', '.join(secilenler)}\n\n📜 Yorum:\n{res.text}")
    except:
        await status.edit_text("Ruhlar alemine ulaşılamadı.")

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID or not context.args:
        return
    
    burc = context.args[0].lower()
    if burc not in ZODIAC_EMOJIS:
        await update.message.reply_text("Lütfen geçerli bir burç adı girin.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("Günlük", callback_data=f"gunluk|{burc}"),
            InlineKeyboardButton("Haftalık", callback_data=f"haftalik|{burc}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"{ZODIAC_EMOJIS[burc]} {burc.upper()} periyot seç:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    tur, burc = query.data.split("|")
    prompt = f"{burc} burcu için {tur} astrolojik yorum yap. Maks 70 kelime."
    try:
        await query.edit_message_text(f"{ZODIAC_EMOJIS.get(burc, '')} Yıldızlar hizalanıyor...")
        res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')]
            )
        )
        await query.edit_message_text(text=f"✨ {burc.upper()} {tur.upper()} YORUMU:\n\n{res.text}")
    except:
        await query.edit_message_text(text="Yıldız bağlantısı koptu.")

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Komutlar
    application.add_handler(CommandHandler("tarotbak", tarot_command))
    application.add_handler(CommandHandler("burcyorumla", burcyorumla_command))
    application.add_handler(CommandHandler("ozetle", ozetle_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Sticker Engelleyici
    application.add_handler(MessageHandler(filters.Sticker.ALL, delete_forbidden_stickers))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Kritik Hata: {e}")
