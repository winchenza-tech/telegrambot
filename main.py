import os
import re 
import io
import random
import time 
import asyncio
import nest_asyncio
import datetime
import pytz
import html 
import json 
from collections import deque 
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from google import genai
from google.genai import types

# --- 1. AYARLAR VE GLOBAL DEĞİŞKENLER ---
UPDATE_HOUR = 2  
ADMIN_IDS = [7094870780, 8639720888]  
ALLOWED_GROUPS = [-1003938704852, -1003297262036] 

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Zenithar Services Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

nest_asyncio.apply()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

MODEL_NAME = 'gemini-2.5-flash'
client = genai.Client(api_key=GOOGLE_API_KEY)

VALID_ZODIACS = ["koc", "boga", "ikizler", "yengec", "aslan", "basak", "terazi", "akrep", "yay", "oglak", "kova", "balik"]
HOROSCOPE_CACHE = {burc: "" for burc in VALID_ZODIACS}
IS_UPDATING = False 
BACKGROUND_TASKS = set() 
TAROT_CARDS = ["Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz", "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet", "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız", "Ay", "Güneş", "Mahkeme", "Dünya"]
RECENT_MESSAGES = {group_id: deque(maxlen=10) for group_id in ALLOWED_GROUPS}
MESSAGE_LOOKUP = {} 
RPG_GAMES = {}
RPG_SCORES = {} 

# --- 2. YARDIMCI FONKSİYONLAR ---

async def safe_generate(contents, config=None, retries=5):
    for attempt in range(retries):
        try:
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=contents, config=config)
            _ = res.text 
            return res
        except Exception as e:
            if attempt == retries - 1: raise e 
            await asyncio.sleep(5) 

def turkce_karakter_duzelt(metin):
    metin = metin.lower().strip()
    duzeltmeler = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'i̇': 'i'}
    for kaynak, hedef in duzeltmeler.items(): metin = metin.replace(kaynak, hedef)
    return metin

async def check_access(update: Update) -> bool:
    if not update.effective_message: return False
    chat_id = update.effective_chat.id
    if update.effective_chat.type == 'private':
        if update.effective_user.id not in ADMIN_IDS: return False
    else:
        if chat_id not in ALLOWED_GROUPS: return False
    return True

# --- 3. RPG OYUN MOTORU ---

async def run_rpg_game(chat_id, context):
    try:
        await asyncio.sleep(60) 
        game = RPG_GAMES.get(chat_id)
        if not game: return
        player_count = len(game["players"])
        if player_count < 3:
            await context.bot.send_message(chat_id, f"⚠️ Oyun iptal! En az 3 kişi lazım (Şu an: {player_count}).")
            RPG_GAMES.pop(chat_id, None); return
            
        game["status"] = "playing"; players = game["players"]; scenario = game["scenario"]
        player_names = ", ".join([p["name"] for p in players.values()])
        round_points = {1: 10, 2: 20, 3: 30, 4: 40}
        
        for round_num in range(1, 5):
            game["round"] = round_num
            alive_players = [p for p in players.values() if p["status"] == "alive"]
            if not alive_players: break
                
            actions_text = ""
            if round_num > 1:
                for p in alive_players: actions_text += f"{p['name']}: {p['action'] if p['action'] else '(Beklemede)'}\n"

            game["recorded_actions"] = [] 
            for uid in players: players[uid]["action"] = None

            if round_num == 1:
                prompt = f"RPG Başla. Senaryo: {scenario}. Karakterler: {player_names}. DM olarak karakterleri bir arada veya birbirini görecek şekilde başlat. Senaryo 30-40 kelime, durumlar 30 kelime. İsimleri <b>isim</b> yap. ASLA yıldız(*) kullanma. 'ÖLENLER: Yok' ile başla."
            elif round_num < 4:
                prompt = f"Senaryo: {scenario}. Tur: {round_num}. Hamleler:\n{actions_text}\nDeğerlendirme yap. Karakterlerden bahsederken etiketleme (mention) formatında yaz. Senaryo 30-40, durumlar 30 kelime. İsimleri <b>isim</b> yap. En başa 'ÖLENLER: isim' yaz."
            else:
                prompt = f"FİNAL TURU! Hamleler:\n{actions_text}\nKarakterleri etiketleyerek epik sonu yaz. 1-2 kazanan olsun. İsimler <b>isim</b> olsun. En başa 'ÖLENLER: isimler' yaz."
                
            res = await safe_generate(contents=prompt, config=types.GenerateContentConfig(safety_settings=[types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'), types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE')]))
            text = res.text
            
            if "ÖLENLER:" in text.upper():
                dead_line = next((l for l in text.split('\n') if l.upper().startswith("ÖLENLER:")), "")
                clean_dead = dead_line.replace('<b>','').replace('</b>','')
                for uid, p in players.items():
                    if p["name"].lower() in clean_dead.lower(): p["status"] = "dead"
                display_text = "\n".join([l for l in text.split('\n') if not l.upper().startswith("ÖLENLER:")]).strip()
            else: display_text = text

            current_alive = [uid for uid, p in players.items() if p["status"] == "alive"]
            if player_count >= 4:
                pts = round_points.get(round_num, 0)
                if round_num == 4 and len(current_alive) <= 2: pts = 70
                for uid in current_alive:
                    if uid not in RPG_SCORES: RPG_SCORES[uid] = {"name": players[uid]["name"], "score": 0}
                    RPG_SCORES[uid]["score"] += pts
                    game["round_points_log"][uid] += pts

            display_text = html.escape(display_text).replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
            alive_tags = "🟢 <b>Hayatta:</b> " + ", ".join([f"<a href='tg://user?id={u}'>{html.escape(players[u]['name'])}</a>" for u in current_alive])
            
            msg_text = f"🎲 <b>TUR {round_num}/4</b>\n\n{display_text}\n\n{alive_tags}\n\n⏳ 90sn içinde REPLY yap!"
            if round_num == 4: msg_text = f"🚨 <b>FİNAL</b>\n\n{display_text}\n\n{alive_tags}"

            game["current_caption"] = msg_text
            msg = await context.bot.send_message(chat_id, msg_text, parse_mode='HTML')
            game["last_message_id"] = msg.message_id
            if round_num < 4: await asyncio.sleep(90) 
        RPG_GAMES.pop(chat_id, None)
    except: RPG_GAMES.pop(chat_id, None)

# --- 4. FAL VE TAROT MOTORU ---

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar seçiliyor...")
    cards_str = " | ".join(secilenler)
    prompt = f"Seçilen Tarot Kartları: {cards_str}. Bu kartları geçmiş, şimdi ve gelecek olarak çok samimi, sıcak, sanki yakın bir dostunmuşsun gibi Türkçe yorumla. Maks 130 kelime. Paragrafların başına emoji koy ve ASLA yıldız(*) kullanma."
    try:
        res = await safe_generate(contents=prompt)
        await status.edit_text(f"🔮 <b>TAROT FALI</b>\n\n🃏 <b>Seçilen Kartlar:</b> {cards_str}\n\n{res.text}", parse_mode="HTML")
    except: await status.edit_text("Bağlantı koptu canım, sonra dene.")

async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    photo = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo: await update.message.reply_text("Fincan fotosu nerede?"); return
    status = await update.message.reply_text("☕ Bakalım neler çıkmış...")
    try:
        file = await photo.get_file(); f = io.BytesIO(); await file.download_to_memory(f); f.seek(0)
        prompt = "Kahve falını mahalle falcısı teyze gibi çok samimi, dobra ve eğlenceli bir dille yorumla. Maks 150 kelime. Paragraflı olsun, yıldız(*) kullanma."
        res = await client.aio.models.generate_content(model=MODEL_NAME, contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        await status.edit_text(f"☕ <b>FALCI TEYZE DİYOR Kİ:</b>\n\n{res.text}", parse_mode="HTML")
    except: await status.edit_text("Fincanı okuyamadım şekerim.")

# --- DİĞER KOMUTLAR VE ANA DÖNGÜ ---

async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_chat: return
    chat_id = update.effective_chat.id
    if chat_id in ALLOWED_GROUPS:
        msg = update.effective_message
        if chat_id in RPG_GAMES and RPG_GAMES[chat_id]["status"] == "playing":
            game = RPG_GAMES[chat_id]
            if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
                uid = update.effective_user.id
                if uid in game["players"] and game["players"][uid]["status"] == "alive" and game["players"][uid]["action"] is None:
                    game["players"][uid]["action"] = msg.text or msg.caption
                    game["recorded_actions"].append(game["players"][uid]["name"])
                    cap = game["current_caption"] + "\n\n✅ <b>Hamle:</b> " + ", ".join(game["recorded_actions"])
                    try: await context.bot.edit_message_text(cap, chat_id, game["last_message_id"], parse_mode='HTML')
                    except: pass

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CallbackQueryHandler(rpg_callback, pattern='^rpg_'))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/rpg'), rpg_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & (~filters.COMMAND), log_message))
    await application.initialize(); await application.start()
    await application.updater.start_polling()
    while True: await asyncio.sleep(3600)

if __name__ == "__main__": asyncio.run(main())
