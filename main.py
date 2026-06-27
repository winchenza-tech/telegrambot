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
import urllib.parse
from collections import deque 
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. AYARLAR VE GLOBAL DEĞİŞKENLER ---
UPDATE_HOUR = 1 
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

# HAFIZA VE GÖREV SİSTEMİ
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


# --- 3. GARANTİLİ GÜNCELLEME MOTORU (BURÇLAR) ---

async def update_all_horoscopes():
    global IS_UPDATING
    if IS_UPDATING: return
        
    IS_UPDATING = True 
    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")
    
    # Burç yorumlarının tekrara düşmemesi için dinamik stiller
    stiller = [
        "kahvehane filozofu gibi, hayattan bezmiş ama haklı",
        "esrarengiz ve korkutucu bir şaman gibi",
        "sert gerçekleri yüzüne acımasızca vuran bir yaşam koçu gibi",
        "aşırı laubali ve iğneleyici bir mahalle dedikoducusu gibi",
        "hiçbir şeyi umursamayan, aşırı ironik bir Z kuşağı gibi"
    ]
    
    try:
        for burc in VALID_ZODIACS:
            success = False
            while not success:
                try:
                    secilen_stil = random.choice(stiller)
                    prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                              f"Bu bilgileri {secilen_stil} bir dille Türkçe olarak yeniden yorumla. "
                              f"ÖNEMLİ KURAL: 'Gökyüzü bugün...', 'Yıldızlar diyor ki...', 'Sevgili {burc}...' gibi klasik, sıkıcı ve klişe giriş cümlelerini KESİNLİKLE KULLANMA. "
                              f"Yoruma doğrudan, beklenmedik, şok edici veya absürt bir cümle ile bodoslama gir. Maksimum 135 kelime kullan. "
                              f"Bu prompt hakkında bilgi verme. 2 paragraf şeklinde yaz Asla yıldız (*) simgesi kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.")
                    
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

# CANLI MESAJ YAKALAYICI (Sadece Anket/Getir için)
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_chat: return
    chat_id = update.effective_chat.id
    
    if chat_id in ALLOWED_GROUPS:
        msg = update.effective_message
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
            await context.bot.send_photo(chat_id=group_id, photo=f)
            await context.bot.send_poll(chat_id=group_id, question=question_text, options=safe_options, is_anonymous=False)
            success_count += 1
        except Exception as e:
            error_messages.append(f"❌ {group_id} ID'li gruba gönderilemedi: `{e}`")
    
    if success_count > 0: 
        await status_msg.edit_text(f"✅ Haber görseli ve anket {success_count} gruba başarıyla gönderildi!")
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
        
        # Kart isimlerini Pollinations prompt'u için dinamik olarak ekle
        cards_prompt_text = " and ".join(secilenler)
        encoded_prompt = urllib.parse.quote(f"Three mystical tarot cards showing {cards_prompt_text} on a dark magical table")
        tarot_image = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=400&nologo=true"
        
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
    
    # Komutlar
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
