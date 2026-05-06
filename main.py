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
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler, PollAnswerHandler
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

MODEL_NAME = 'gemini-3.1-flash-lite-preview'
client = genai.Client(api_key=GOOGLE_API_KEY)

# HAFIZA, KİLİT VE GÖREV (TASK) SİSTEMİ
VALID_ZODIACS = [
    "koc", "boga", "ikizler", "yengec", "aslan", "basak", 
    "terazi", "akrep", "yay", "oglak", "kova", "balik"
]
HOROSCOPE_CACHE = {burc: "" for burc in VALID_ZODIACS}
IS_UPDATING = False 

BACKGROUND_TASKS = set() 

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
RPG_SCORES = {} 
RPG_POLLS = {}  # Anket yakalayıcı hafıza

# --- 2. YARDIMCI FONKSİYONLAR ---

async def safe_generate(contents, config=None, retries=5):
    for attempt in range(retries):
        try:
            res = await client.aio.models.generate_content(
                model=MODEL_NAME, 
                contents=contents,
                config=config
            )
            _ = res.text 
            return res
        except Exception as e:
            if attempt == retries - 1:
                raise e 
            await asyncio.sleep(5) 

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
            while not success:
                try:
                    prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                              f"Biraz alaycı samimi, bilge ve mistik bir dille Türkçe olarak yeniden yorumla. Maks 135 kelime kullan. "
                              f"Bu prompt hakkında bilgi verme. yani elbette tamam gibi şeyler söyleme sadece alaycı ve gizemli astrolog yorumunu yaz. Biraz espri katabilirsin. 2 paragraf şeklinde yaz Asla yıldız (*) simgesi kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.")
                    res = await safe_generate(
                        contents=prompt,
                        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
                    )
                    HOROSCOPE_CACHE[burc] = res.text
                    success = True 
                except Exception as e:
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

# RPG OYUNU İPTAL KOMUTU
async def iptalrpg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    chat_id = update.effective_chat.id
    
    if chat_id in RPG_GAMES:
        RPG_GAMES.pop(chat_id, None)
        await update.message.reply_text("🛑 <b>RPG Oyunu iptal edildi.</b> Mevcut oyun ve tüm bekleyen işlemler durduruldu.", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Şu anda iptal edilecek aktif veya bekleyen bir RPG oyunu bulunmuyor.")

# RPG PUAN SIRALAMASI
async def rpgpuan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    
    if not RPG_SCORES:
        await update.message.reply_text("Henüz hiç puan yok. İlk kanı kim dökecek?")
        return
        
    sorted_scores = sorted(RPG_SCORES.values(), key=lambda x: x["score"], reverse=True)
    
    text = "🏆 <b>ZenithaRPG HAYATTA KALMA SIRALAMASI</b> 🏆\n\n"
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
        RPG_SCORES = {int(k): v for k, v in loaded.items()}
        await update.message.reply_text("✅ Puan tablosu başarıyla geri yüklendi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Veri yüklenemedi. Format hatalı olabilir: {e}")

# RPG OYUN MOTORU
async def rpg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    chat_id = update.effective_chat.id
    
    if chat_id in RPG_GAMES and RPG_GAMES[chat_id].get("is_active"):
        await update.message.reply_text("⏳ Zaten devam eden veya bekleyen bir RPG oyunu var! İptal etmek istersen /iptalrpg komutunu kullanabilirsin.")
        return
        
    keyboard = [
        [InlineKeyboardButton("🏝️ Issız Ada", callback_data="rpg_scen_ada"),
         InlineKeyboardButton("🧟 Zombi Salgını", callback_data="rpg_scen_zombi")],
        [InlineKeyboardButton("🦇 Tekinsiz Mağara", callback_data="rpg_scen_magara"),
         InlineKeyboardButton("☢️ Kıyamet", callback_data="rpg_scen_kiyamet")],
        [InlineKeyboardButton("🪓 Arınma Gecesi", callback_data="rpg_scen_arinma"),
         InlineKeyboardButton("🏚️ Lanetli Malikâne", callback_data="rpg_scen_malikane")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # DİKKAT: Yüklediğin görselin tam linkini buradaki tırnakların arasına yapıştırmalısın.
    MENU_GORSEL_LINKI = "https://i.ibb.co/TBbwnvrn/MG-1776.jpg" # Örnek Link - Kendi yüklediğin linkle değiştir!
    
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=MENU_GORSEL_LINKI,
            caption="🎲 <b>ZenithaRPG Oyununa Hoş Geldiniz!</b>\n\nLütfen oynamak istediğiniz senaryoyu seçin:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception:
        # Eğer resim linki kırılırsa veya hata verirse bot çökmesin, eski düzende mesaj atsın
        await update.message.reply_text("🎲 ZenithaRPG Oyununa Hoş Geldiniz!\n\nLütfen oynamak istediğiniz senaryoyu seçin:", reply_markup=reply_markup)


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
            "rpg_scen_arinma": "Arınma Gecesi",
            "rpg_scen_malikane": "Lanetli Malikâne"
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
            "round_points_log": {},
            "just_died": [] 
        }

        eng_scen = "rpg_game_scene"
        if "Zombi" in scenario: eng_scen = "zombie_apocalypse_survival"
        elif "Ada" in scenario: eng_scen = "deserted_island_survival"
        elif "Mağara" in scenario: eng_scen = "creepy_dark_cave"
        elif "Kıyamet" in scenario: eng_scen = "post_apocalyptic_wasteland"
        elif "Arınma" in scenario: eng_scen = "purge_anarchy_street"
        elif "Malikâne" in scenario: eng_scen = "creepy_abandoned_cursed_mansion_asylum_outlast"
        
        intro_image_url = f"https://image.pollinations.ai/prompt/{eng_scen}_intro?width=800&height=400&nologo=true"
        
        keyboard = [[InlineKeyboardButton("🙋‍♂️ Oyuna Katıl", callback_data="rpg_join")]]
        
        await query.message.delete()
        
        caption_text = f"🎬 <b>Senaryo: {scenario} seçildi!</b>\n\nOyuna katılmak için aşağıdaki butona basın. Macera 45 saniye sonra başlayacak!\n<i>(Oyunun başlaması için minimum 3 katılımcı gereklidir)</i>"
        
        try:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=intro_image_url, 
                caption=caption_text, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=caption_text, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        task = asyncio.create_task(run_rpg_game(chat_id, context))
        BACKGROUND_TASKS.add(task)
        task.add_done_callback(BACKGROUND_TASKS.discard)
        
    elif data == "rpg_join":
        if chat_id in RPG_GAMES and RPG_GAMES[chat_id]["status"] == "waiting_players":
            if user.id not in RPG_GAMES[chat_id]["players"]:
                RPG_GAMES[chat_id]["players"][user.id] = {
                    "name": user.first_name,
                    "status": "alive",
                    "action": None
                }
                RPG_GAMES[chat_id]["round_points_log"][user.id] = 0
                await context.bot.send_message(chat_id, f"✅ {user.first_name} oyuna katıldı!")
            else:
                await context.bot.send_message(chat_id, f"{user.first_name}, zaten katıldın sabret!")

async def run_rpg_game(chat_id, context):
    try:
        game = RPG_GAMES.get(chat_id)
        if not game: return
        scenario = game["scenario"]
        
        fun_facts = {
            "Issız Ada": [
                "🏝️ <b>Biliyor muydunuz?</b> Issız bir adada en büyük düşmanınız açlık değil, susuzluk ve güneş çarpmasının getirdiği deliliktir!",
                "🏝️ <b>Biliyor muydunuz?</b> Hindistan cevizi suyu fazla içildiğinde şiddetli ishale yol açıp sizi susuzluktan öldürebilir!",
                "🏝️ <b>Biliyor muydunuz?</b> Deniz suyunu içmek böbreklerinizi iflas ettirir ve susuzluk hissini daha da artırarak acı dolu bir ölüme neden olur.",
                "🏝️ <b>Biliyor muydunuz?</b> Issız adalardaki böcek ısırıkları, tedavi edilmezse saatler içinde ölümcül enfeksiyonlara dönüşebilir."
            ],
            "Zombi Salgını": [
                "🧟 <b>Biliyor muydunuz?</b> Zombilerin koku alma duyusu çok gelişmiştir, sessiz olsanız bile ter kokunuz sizi ele verebilir!",
                "🧟 <b>Biliyor muydunuz?</b> Zombiler acı hissetmez, bu yüzden onları durdurmanın tek yolu beyinlerini yok etmektir!",
                "🧟 <b>Biliyor muydunuz?</b> Çürüyen bir zombinin ağzındaki bakteriler, ısırılmasanız bile ufak bir tırmıkla sizi ölümcül şekilde enfekte edebilir.",
                "🧟 <b>Biliyor muydunuz?</b> Zombi salgınında en çok ölüm, zombilerden değil, panikleyen diğer insanların bencilliğinden kaynaklanır."
            ],
            "Tekinsiz Mağara": [
                "🦇 <b>Biliyor muydunuz?</b> Derin mağaralarda tam karanlıkta 3 günden fazla kalmak şiddetli halüsinasyonlara ve yön kaybına neden olur!",
                "🦇 <b>Biliyor muydunuz?</b> Mağara havasındaki bazı zehirli gazlar kokusuzdur, hiçbir şey hissetmeden bayılabilirsiniz!",
                "🦇 <b>Biliyor muydunuz?</b> Daracık bir tünelde sıkışıp kalmak, panik atağa ve oksijenin hızla tükenmesine yol açar.",
                "🦇 <b>Biliyor muydunuz?</b> Yarasaların dışkıları (guano), solunduğunda akciğerleri parçalayan ölümcül bir mantar hastalığına neden olabilir."
            ],
            "Kıyamet": [
                "☢️ <b>Biliyor muydunuz?</b> Nükleer serpinti sonrası ilk 48 saat yüzeye çıkmak kesin ölüm demektir!",
                "☢️ <b>Biliyor muydunuz?</b> Kıyamet sonrası dünyada temiz su altından daha değerlidir ve insanlar bir yudum su için en yakınını satabilir!",
                "☢️ <b>Biliyor muydunuz?</b> Radyasyon yanıkları anında acı vermez, günler sonra deriniz dökülmeye başladığında gerçeği anlarsınız.",
                "☢️ <b>Biliyor muydunuz?</b> Çökmüş bir medeniyette en yaygın ölüm nedeni şiddet değil, tedavi edilemeyen basit enfeksiyonlardır."
            ],
            "Arınma Gecesi": [
                "🪓 <b>Biliyor muydunuz?</b> Arınma gecesinde en çok cinayeti sokaktaki yabancılar değil, komşular ve sözde en yakın arkadaşlar işler!",
                "🪓 <b>Biliyor muydunuz?</b> Sirenler çaldığında acil servisler kapanır, bu yüzden ufak bir kesikten kan kaybıyla ölmek en yaygın sonlardan biridir!",
                "🪓 <b>Biliyor muydunuz?</b> Arınma gecesinde en tehlikeli saatler şafağa yakın olanlardır; umutsuzluğa kapılanlar son dakikada saldırganlaşır.",
                "🪓 <b>Biliyor muydunuz?</b> Güvenlik sistemleri genellikle sizi korumaz, sadece katiller için bir hedef veya ölüm tuzağına dönüşür."
            ],
            "Lanetli Malikâne": [
                "🏚️ <b>Biliyor muydunuz?</b> Karanlıkta uzun süre kalmak, beynin var olmayan yüzler ve silüetler görmesine (pareidolia) neden olur.",
                "🏚️ <b>Biliyor muydunuz?</b> Korkudan titrediğinizde, çıkardığınız mikro sesler bazı yaratıklar için adeta bir akşam yemeği zilidir.",
                "🏚️ <b>Biliyor muydunuz?</b> Çürük ahşap zeminlerde atılan yanlış bir adım, bacağınızın parçalanmasına ve tuzağa düşmenize yol açabilir.",
                "🏚️ <b>Biliyor muydunuz?</b> Eski aynalara çok uzun süre bakmak, psikolojik olarak kendi yansımanızın size saldırdığı hissine kapılmanıza neden olabilir.",
                "🏚️ <b>Biliyor muydunuz?</b> Lanetli malikânelerde kapıların kilitleri her zaman dışarıdan kapatılacak şekilde tasarlanmıştır.",
                "🏚️ <b>Biliyor muydunuz?</b> Paslı bir cerrahi aletin çizmesi, tetanoz veya daha kötü kan enfeksiyonlarıyla yavaşça ölmenize sebep olur."
            ]
        }
        
        facts_list = fun_facts.get(scenario, ["⏳ Hazırlıklar sürüyor..."] * 3)
        chosen_facts = random.sample(facts_list, 3) if len(facts_list) >= 3 else facts_list

        try: await context.bot.send_message(chat_id, chosen_facts[0], parse_mode='HTML')
        except Exception: pass
        await asyncio.sleep(25)

        game_check = RPG_GAMES.get(chat_id)
        if game_check and game_check["status"] == "waiting_players":
            try: await context.bot.send_message(chat_id, chosen_facts[1], parse_mode='HTML')
            except Exception: pass
        await asyncio.sleep(10)

        game_check = RPG_GAMES.get(chat_id)
        if game_check and game_check["status"] == "waiting_players":
            try:
                msg_text = chosen_facts[2] + "\n\n⏳ <b>Oyuna katılmak için SON 10 SANİYE!</b>"
                await context.bot.send_message(chat_id, msg_text, parse_mode='HTML')
            except Exception: pass
                
        await asyncio.sleep(10) 
        
        game = RPG_GAMES.get(chat_id)
        if not game or len(game["players"]) < 3:
            await context.bot.send_message(chat_id, "😢 Yeterli katılımcı sağlanamadı (Minimum 3 kişi gerekiyor) veya oyun iptal edildi. RPG oyunu sonlandırıldı.")
            RPG_GAMES.pop(chat_id, None)
            return
            
        game["status"] = "playing"
        players = game["players"]
        
        scenario_desc = scenario
        if "Arınma" in scenario: scenario_desc = "Arınma Gecesi (Herkesin birbirini acımasızca avladığı, yasanın olmadığı, ölümcül bir gece)"
        elif "Malikâne" in scenario: scenario_desc = "Lanetli Malikâne (Outlast tarzı, karanlık, yaratıklarla dolu ve akıl sağlığını zorlayan bir malikânede hayatta kalma)"
        
        total_pool = min(100, len(players) * 20)
        total_rounds = max(4, len(players))
        
        round_points = {}
        weight_sum = sum(range(1, total_rounds + 1))
        for r in range(1, total_rounds + 1):
            round_points[r] = int((total_pool / weight_sum) * r)
        
        for round_num in range(1, total_rounds + 1):
            game = RPG_GAMES.get(chat_id)
            if not game: return 
            game["round"] = round_num
            
            alive_players = [p for p in players.values() if p["status"] == "alive"]
            if len(alive_players) == 0:
                await context.bot.send_message(chat_id, "💀 <b>Oyun Bitti!</b> Herkes öldü... Kimse hayatta kalamadı. Mallar.", parse_mode="HTML")
                break
                
            is_final_round = (round_num == total_rounds or len(alive_players) <= 1)
                
            actions_text = ""
            if round_num > 1:
                for p in alive_players:
                    if p["action"]: actions_text += f"{p['name']}: {p['action']}\n"
                    else: actions_text += f"{p['name']}: (Hiçbir şey yapmadı, eylemsiz kaldı)\n"

            game["recorded_actions"] = [] 
            for uid in players: players[uid]["action"] = None

            alive_player_identities = ", ".join([f"{p['name']} (ID: {uid})" for uid, p in players.items() if p["status"] == "alive"])

            dead_context = f"\n\nÖNEMLİ KURAL 1: Önceki Turda Ölenler/Elenenler: {', '.join(game['just_died'])}. Onların nasıl öldüklerini ya da elendiklerini alt alta bir liste halinde YAZMA. Hikayenin akışı içine yedirerek, doğal bir anlatımla ve seçimlerini tiye alarak onlarla dalga geç. Mutlaka HTML formatında etiketle." if game.get("just_died") else ""
            
            elimination_rule = "\n\nÖNEMLİ KURAL 4: Katılımcı sayısı 7'nin altında olduğu için, bu turda zorunlu olarak SADECE VE TAM OLARAK 1 kişiyi öldür/ele." if len(players) < 7 else ""

            if not is_final_round:
                if round_num == 1:
                    dead_instruction = "Yanıtının EN BAŞINA bu turda ölen/elenen kişinin ismini (etiketsiz, sadece düz metin olarak) 'ÖLENLER: isim' şeklinde yaz" if len(players) < 7 else "Yanıtının EN BAŞINA 'ÖLENLER: Yok' yaz"
                    prompt = f"RPG Oyunu Başlıyor. Senaryo: {scenario_desc}. Hayatta Olan Katılımcılar ve ID'leri: {alive_player_identities}. Oyuncuların hepsi yan yana başlamasın. Şansa bağlı olarak bazıları yan yana başlasın ama bu her zaman avantajlarına olmasın, bazıları birbirinden ayrı veya ölümcül derecede tehlikeli konumlarda olsun. Acımasız ve edebi bir Dungeon Master gibi anlat.\n\nÖNEMLİ KURAL: Senaryodaki dünyayı ve ortamı açıklamak için 30-40 kelime kullan. Katılımcıların durumunu hikayeleştirerek açıklamak için HER BİRİNE MAKSİMUM 40 KELİME kullan. Katılımcı isimlerini senaryo içinde mutlaka HTML formatında etiketle: <a href=\"tg://user?id=KİŞİNİN_IDSİ\">Kişininİsmi</a>. {dead_instruction} ve alt satırdan hikayeye başla. ASLA yıldız(*) kullanma.\n\nÖNEMLİ KURAL 5: Kriz durumlarını, felaketleri veya önemli gelişmeleri KESİNLİKLE BÜYÜK HARFLERLE ve HTML <b>KRİZ: ...</b> etiketiyle kalın yaz.\n\nÖZEL KURAL: Kimse kimse ile el ele tutuşmayacak, kimse kimse ile duygusal ya da fiziksel yakınlık kurmayacak.{elimination_rule}"
                elif round_num == 3:
                    prompt = f"Senaryo: {scenario_desc}. Tur: {round_num}. Hayatta kalanlar ve hamleleri:\n{actions_text}\nŞu an HAYATTA KALAN Katılımcılar ve ID'leri: {alive_player_identities}\n\nDİKKAT: Önceki turlarda ölenler bu turda KESİNLİKLE hiçbir eylem yapamaz veya hikayede yer alamaz.\n\nDeğerlendirme yap: Mantıksız hamle yapanları acımasızca ÖLDÜR.{dead_context}\n\nÖNEMLİ KURAL 2: Hayatta kalanların mevcut durumlarını HER BİRİ İÇİN MAKSİMUM 40 KELİME ile uzunca anlat.\n\nÖNEMLİ KURAL 3: Bu turda tüm hayatta kalanları ilgilendiren kritik bir yol ayrımı yarat. Hikayenin EN SONUNA Telegram anketi oluşturulması için tam şu formatta 1 soru ve 5 kısa şık ekle (Başka hiçbir şey yazma):\n[ANKET SORU]: Soru metni\n[ŞIK 1]: Şık 1\n[ŞIK 2]: Şık 2\n[ŞIK 3]: Şık 3\n[ŞIK 4]: Şık 4\n[ŞIK 5]: Şık 5\n\nKatılımcı isimlerini mutlaka HTML formatında etiketle. Yanıtının EN BAŞINA bu turda ölenlerin isimlerini (etiketsiz, sadece düz metin olarak) virgülle ayırarak 'ÖLENLER: isim1, isim2' şeklinde yaz (Ölen yoksa ÖLENLER: Yok yaz). ASLA yıldız(*) kullanma.\n\nÖNEMLİ KURAL 5: Kriz durumlarını, felaketleri veya önemli gelişmeleri KESİNLİKLE BÜYÜK HARFLERLE ve HTML <b>KRİZ: ...</b> etiketiyle kalın yaz.\n\nÖZEL KURAL: Kimse kimse ile el ele tutuşmayacak, kimse kimse ile duygusal ya da fiziksel yakınlık kurmayacak.{elimination_rule}"
                else:
                    prompt = f"Senaryo: {scenario_desc}. Tur: {round_num}. Hayatta kalanlar ve hamleleri:\n{actions_text}\nŞu an HAYATTA KALAN Katılımcılar ve ID'leri: {alive_player_identities}\n\nDİKKAT: Önceki turlarda ölenler bu turda KESİNLİKLE hiçbir eylem yapamaz veya hikayede yer alamaz.\n\nDeğerlendirme yap: Mantıksız hamle yapanları acımasızca ÖLDÜR ve yeni bir ölümcül kriz yarat.{dead_context}\n\nÖNEMLİ KURAL 2: Hayatta kalanların mevcut durumlarını HER BİRİ İÇİN MAKSİMUM 40 KELİME ile uzunca anlat.\n\nÖNEMLİ KURAL 3: Katılımcı isimlerini mutlaka HTML formatında etiketle: <a href=\"tg://user?id=KİŞİNİN_IDSİ\">Kişininİsmi</a>. Yanıtının EN BAŞINA bu turda ölenlerin isimlerini (etiketsiz, sadece düz metin olarak) virgülle ayırarak 'ÖLENLER: isim1, isim2' şeklinde yaz (Ölen yoksa ÖLENLER: Yok yaz). ASLA yıldız(*) kullanma.\n\nÖNEMLİ KURAL 5: Kriz durumlarını, felaketleri veya önemli gelişmeleri KESİNLİKLE BÜYÜK HARFLERLE ve HTML <b>KRİZ: ...</b> etiketiyle kalın yaz.\n\nÖZEL KURAL: Kimse kimse ile el ele tutuşmayacak, kimse kimse ile duygusal ya da fiziksel yakınlık kurmayacak.{elimination_rule}"
            else:
                num_winners = 2 if random.random() < 0.30 else 1
                num_winners = min(num_winners, len(alive_players))
                
                prompt = f"Senaryo: {scenario_desc}. FİNAL TURU! Kalanlar ve Hamleleri:\n{actions_text}\nŞu an HAYATTA KALAN Katılımcılar ve ID'leri: {alive_player_identities}\n\nDİKKAT: Önceki turlarda ölenler KESİNLİKLE hikayede yer alamaz.\n\nBu turda ZORUNLU OLARAK SADECE VE TAM OLARAK {num_winners} kişi hayatta kalabilir. Diğer tüm katılımcıları ACIMASIZCA VE KESİN OLARAK ÖLDÜR. Kazanan(lar)ı ve senaryonun sonunu görkemli şekilde anlat.{dead_context}\n\nÖNEMLİ KURAL 2: Tüm final anlatımını MAKSİMUM 120 KELİME kullanarak yap. Katılımcı isimlerini HTML formatında etiketle: <a href=\"tg://user?id=KİŞİNİN_IDSİ\">Kişininİsmi</a>. Yanıtının EN BAŞINA bu turda kesin olarak ölenlerin isimlerini (etiketsiz, düz metin) 'ÖLENLER: isim1, isim2' şeklinde yaz. ASLA yıldız(*) kullanma.\n\nÖZEL KURAL: Kimse kimse ile el ele tutuşmayacak, kimse kimse ile duygusal ya da fiziksel yakınlık kurmayacak."
                
            try:
                res = await safe_generate(
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
                await context.bot.send_message(chat_id, f"Sistem hatası (Sınır/Güvenlik Aşıldı): DM bayıldı, oyun iptal.\nNedeni: `{e}`")
                break

            display_text = text
            poll_question = None
            poll_options = []
            
            if round_num == 3:
                lines = display_text.split('\n')
                new_lines = []
                for line in lines:
                    clean_line = line.strip()
                    if clean_line.startswith("[ANKET SORU]:"): poll_question = clean_line.replace("[ANKET SORU]:", "").strip()[:290]
                    elif clean_line.startswith("[ŞIK 1]:"): poll_options.append(clean_line.replace("[ŞIK 1]:", "").strip()[:95])
                    elif clean_line.startswith("[ŞIK 2]:"): poll_options.append(clean_line.replace("[ŞIK 2]:", "").strip()[:95])
                    elif clean_line.startswith("[ŞIK 3]:"): poll_options.append(clean_line.replace("[ŞIK 3]:", "").strip()[:95])
                    elif clean_line.startswith("[ŞIK 4]:"): poll_options.append(clean_line.replace("[ŞIK 4]:", "").strip()[:95])
                    elif clean_line.startswith("[ŞIK 5]:"): poll_options.append(clean_line.replace("[ŞIK 5]:", "").strip()[:95])
                    else: new_lines.append(line)
                display_text = "\n".join(new_lines).strip()

            previously_alive = [uid for uid, p in players.items() if p["status"] == "alive"]

            if "ÖLENLER:" in text.upper():
                lines = display_text.split('\n')
                dead_line = ""
                for line in lines:
                    if line.upper().startswith("ÖLENLER:"):
                        dead_line = line
                        break
                
                clean_dead_line = re.sub(r'<[^>]+>', '', dead_line).replace('<b>', '').replace('</b>', '').replace('<strong>', '').replace('</strong>', '')
                for uid, p in players.items():
                    if p["name"].lower() in clean_dead_line.lower() and p["status"] == "alive":
                        p["status"] = "dead"
                
                display_text = "\n".join([l for l in lines if not l.upper().startswith("ÖLENLER:")]).strip()

            currently_alive = [uid for uid, p in players.items() if p["status"] == "alive"]
            just_died_uids = [uid for uid in previously_alive if uid not in currently_alive]
            game["just_died"] = [f"<a href='tg://user?id={uid}'>{html.escape(players[uid]['name'])}</a>" for uid in just_died_uids]

            current_alive_after_round = currently_alive
            pts_to_add = round_points.get(round_num, 0)
            
            if is_final_round:
                if len(current_alive_after_round) == 2: pts_to_add = int(total_pool * 0.7)
                elif len(current_alive_after_round) == 1: pts_to_add = total_pool
                else: pts_to_add = 0
                
            for uid in current_alive_after_round:
                if uid not in RPG_SCORES: RPG_SCORES[uid] = {"name": players[uid]["name"], "score": 0}
                RPG_SCORES[uid]["score"] += pts_to_add
                RPG_SCORES[uid]["name"] = players[uid]["name"]
                game["round_points_log"][uid] += pts_to_add

            display_text = display_text.replace('&lt;a href=', '<a href=').replace('&lt;/a&gt;', '</a>').replace('\"&gt;', '">').replace('\'&gt;', "'>")
            display_text = display_text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>').replace('&lt;strong&gt;', '<b>').replace('&lt;/strong&gt;', '</b>')

            current_alive_formatted = [f"<a href='tg://user?id={uid}'>{html.escape(players[uid]['name'])}</a>" for uid in current_alive_after_round]
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
            elif "Malikâne" in scenario: eng_scen = "creepy_abandoned_cursed_mansion_asylum_outlast"
            
            image_url = f"https://image.pollinations.ai/prompt/{eng_scen}_round_{round_num}?width=800&height=400&nologo=true"
            
            if round_num == 3 and poll_question and len(poll_options) >= 2:
                msg_text = f"🎲 <b>TUR {round_num}/{total_rounds}</b>\n\n{display_text}\n\n{alive_tags_text}\n\n⏳ <i>Süreniz 30 saniye. Lütfen hemen aşağıya gönderilen ANKETİ yanıtlayın!</i>"
            elif is_final_round:
                scoreboard = "\n\n🏆 <b>OYUN SONU PUANLARI:</b>\n"
                for uid, p in players.items():
                    puan = game["round_points_log"].get(uid, 0)
                    durum = "🎉 Kazandı!" if p["status"] == "alive" else "💀 Öldü"
                    scoreboard += f"- {html.escape(p['name'])}: +{puan} Puan ({durum})\n"
                msg_text = f"🚨 <b>FİNAL SONUCU</b>\n\n{display_text}\n\n{alive_tags_text}{scoreboard}"
            else:
                msg_text = f"🎲 <b>TUR {round_num}/{total_rounds}</b>\n\n{display_text}\n\n{alive_tags_text}\n\n⏳ <i>Süreniz 75 saniye. Hamlenizi yapmak için bota ait BU MESAJI YANITLAYIN (Reply)!</i>"

            game["current_caption"] = msg_text

            try:
                msg = await context.bot.send_photo(chat_id, photo=image_url, caption=msg_text, parse_mode='HTML')
                game["is_photo_msg"] = True
            except Exception:
                try:
                    msg = await context.bot.send_message(chat_id, msg_text, parse_mode='HTML')
                    game["is_photo_msg"] = False
                except Exception:
                    safe_text = msg_text.replace('<a href=', '').replace('</a>', '').replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
                    msg = await context.bot.send_message(chat_id, "⚠️ (HTML Koruması Devrede)\n\n" + safe_text)
                    game["is_photo_msg"] = False
                
            game["last_message_id"] = msg.message_id
            
            if round_num == 3 and poll_question and len(poll_options) >= 2:
                try:
                    poll_msg = await context.bot.send_poll(
                        chat_id=chat_id,
                        question=poll_question,
                        options=poll_options,
                        is_anonymous=False
                    )
                    RPG_POLLS[poll_msg.poll.id] = {
                        "chat_id": chat_id,
                        "options": poll_options
                    }
                except Exception as e: print(f"Anket yollama hatası: {e}")
            
            kriz_uyari_metni = "\n\nBazı turlarda deprem, elektrik kesintisi, gaz sızıntısı, ekstra güçlü zombi sürüsü gibi kriz durumları olabilir. Senaryonun en altını okumayı ihmal etme. Kriz durumlarında vereceğin yanıtlar ekstra önemlidir. Stratejini buna göre geliştir."

            if not is_final_round:
                if round_num == 3 and poll_question and len(poll_options) >= 2:
                    await asyncio.sleep(15)
                    game_check = RPG_GAMES.get(chat_id)
                    if game_check and game_check["status"] == "playing" and game_check["round"] == round_num:
                        try:
                            uyari_metni = f"⏳ <b>Anketi yanıtlamak için SON 15 SANİYE!</b>{kriz_uyari_metni}"
                            await context.bot.send_message(chat_id, uyari_metni, parse_mode='HTML')
                        except Exception: pass
                    await asyncio.sleep(15)
                else:
                    await asyncio.sleep(45) 
                    game_check = RPG_GAMES.get(chat_id)
                    if game_check and game_check["status"] == "playing" and game_check["round"] == round_num:
                        try:
                            uyari_metni = f"⏳ <b>Hamlenizi yapmak için SON 30 SANİYE!</b> Mesajı yanıtlamayı (reply) unutmayın!{kriz_uyari_metni}"
                            await context.bot.send_message(chat_id, uyari_metni, parse_mode='HTML')
                        except Exception: pass
                    await asyncio.sleep(30)
            else:
                break 
        
        await asyncio.sleep(2) 
        RPG_GAMES.pop(chat_id, None)
        
    except Exception as e:
        print(f"Kritik Oyun Hatası: {e}")
        if chat_id in RPG_GAMES:
            await context.bot.send_message(chat_id, f"⚠️ Oyun motorunda kritik bir hata oluştu ve oyun iptal edildi.\nHata detayı: {e}")
            RPG_GAMES.pop(chat_id, None)

# ANKET CEVAP YAKALAYICI (3. Tur İçin)
async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    
    if poll_id in RPG_POLLS:
        chat_id = RPG_POLLS[poll_id]["chat_id"]
        options = RPG_POLLS[poll_id]["options"]
        
        if chat_id in RPG_GAMES:
            game = RPG_GAMES[chat_id]
            if game["status"] == "playing" and user_id in game["players"]:
                if game["players"][user_id]["status"] == "alive":
                    selected_opts = [options[i] for i in answer.option_ids]
                    if selected_opts:
                        action_text = "Anket Seçimi: " + ", ".join(selected_opts)
                        if game["players"][user_id]["action"] is None:
                            game["players"][user_id]["action"] = action_text
                            user_name = game["players"][user_id]["name"]
                            game["recorded_actions"].append(user_name)
                            
                            new_caption = game["current_caption"] + "\n\n✅ <b>Hamlesi Kaydedilenler:</b> " + ", ".join(game["recorded_actions"])
                            try:
                                if game["is_photo_msg"]:
                                    await context.bot.edit_message_caption(chat_id=chat_id, message_id=game["last_message_id"], caption=new_caption, parse_mode='HTML')
                                else:
                                    await context.bot.edit_message_text(chat_id=chat_id, message_id=game["last_message_id"], text=new_caption, parse_mode='HTML')
                            except Exception: pass

# CANLI MESAJ YAKALAYICI
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_chat: return
    chat_id = update.effective_chat.id
    
    if chat_id in ALLOWED_GROUPS:
        msg = update.effective_message
        
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
                        except Exception: pass 
                        return 

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
        res = await safe_generate(
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
        await status_msg.edit_text(f"❌ Yapay zeka soruyu üretemedi (Yoğunluk Olabilir): {e}")
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
        res = await safe_generate(
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


# /amahaber KOMUTU
async def amahaber_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    if update.effective_user.id not in ADMIN_IDS: return

    target_msg = update.message.reply_to_message if update.message.reply_to_message else update.message
    
    photo_obj = target_msg.photo[-1] if target_msg.photo else None
    if not photo_obj:
        await update.message.reply_text("❗ Lütfen komutu bir haber görseliyle birlikte gönderin veya bir görsele yanıt verin.")
        return

    metin = target_msg.caption or update.message.text
    if not metin:
        await update.message.reply_text("❗ Lütfen haber metnini de ekleyin.")
        return

    temiz_metin = re.sub(r'(?i)^/amahaber(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    if not temiz_metin:
        temiz_metin = "Son dakika haberi!" 

    status_msg = await update.message.reply_text("📰 Haber inceleniyor, tartışma yaratacak anket hazırlanıyor...")
    
    prompt = f"""Şu haber metnini incele: "{temiz_metin}"
Bu habere dayanarak, insanların tartışabileceği, farklı fikirler sunabileceği, kışkırtıcı veya düşündürücü 1 anket sorusu ve tam olarak 4 adet şık oluştur.
ŞARTLAR:
1. Şıklarda KESİNLİKLE emoji KULLANMA.
2. Her bir şık MAKSİMUM 10 KELİME olmalıdır.

Yanıtını tam olarak şu formatta ver (Başka hiçbir açıklama yazma):
Soru: [Anket Sorusu]
1- [Şık 1]
2- [Şık 2]
3- [Şık 3]
4- [Şık 4]"""

    try:
        res = await safe_generate(
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
        question_text = "Haber Hakkında Ne Düşünüyorsunuz?"
        
        for line in lines:
            if line.startswith("Soru:"):
                question_text = line.replace("Soru:", "").strip()
            elif re.match(r'^[1-4][-.)]\s*', line):
                clean_opt = re.sub(r'^[1-4][-.)]\s*', '', line).strip()
                clean_opt = clean_opt.replace('*', '') 
                parsed_options.append(clean_opt)
        
        options = parsed_options if len(parsed_options) == 4 else ["Katılıyorum", "Katılmıyorum", "Emin değilim", "Fikrim yok"]
    except Exception as e:
        await status_msg.edit_text(f"❌ Yapay zeka soruyu üretemedi: {e}")
        return

    question_text = question_text[:290] 
    safe_options = [opt[:95] for opt in options]

    photo_file = await photo_obj.get_file()
    f = io.BytesIO()
    await photo_file.download_to_memory(f)
    
    success_count = 0
    error_messages = []
    
    for group_id in ALLOWED_GROUPS:
        try:
            f.seek(0)
            await context.bot.send_photo(chat_id=group_id, photo=f, caption=f"📰 <b>HABER:</b>\n\n{temiz_metin}", parse_mode='HTML')
            await context.bot.send_poll(chat_id=group_id, question=question_text, options=safe_options, is_anonymous=False)
            success_count += 1
        except Exception as e:
            error_messages.append(f"❌ {group_id} ID'li gruba gönderilemedi: `{e}`")
    
    if success_count > 0: 
        await status_msg.edit_text(f"✅ Haber ve anket {success_count} gruba başarıyla gönderildi!")
    else: 
        await status_msg.edit_text(f"⚠️ Gönderim başarısız!\n" + "\n".join(error_messages))


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
        prompt = "Görseldeki kahve lekelerini somut nesnelere benzeterek mahalledeki 'Falcı Abla' karakteriyle yorumla. Çok laubali olmadan, samimi ama ölçülü, robotik olmayan doğal bir dille konuş. Kendi ismin 'Falcı Abla'. Maksimum 150 kelime kullan ve asla yıldız(*) işareti kullanma. Her paragrafın başına içeriğine uygun bir emoji ekle."
        res = await safe_generate(
            contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")],
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )
        await status_msg.edit_text(f"☕ Falcı Abla:\n\n{res.text}")
    except: await status_msg.edit_text("⚠️ Fincanı okuyamadım (Sistem yoğun).")

async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    status_msg = await update.message.reply_text("🔄 İnceleniyor...")
    try:
        if target.photo:
            photo_file = await target.photo[-1].get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = await safe_generate(contents=["Bu resmi Türkçe özetle.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
        else:
            res = await safe_generate(contents=f"Özetle: {target.text or target.caption}")
        await status_msg.edit_text(f"📝 ÖZET:\n\n{res.text}")
    except: await status_msg.edit_text("❌ Hata (Sistem yoğun).")

async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    
    async def fetch_tarot():
        return await safe_generate(
            contents=f"Tarot kartları: {', '.join(secilenler)}. Geçmiş, şimdi ve geleceği ayrı paragraflarda yorumla. Daha samimi, candan ve içten bir dil kullan. Maksimum 120 kelime kullan ama asla yıldız işareti(*) kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.",
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE')
                ]
            )
        )

    gen_task = asyncio.create_task(fetch_tarot())
    
    steps = [
        "🌌 Kutsal enerjiler kartlara aktarılıyor...",
        "✨ Ruhani boyutta bağ kuruluyor...",
        "👁️ Geçmiş, şimdi ve gelecek için üç kart çekiliyor...",
        "🔮 Kaderin gizemli fısıltıları dinleniyor..."
    ]
    
    for step in steps:
        await asyncio.sleep(3)
        try: await status.edit_text(step)
        except Exception: pass 
            
    try:
        res = await gen_task
        tarot_image = f"https://image.pollinations.ai/prompt/mystical_tarot_cards_reading_table_with_three_cards_on_it?width=800&height=400&nologo=true"
        await status.delete()
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=tarot_image,
            caption=f"🔮 <b>TAROT FALI:</b>\n\n🃏 Seçilen Kartlar: {', '.join(secilenler)}\n\n{res.text}",
            parse_mode='HTML'
        )
    except Exception as e: 
        await status.edit_text(f"Tüh bağlantı koptu (Sistem yoğun).\n\nHata Detayı: `{e}`")

async def main():
    keep_alive()
    asyncio.create_task(background_scheduler())
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    allowed_filter = filters.Chat(chat_id=ALLOWED_GROUPS) | (filters.ChatType.PRIVATE & filters.User(user_id=ADMIN_IDS))
    interaction_filter = filters.TEXT | filters.COMMAND | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL
    
    application.add_handler(MessageHandler(interaction_filter & (~allowed_filter), reject_unauthorized))
    
    application.add_handler(CallbackQueryHandler(rpg_callback, pattern='^rpg_'))
    application.add_handler(PollAnswerHandler(poll_answer_handler))
    
    # Komutlar
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/rpgpuan'), rpgpuan_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/puanyedek'), puanyedek_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/puanla'), puanla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/rpg'), rpg_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/iptalrpg'), iptalrpg_command)) 
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/update'), update_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ama\b'), ama_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/amahaber'), amahaber_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/getir'), getir_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/anketle'), anketle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))

    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO) & (~filters.COMMAND), log_message))
    
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
