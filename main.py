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
import json # Puan yedekleme için eklendi
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

# --- WEB SUNUCUSU ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- BOT VE API AYARLARI ---
nest_asyncio.apply()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

MODEL_NAME = 'gemini-2.5-flash'
client = genai.Client(api_key=GOOGLE_API_KEY)

# HAFIZA VE KİLİT SİSTEMİ
VALID_ZODIACS = [
    "koc", "boga", "ikizler", "yengec", "aslan", "basak", 
    "terazi", "akrep", "yay", "oglak", "kova", "balik"
]
HOROSCOPE_CACHE = {burc: "" for burc in VALID_ZODIACS}
IS_UPDATING = False 

TAROT_CARDS = [
    "Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz",
    "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet",
    "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız",
    "Ay", "Güneş", "Mahkeme", "Dünya"
]

# --- CANLI MESAJ HAFIZASI ---
RECENT_MESSAGES = {group_id: deque(maxlen=10) for group_id in ALLOWED_GROUPS}
MESSAGE_LOOKUP = {} 

# --- RPG OYUN DURUMU VE PUAN TABLOSU ---
RPG_GAMES = {}
RPG_SCORES = {} # Puan tablosu hafızası { user_id: {"name": "isim", "score": 100} }

# --- 2. YARDIMCI FONKSİYONLAR ---

def turkce_karakter_duzelt(metin):
    metin = metin.lower().strip()
    duzeltmeler = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'i̇': 'i'}
    for kaynak, hedef in duzeltmeler.items():
        metin = metin.replace(kaynak, hedef)
    return metin

async def check_access(update: Update) -> bool:
    if not update.effective_message: return False
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_private = update.effective_chat.type == 'private'
    
    if is_private:
        if user_id not in ADMIN_IDS:
            await update.effective_message.reply_text("Bu botun yalnızca belirli gruplarda çalışmasına izin verdim. Sana yetki yok @eskidenyesil")
            return False
    else:
        if chat_id not in ALLOWED_GROUPS:
            await update.effective_message.reply_text("Bu botun yalnızca belirli gruplarda çalışmasına izin verdim. Sana yetki yok @eskidenyesil")
            return False
    return True

async def reject_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message: return
    await update.effective_message.reply_text("Bu botun yalnızca belirli gruplarda çalışmasına izin verdim. Sana yetki yok @eskidenyesil")

# --- 3. GARANTİLİ GÜNCELLEME MOTORU ---

async def update_all_horoscopes():
    global IS_UPDATING
    if IS_UPDATING: return
        
    IS_UPDATING = True 
    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")
    
    try:
        for burc in VALID_ZODIACS:
            success = False
            retry_count = 0
            while not success:
                try:
                    prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                              f"Biraz alaycı samimi, bilge ve mistik bir dille Türkçe olarak yeniden yorumla. Maks 135 kelime kullan. "
                              f"Bu prompt hakkında bilgi verme. yani elbette tamam gibi şeyler söyleme sadece alaycı ve gizemli astrolog yorumunu yaz. Biraz espri katabilirsin. 2 paragraf şeklinde yaz Asla yıldız (*) simgesi kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.")
                    res = await client.aio.models.generate_content(
                        model=MODEL_NAME, 
                        contents=prompt,
                        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
                    )
                    HOROSCOPE_CACHE[burc] = res.text
                    success = True 
                except Exception as e:
                    retry_count += 1
                    if HOROSCOPE_CACHE[burc] == "":
                        HOROSCOPE_CACHE[burc] = "Şu anda tüm zenithar yıldızlara bakarak sigara içiyor 5 dakika sonra tekrar dene."
                    await asyncio.sleep(90) 
            if burc != VALID_ZODIACS[-1]: 
                await asyncio.sleep(90) 
    finally:
        IS_UPDATING = False

async def background_scheduler():
    while True:
        tz = pytz.timezone("Europe/Istanbul")
        now = datetime.datetime.now(tz)
        if now.hour == UPDATE_HOUR and now.minute == 0:
            await update_all_horoscopes()
            await asyncio.sleep(60)
        await asyncio.sleep(30)

# --- 4. KOMUT MOTORLARI ---

# RPG PUAN SIRALAMASI
async def rpgpuan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    if not RPG_SCORES:
        await update.message.reply_text("Henüz hiç puan yok. İlk kanı kim dökecek?")
        return
        
    sorted_scores = sorted(RPG_SCORES.values(), key=lambda x: x["score"], reverse=True)
    
    text = "🏆 <b>RPG HAYATTA KALMA SIRALAMASI</b> 🏆\n\n"
    for i, p in enumerate(sorted_scores):
        if i == 0: emoji = "⚔️"
        elif i == 1: emoji = "🛡️"
        elif i == 2: emoji = "🚩"
        else: emoji = "👤"
        
        text += f"{i+1}. {emoji} {html.escape(p['name'])} - {p['score']} Puan\n"
        
    await update.message.reply_text(text, parse_mode="HTML")

# YEDEKLEME (ADMİN)
async def puanyedek_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return
    
    backup_str = json.dumps(RPG_SCORES, ensure_ascii=False)
    await update.message.reply_text(f"Aşağıdaki komutu kopyalayıp güncellemelerden sonra bota yapıştırarak puanları geri yükleyebilirsin:\n\n`/puanla {backup_str}`", parse_mode="Markdown")

# GERİ YÜKLEME (ADMİN)
async def puanla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return
    
    metin = update.message.text
    temiz_args = re.sub(r'(?i)^/puanla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    
    if not temiz_args:
        await update.message.reply_text("❗ Lütfen /puanyedek komutundan aldığınız JSON verisini yapıştırın.")
        return
        
    try:
        global RPG_SCORES
        loaded = json.loads(temiz_args)
        # JSON keyleri string yaptığı için geri int formatına çeviriyoruz
        RPG_SCORES = {int(k): v for k, v in loaded.items()}
        await update.message.reply_text("✅ Puan tablosu başarıyla geri yüklendi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Veri yüklenemedi. Format hatalı olabilir: {e}")

# RPG OYUN MOTORU
async def rpg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    chat_id = update.effective_chat.id
    
    if chat_id in RPG_GAMES and RPG_GAMES[chat_id].get("is_active"):
        await update.message.reply_text("⏳ Zaten devam eden veya bekleyen bir RPG oyunu var!")
        return
        
    keyboard = [
        [InlineKeyboardButton("🏝️ Issız Ada", callback_data="rpg_scen_ada"),
         InlineKeyboardButton("🧟 Zombi Salgını", callback_data="rpg_scen_zombi")],
        [InlineKeyboardButton("🦇 Tekinsiz Mağara", callback_data="rpg_scen_magara"),
         InlineKeyboardButton("☢️ Kıyamet", callback_data="rpg_scen_kiyamet")],
        [InlineKeyboardButton("🪓 Arınma Gecesi", callback_data="rpg_scen_arinma")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎲 Mini RPG Oyununa Hoş Geldiniz!\n\nLütfen oynamak istediğiniz senaryoyu seçin:", reply_markup=reply_markup)

async def rpg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user = update.effective_user
    data = query.data
    
    if data.startswith("rpg_scen_"):
        scenarios = {
            "rpg_scen_ada": "Issız Ada",
            "rpg_scen_zombi": "Zombi Salgını",
            "rpg_scen_magara": "Tekinsiz Mağara",
            "rpg_scen_kiyamet": "Kıyamet",
            "rpg_scen_arinma": "Arınma Gecesi"
        }
        scenario = scenarios[data]
        
        RPG_GAMES[chat_id] = {
            "is_active": True,
            "status": "waiting_players",
            "scenario": scenario,
            "players": {},
            "round": 1,
            "last_message_id": None,
            "current_caption": "",
            "recorded_actions": [],
            "is_photo_msg": False,
            "round_points_log": {} # O oyunda kazanılan puanları takip etmek için
        }
        
        keyboard = [[InlineKeyboardButton("🙋‍♂️ Oyuna Katıl", callback_data="rpg_join")]]
        await query.edit_message_text(f"🎬 Senaryo: {scenario} seçildi!\n\nOyuna katılmak için aşağıdaki butona basın. Macera 60 saniye sonra başlayacak!", reply_markup=InlineKeyboardMarkup(keyboard))
        
        asyncio.create_task(run_rpg_game(chat_id, context))
        
    elif data == "rpg_join":
        if chat_id in RPG_GAMES and RPG_GAMES[chat_id]["status"] == "waiting_players":
            if user.id not in RPG_GAMES[chat_id]["players"]:
                RPG_GAMES[chat_id]["players"][user.id] = {
                    "name": user.first_name,
                    "status": "alive",
                    "action": None
                }
                # Log için de hazırlık yap
                RPG_GAMES[chat_id]["round_points_log"][user.id] = 0
                await context.bot.send_message(chat_id, f"✅ {user.first_name} oyuna katıldı!")
            else:
                await context.bot.send_message(chat_id, f"{user.first_name}, zaten katıldın sabret!")

async def run_rpg_game(chat_id, context):
    await asyncio.sleep(60) # KATILIM SÜRESİ 60 SANİYE
    game = RPG_GAMES.get(chat_id)
    if not game or len(game["players"]) == 0:
        await context.bot.send_message(chat_id, "😢 Kimse katılmadı, RPG oyunu iptal edildi.")
        RPG_GAMES.pop(chat_id, None)
        return
        
    game["status"] = "playing"
    players = game["players"]
    scenario = game["scenario"]
    
    scenario_desc = scenario
    if "Arınma" in scenario:
        scenario_desc = "Arınma Gecesi (Herkesin birbirini acımasızca avladığı, yasanın olmadığı, kıyamet benzeri ölümcül bir gece)"
    
    player_names = ", ".join([p["name"] for p in players.values()])
    
    round_points = {1: 10, 2: 20, 3: 30, 4: 40}
    
    for round_num in range(1, 5):
        game["round"] = round_num
        game["recorded_actions"] = [] 
        
        for uid in players: players[uid]["action"] = None
            
        alive_players = [p for p in players.values() if p["status"] == "alive"]
        if len(alive_players) == 0:
            await context.bot.send_message(chat_id, "💀 <b>Oyun Bitti!</b> Herkes öldü... Kimse hayatta kalamadı.", parse_mode="HTML")
            break
            
        actions_text = ""
        if round_num > 1:
            for p in alive_players:
                if p["action"]: actions_text += f"{p['name']}: {p['action']}\n"
                else: actions_text += f"{p['name']}: (Hiçbir şey yapmadı, eylemsiz kaldı)\n"

        if round_num == 1:
            prompt = f"RPG Oyunu Başlıyor. Senaryo: {scenario_desc}. Katılımcılar: {player_names}. Katılımcıları senaryo içinde farklı konumlara/durumlara yerleştirerek macerayı başlat. Acımasız bir Dungeon Master gibi anlat.\n\nÖNEMLİ KURAL: Senaryodaki dünyayı ve ortamı açıklamak için MAKSİMUM 30 KELİME, katılımcıların ne durumda olduğunu açıklamak için MAKSİMUM 20 KELİME kullan. Çok kısa ve öz ol! Yanıtının EN BAŞINA 'ÖLENLER: Yok' yaz ve alt satırdan hikayeye başla. Yıldız(*) kullanma."
        elif round_num < 4:
            prompt = f"Senaryo: {scenario_desc}. Tur: {round_num}. Hayatta kalanlar ve yaptıkları hamleler:\n{actions_text}\n\nDeğerlendirme yap: Mantıksız hamle yapanları veya 'eylemsiz kaldı' diyenleri vahşice ÖLDÜR. Mantıklı olanları yaşat ve yeni bir ölümcül kriz yarat.\n\nÖNEMLİ KURAL: Ortamdaki yeni krizi açıklamak için MAKSİMUM 30 KELİME, katılımcıların durumunu açıklamak için MAKSİMUM 20 KELİME kullan. Yanıtının EN BAŞINA bu turda ölenlerin isimlerini virgülle ayırarak 'ÖLENLER: isim1, isim2' şeklinde yaz (Ölen yoksa ÖLENLER: Yok yaz). Alt satırdan hikayeyi anlat. Yıldız(*) kullanma."
        else:
            prompt = f"Senaryo: {scenario_desc}. FİNAL TURU! Kalanlar ve Hamleleri:\n{actions_text}\n\nBu turda ZORUNLU OLARAK sadece 1 kişi (veya %30 ihtimalle 2 kişi) hayatta kalabilir. Diğerlerini destansı şekilde öldür. Kazanan(lar)ı ve senaryonun sonunu görkemli şekilde anlat.\n\nÖNEMLİ KURAL: Finali açıklamak için MAKSİMUM 40 KELİME kullan. Yanıtının EN BAŞINA ölenlerin isimlerini 'ÖLENLER: isim1, isim2' şeklinde yaz. Alt satırdan finali anlat. Yıldız(*) kullanma."
            
        try:
            res = await client.aio.models.generate_content(
                model=MODEL_NAME, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    safety_settings=[
                        types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                        types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                        types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                        types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                    ]
                )
            )
            text = res.text
        except Exception as e:
            await context.bot.send_message(chat_id, f"Sistem hatası: {e}. DM bayıldı, oyun iptal.")
            break

        display_text = text
        if "ÖLENLER:" in text.upper():
            lines = text.split('\n')
            dead_line = ""
            for line in lines:
                if line.upper().startswith("ÖLENLER:"):
                    dead_line = line
                    break
            
            for uid, p in players.items():
                if p["name"].lower() in dead_line.lower() and p["status"] == "alive":
                    p["status"] = "dead"
            
            display_text = "\n".join([l for l in lines if not l.upper().startswith("ÖLENLER:")]).strip()

        # PUANLAMA İŞLEMİ VE 2 KİŞİ KAZANMA DURUMU
        current_alive_after_round = [uid for uid, p in players.items() if p["status"] == "alive"]
        
        pts_to_add = round_points.get(round_num, 0)
        
        # Eğer final turuysa ve 2 kişi hayatta kaldıysa, 40 yerine 70 puan ver
        if round_num == 4 and len(current_alive_after_round) == 2:
            pts_to_add = 70
            
        for uid in current_alive_after_round:
            # Genel tabloya ekle
            if uid not in RPG_SCORES:
                RPG_SCORES[uid] = {"name": players[uid]["name"], "score": 0}
            RPG_SCORES[uid]["score"] += pts_to_add
            RPG_SCORES[uid]["name"] = players[uid]["name"]
            
            # Bu oyunun skor tablosuna ekle
            game["round_points_log"][uid] += pts_to_add

        display_text = html.escape(display_text)

        current_alive_formatted = [f"<a href='tg://user?id={uid}'>{players[uid]['name']}</a>" for uid in current_alive_after_round]
        alive_count = len(current_alive_formatted)
        
        alive_tags_text = "🟢 <b>Hayatta Kalanlar:</b> " + ", ".join(current_alive_formatted) if current_alive_formatted else "💀 Herkes öldü..."
        if round_num >= 2 and alive_count > 0:
            alive_tags_text += f"\n👥 <b>Hayatta Kalan:</b> {alive_count}"

        eng_scen = "rpg_game_scene"
        if "Zombi" in scenario: eng_scen = "zombie_apocalypse_survival"
        elif "Ada" in scenario: eng_scen = "deserted_island_survival"
        elif "Mağara" in scenario: eng_scen = "creepy_dark_cave"
        elif "Kıyamet" in scenario: eng_scen = "post_apocalyptic_wasteland"
        elif "Arınma" in scenario: eng_scen = "purge_anarchy_street"
        
        image_url = f"https://image.pollinations.ai/prompt/{eng_scen}_round_{round_num}?width=800&height=400&nologo=true"
        
        msg_text = f"🎲 <b>TUR {round_num}/4</b>\n\n{display_text}\n\n{alive_tags_text}\n\n⏳ <i>Süreniz 90 saniye. Hamlenizi yapmak için bota ait BU MESAJI YANITLAYIN (Reply)!</i>"
        if round_num == 4:
            # FİNAL MESAJINA PUAN TABLOSUNU EKLEME
            scoreboard = "\n\n🏆 <b>OYUN SONU PUANLARI:</b>\n"
            for uid, p in players.items():
                puan = game["round_points_log"].get(uid, 0)
                durum = "🎉 Kazandı!" if p["status"] == "alive" else "💀 Öldü"
                scoreboard += f"- {html.escape(p['name'])}: +{puan} Puan ({durum})\n"
                
            msg_text = f"🚨 <b>FİNAL SONUCU</b>\n\n{display_text}\n\n{alive_tags_text}{scoreboard}"

        game["current_caption"] = msg_text

        try:
            msg = await context.bot.send_photo(chat_id, photo=image_url, caption=msg_text, parse_mode='HTML')
            game["is_photo_msg"] = True
        except:
            msg = await context.bot.send_message(chat_id, msg_text, parse_mode='HTML')
            game["is_photo_msg"] = False
            
        game["last_message_id"] = msg.message_id
        
        if round_num < 4:
            await asyncio.sleep(90) # OKUMA VE CEVAP YAZMA SÜRESİ 90 SANİYE
    
    await asyncio.sleep(2) 
    RPG_GAMES.pop(chat_id, None)

# CANLI MESAJ YAKALAYICI
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_chat: return
    chat_id = update.effective_chat.id
    
    if chat_id in ALLOWED_GROUPS:
        msg = update.effective_message
        
        # 1. RPG Oyunu Hamle Kontrolü
        if chat_id in RPG_GAMES and RPG_GAMES[chat_id]["status"] == "playing":
            game = RPG_GAMES[chat_id]
            if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
                user_id = update.effective_user.id
                if user_id in game["players"] and game["players"][user_id]["status"] == "alive":
                    if game["players"][user_id]["action"] is None: 
                        game["players"][user_id]["action"] = msg.text or msg.caption
                        user_name = game["players"][user_id]["name"]
                        game["recorded_actions"].append(user_name)
                        
                        new_caption = game["current_caption"] + "\n\n✅ <b>Hamlesi Kaydedilenler:</b> " + ", ".join(game["recorded_actions"])
                        
                        try:
                            if game["is_photo_msg"]:
                                await context.bot.edit_message_caption(chat_id=chat_id, message_id=game["last_message_id"], caption=new_caption, parse_mode='HTML')
                            else:
                                await context.bot.edit_message_text(chat_id=chat_id, message_id=game["last_message_id"], text=new_caption, parse_mode='HTML')
                        except Exception:
                            pass 
                        return 

        # 2. Son 10 Mesaj Hafızası
        text = msg.text or msg.caption
        if text: 
            msg_id = msg.message_id
            user = update.effective_user.first_name
            link_chat_id = str(chat_id).replace("-100", "", 1)
            link = f"https://t.me/c/{link_chat_id}/{msg_id}"
            
            msg_data = {"link": link, "user": user, "text": text, "group_id": chat_id}
            RECENT_MESSAGES[chat_id].append(msg_data)
            MESSAGE_LOOKUP[link] = msg_data

# /getir KOMUTU 
async def getir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return
    
    response = "📜 GRUPLARDAKİ SON MESAJLAR\n\n"
    for group_id in ALLOWED_GROUPS:
        response += f"🏢 Grup ID: {group_id}\n"
        if not RECENT_MESSAGES[group_id]:
            response += "Henüz bot açıkken bu grupta mesaj yazılmadı.\n"
        else:
            for msg in RECENT_MESSAGES[group_id]:
                kisa_text = msg['text'][:40] + "..." if len(msg['text']) > 40 else msg['text']
                response += f"👤 {msg['user']}: {kisa_text}\n🔗 {msg['link']}\n"
        response += "\n"
        
    await update.message.reply_text(response, disable_web_page_preview=True)

# /anketle KOMUTU 
async def anketle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return

    metin = update.message.text
    temiz_args = re.sub(r'(?i)^/anketle(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    
    if not temiz_args:
        await update.message.reply_text("❗ Lütfen bir mesaj linki girin.\nÖrnek: `/anketle https://t.me/c/12345/678`")
        return
        
    link = temiz_args
    msg_data = MESSAGE_LOOKUP.get(link)
    
    if not msg_data:
        await update.message.reply_text("⚠️ Bu mesaj hafızamda yok. Mesaj eski olabilir veya bot resetlenmiş olabilir. Önce /getir yazarak hafızadaki linkleri kontrol et.")
        return
        
    text_to_poll = msg_data["text"]
    target_group = msg_data["group_id"]
    
    status_msg = await update.message.reply_text("🤔 İnceliyorum... Mesajın sahibini rezil edecek veya tiye alacak zekice bir anket yaratılıyor...")

    prompt = f"""Şu mesajı incele: "{text_to_poll}"
Bu mesaja dayanarak, mesajı yazan kişiyi alaya alan veya duruma uygun ince zekalı, absürt ve komik bir anket sorusu üret. 
Kararı sen ver: Mesaj ciddiyse tiye al, komikse daha da absürtleştir. İnce bir mizah veya iğneleme barındırsın.

Ayrıca bu duruma insanların verebileceği 5 farklı anket şıkkı yaz. 
ŞARTLAR:
1. Şıklarda KESİNLİKLE emoji KULLANMA. Sadece düz metin olsun.
2. Olumsuz veya sinirli şıklarda 'amk' kelimesini kullanabilirsin.
3. Her bir şık MAKSİMUM 10 KELİME olmalıdır.
4. Sorunun en başına içeriğe uygun tek bir emoji koy.

Yanıtını tam olarak şu formatta ver (Başka hiçbir açıklama yazma):
Soru: [En başa Emoji] [Soru metni]
1- [Şık 1]
2- [Şık 2]
3- [Şık 3]
4- [Şık 4]
5- [Şık 5]"""

    try:
        res = await client.aio.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )
        
        lines = [line.strip() for line in res.text.strip().split('\n') if line.strip()]
        parsed_options = []
        question_text = "🤔 Mesajı okudum ama dilim tutuldu?"
        
        for line in lines:
            if line.startswith("Soru:"):
                question_text = line.replace("Soru:", "").strip()
            elif re.match(r'^[1-5][-.)]\s*', line):
                clean_opt = re.sub(r'^[1-5][-.)]\s*', '', line).strip()
                clean_opt = clean_opt.replace('*', '') 
                parsed_options.append(clean_opt)
        
        options = parsed_options if len(parsed_options) == 5 else ["Haklısın", "Haksızsın", "Umrumda değil"]

    except Exception as e:
        await status_msg.edit_text(f"❌ Yapay zeka soruyu üretemedi: {e}")
        return

    question_text = question_text[:290] 
    safe_options = []
    for opt in options:
        clean_opt = opt[:95] 
        if clean_opt not in safe_options:
            safe_options.append(clean_opt)
        else:
            safe_options.append(clean_opt + " (Katılıyorum)") 
            
    try:
        await context.bot.send_poll(chat_id=target_group, question=question_text, options=safe_options, is_anonymous=False)
        await status_msg.edit_text(f"✅ Anket başarıyla oluşturuldu ve o mesajın ait olduğu gruba gönderildi!\n\nSoru: {question_text}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Gruba anket gönderilemedi!\nTelegram Hatası: `{e}`")

# /ama KOMUTU
async def ama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return

    gender = "Çocuk/Kız"
    is_high_score = random.random() < 0.60 

    status_msg = await update.message.reply_text("🤔 Anket sorusu ve mantıklı seçenekler yaratılıyor...")

    score = random.randint(8, 10) if is_high_score else random.randint(1, 7)

    prompt = f"""Potansiyel bir partner ({gender}) düşün. Dış görünüşü {score}/10. Buna gerçekçi ama fikir ayrılığı yaratacak, tartışmalı bir huy/özellik ekle.
Puan yüksekse (8-10) özellik itici veya zorlayıcı olsun (red flag). Puan düşükse (1-7) özellik cazip veya durumu kurtaran bir şey olsun (green flag).
Sadece 'ama'dan sonraki kısmı yazacaksın. Uçuk kaçık fantastik veya çok saçma şeyler olmasın (örnek: ağzında bozuk para biriktiriyor GİBİ OLAMAZ). İkili ilişkilerde insanların gerçekten tartışıp kafa yoracağı durumlar olsun (örnek: eski sevgilisiyle hala yakın arkadaş, hesabı asla ödemiyor, annesinin sözünden çıkmıyor).
ÖNEMLİ KURAL: Özelliği yazarken cinsiyet belirtme (örneğin 'kız arkadaşlarıyla' veya 'erkek kankalarıyla' yerine 'karşı cinsten arkadaşlarıyla' gibi genel ifadeler kullan ki anketi okuyan hem erkekler hem kadınlar kendilerine göre yorumlayabilsin).

Ayrıca bu duruma insanların verebileceği 5 farklı anketi şıkkını yaz. 
ŞARTLAR:
1. Şıklarda KESİNLİKLE emoji KULLANMA. Sadece düz metin olsun.
2. Şıklar oluşturduğun bu spesifik duruma tam uygun olsun.
3. Olumsuz veya sinirli şıklarda 'amk' kelimesini kullanabilirsin.
4. Her bir şık MAKSİMUM 10 KELİME olmalıdır.

Yanıtını tam olarak şu formatta ver (Başka hiçbir açıklama yazma):
Emoji: [Duruma uygun tek bir emoji]
Özellik: [Sadece ama'dan sonraki kısım]
1- [Şık 1]
2- [Şık 2]
3- [Şık 3]
4- [Şık 4]
5- [Şık 5]"""

    emoji = "🤔"
    trait = "eski sevgilisiyle hala yakın arkadaş"
    options = ["Sıkıntı yok güveniyorsam tamam", "Duruma ve karşındakine göre değişir", "Kesinlikle sorun çıkarırım", "Direkt yol veririm", "Böyle saçmalık olmaz amk"]

    try:
        res = await client.aio.models.generate_content(
            model=MODEL_NAME, contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )
        
        lines = [line.strip() for line in res.text.strip().split('\n') if line.strip()]
        parsed_options = []
        
        for line in lines:
            if line.startswith("Emoji:"): emoji = line.replace("Emoji:", "").strip()
            elif line.startswith("Özellik:"): trait = line.replace("Özellik:", "").strip()
            elif re.match(r'^[1-5][-.)]\s*', line):
                clean_opt = re.sub(r'^[1-5][-.)]\s*', '', line).strip()
                clean_opt = clean_opt.replace('*', '') 
                parsed_options.append(clean_opt)
        
        if len(parsed_options) == 5: options = parsed_options

    except Exception: pass

    question_text = f"{emoji} {gender} {score}/10 ama {trait}?"
    question_text = question_text[:290] 

    safe_options = []
    for opt in options:
        clean_opt = opt[:95] 
        if clean_opt not in safe_options: safe_options.append(clean_opt)
        else: safe_options.append(clean_opt + " (Katılıyorum)") 
            
    if len(safe_options) < 2: safe_options = ["Evet", "Hayır"] 
        
    success_count = 0
    error_messages = []
    
    for group_id in ALLOWED_GROUPS:
        try:
            await context.bot.send_poll(chat_id=group_id, question=question_text, options=safe_options, is_anonymous=False)
            success_count += 1
        except Exception as e:
            error_messages.append(f"❌ {group_id} ID'li gruba gönderilemedi.\nTelegram Hatası: `{e}`")
    
    if success_count > 0: await status_msg.edit_text(f"✅ Soru {success_count} gruba anket olarak gönderildi!\n\nGönderilen Soru: {emoji} {gender} {score}/10 ama {trait}")
    else: await status_msg.edit_text(f"⚠️ Anket 0 gruba gönderildi! Sorun Telegram tarafından engellendi.\n\nİşte detaylar:\n" + "\n\n".join(error_messages))


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_UPDATING
    if update.effective_user.id not in ADMIN_IDS: return 
    if IS_UPDATING: await update.message.reply_text(" Bot şu anda zaten bir güncelleme yapıyor. Lütfen bitmesini bekle.")
    else:
        await update.message.reply_text("🔄 Manuel toplu güncelleme başlatıldı.\nHer burç arası 90 saniye bekleniyor.\nİşlem yaklaşık 18 dakika sürecektir.")
        asyncio.create_task(update_all_horoscopes())

async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
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
    yorum = HOROSCOPE_CACHE.get(burc_input)

    if yorum == "": await update.message.reply_text("🛰️ Yıldızlar henüz uyanmadı. Lütfen yönetici güncellemeyi başlatana kadar veya gece güncellemesi yapılana kadar bekle.")
    else: await update.message.reply_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")

async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    photo_obj = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo_obj:
        await update.message.reply_text("☕ Fal için fincan fotosu lazım. Neyim ben mahalle falcısı mı sandın?")
        return
        
    status_msg = await update.message.reply_text("☕ Telveler analiz ediliyor...")
    try:
        photo_file = await photo_obj.get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
        prompt = "Görseldeki kahve lekelerini somut nesnelere benzeterek dobra ve mistik bir dille yorumla. Klişelerden kaçın. maksimum 150 kelime kullan ve asla yıldız(*) işareti kullanma. Her paragrafın başına içeriğine uygun bir emoji ekle."
        res = await client.aio.models.generate_content(
            model=MODEL_NAME, contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")],
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )
        await status_msg.edit_text(f"☕ Zenithar Falcı Teyze:\n\n{res.text}")
    except: await status_msg.edit_text("⚠️ Fincanı okuyamadım.")

async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    status_msg = await update.message.reply_text("🔄 İnceleniyor...")
    try:
        if target.photo:
            photo_file = await target.photo[-1].get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        else:
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=f"Özetle: {target.text or target.caption}")
        await status_msg.edit_text(f"📝 ÖZET:\n\n{res.text}")
    except: await status_msg.edit_text("❌ Hata.")

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    try:
        res = await client.aio.models.generate_content(
            model=MODEL_NAME, contents=f"Tarot kartları: {', '.join(secilenler)}. Geçmiş, şimdi ve geleceği ayrı paragraflarda yorumla. maksimum 120 kelime kullan ama asla yıldız işareti(*) kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.",
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )
        await status.edit_text(f"🔮 TAROT FALI:\n\n{res.text}")
    except: await status.edit_text("Tüh bağlantı koptu.")

async def main():
    keep_alive()
    asyncio.create_task(background_scheduler())
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    allowed_filter = filters.Chat(chat_id=ALLOWED_GROUPS) | (filters.ChatType.PRIVATE & filters.User(user_id=ADMIN_IDS))
    interaction_filter = filters.TEXT | filters.COMMAND | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL
    
    application.add_handler(MessageHandler(interaction_filter & (~allowed_filter), reject_unauthorized))
    
    application.add_handler(CallbackQueryHandler(rpg_callback, pattern='^rpg_'))
    
    # Komutlar
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/rpgpuan'), rpgpuan_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/puanyedek'), puanyedek_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/puanla'), puanla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/rpg'), rpg_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/update'), update_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ama'), ama_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/getir'), getir_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/anketle'), anketle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), log_message))
    
    print(f"Zenithar Services Başlatıldı. (Manuel Başlangıç ve 02:00 Oto-Güncelleme)")
    
    await application.initialize(); await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: 
        print("Eski bot örneğinin kapanması bekleniyor...")
        time.sleep(10) 
        asyncio.run(main())
    except Exception as e: 
        print(f"Kritik Hata: {e}")
