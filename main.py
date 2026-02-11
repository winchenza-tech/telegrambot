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
def home(): return "Zenithar Services Aktif! (Tarot, Burç, Özetleme ve Sticker Engelleyici)"

def run_flask():
    port = int(os.environ.get("PORT", 8081))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_flask).start()

# --- 2. AYARLAR ---
nest_asyncio.apply()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES") # Services Bot Token
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
AUTHORIZED_GROUP_ID = -1003297262036 # Es Justo Grup ID

# --- 🚫 YASAKLI STICKER PAKETLERİ ---
YASAKLI_PAKETLER = [
    "OldiesButGoldies5",
    "ino8723",
    "gq0bpksh8_1003369169896_by_QuotLyBot"
]

client = genai.Client(api_key=GOOGLE_API_KEY)

ZODIAC_EMOJIS = {"koç": "♈", "boğa": "♉", "ikizler": "♊", "yengeç": "♋", "aslan": "♌", "başak": "♍", "terazi": "♎", "akrep": "♏", "yay": "♐", "oğlak": "♑", "kova": "♒", "balık": "♓"}
TAROT_CARDS = ["Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz", "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet", "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız", "Ay", "Güneş", "Mahkeme", "Dünya"]

# --- 3. STICKER ENGELLEME MOTORU ---
async def delete_forbidden_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.sticker: return
    
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
            f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = client.models.generate_content(model='gemini-2.5-flash', contents=[types.Part.from_text(text="Bu resmi Türkçe özetle. Maks 50 kelime."), types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
            await status_msg.edit_text(f"📝GÖRSEL ÖZETİ:\n\n{res.text}")
        except Exception as e: await status_msg.edit_text(f"⚠️ Hata: {e}")
    elif target.text or target.caption:
        status_msg = await update.message.reply_text("📝 Metin özetleniyor...")
        try:
            res = client.models.generate_content(model='gemini-2.5-flash', contents=f"Özetle: {target.text or target.caption}")
            await status_msg.edit_text(f"📝 METİN ÖZETİ:\n\n{res.text}")
        except: pass

async def tarot_command(update, context):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID: return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text(f"🃏Kartlar karıştırılıyor...")
    prompt = f"Tarot falı yorumla. Kartlar: Geçmiş: {secilenler[0]}, Şimdi: {secilenler[1]}, Gelecek: {secilenler[2]}. Mistik bir dille maks 100 kelime."
    try:
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        await status.edit_text(f"🔮TAROT FALI:\n\n🃏 Kartlar: {', '.join(secilenler)}\n\n📜 Yorum:\n{res.text}")
    except: pass

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_GROUP_ID or not context.args: return
    burc = context.args[0].lower()
    if burc not in ZODIAC_EMOJIS: return
    keyboard = [[InlineKeyboardButton("Günlük", callback_data=f"gunluk|{burc}"), InlineKeyboardButton("Haftalık", callback_data=f"haftalik|{burc}")]]
    await update.message.reply_text(f"{ZODIAC_EMOJIS[burc]} {burc.upper()} periyot seç:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    tur, burc = query.data.split("|")
    prompt = f"{burc} burcu için {tur} astrolojik yorum yap. Maks 70 kelime."
    try:
        await query.edit_message_text("🌟 Yıldızlar hizalanıyor...")
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        await query.edit_message_text(text=f"✨ {burc.upper()} {tur.upper()} YORUMU:\n\n{res.text}")
    except: pass

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Komutlar
    app.add_handler(CommandHandler("tarotbak", tarot_command))
    app.add_handler(CommandHandler("burcyorumla", burcyorumla_command))
    app.add_handler(CommandHandler("ozetle", ozetle_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Sticker Engelleyici (Her sticker mesajını dinler)
    app.add_handler(MessageHandler(filters.Sticker.ALL, delete_forbidden_stickers))
    
    await app.initialize(); await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except:
        pass
