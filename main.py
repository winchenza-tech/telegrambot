import os
import re 
import io
import random
import time # Çakışma önleyici için eklendi
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
UPDATE_HOUR = 2  # Gece otomatik güncelleme saati (Türkiye saati ile 02:00)
ADMIN_IDS = [7094870780, 8639720888]  # Admin ID'leri (Sadece bu ID'ler özelden yazabilir, /update ve /ama çalıştırabilir)
ALLOWED_GROUPS = [-1003938704852, -1003297262036] # Sadece bu gruplarda çalışmasına izin verilir

# --- WEB SUNUCUSU (Uygulamayı 7/24 Ayakta Tutar) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Manuel Başlangıç ve 02:00 Güncelleme Modu)"

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

# Yapay Zeka Model Adı 2.5 Flash olarak güncellendi
MODEL_NAME = 'gemini-2.5-flash'

client = genai.Client(api_key=GOOGLE_API_KEY)

# HAFIZA VE KİLİT SİSTEMİ
VALID_ZODIACS = [
    "koc", "boga", "ikizler", "yengec", "aslan", "basak", 
    "terazi", "akrep", "yay", "oglak", "kova", "balik"
]
# Başlangıçta içi boş
HOROSCOPE_CACHE = {burc: "" for burc in VALID_ZODIACS}

# Aynı anda birden fazla güncelleme çalışmasını engelleyen KİLİT
IS_UPDATING = False 

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
    """Komutların içerisindeki erişim kontrolü - Yeni güvenlik mesajıyla güncellendi"""
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
    """Yetkisiz erişimlerde devreye giren özel fırça mesajı"""
    if not update.effective_message: return
    await update.effective_message.reply_text("Bu botun yalnızca belirli gruplarda çalışmasına izin verdim. Sana yetki yok @eskidenyesil")

# --- 3. GARANTİLİ GÜNCELLEME MOTORU (Başarana Kadar Dener) ---

async def update_all_horoscopes():
    global IS_UPDATING
    
    if IS_UPDATING:
        print("⚠️ Uyarı: Güncelleme zaten arka planda devam ediyor. Çakışma önlendi.")
        return
        
    IS_UPDATING = True 
    tz = pytz.timezone("Europe/Istanbul")
    bugun = datetime.datetime.now(tz).strftime("%d-%m-%Y")
    print(f"🔄 {bugun} için GARANTİLİ TOPLU GÜNCELLEME BAŞLADI...")
    
    try:
        for burc in VALID_ZODIACS:
            success = False
            retry_count = 0
            
            while not success:
                try:
                    print(f"📡 {burc.upper()} internetten çekiliyor (Deneme: {retry_count + 1})...")
                    prompt = (f"Bugün {bugun}. {burc} burcu için internetten en güncel astrolojik gelişmeleri bul. "
                              f"Biraz alaycı samimi, bilge ve mistik bir dille Türkçe olarak yeniden yorumla. Maks 135 kelime kullan. "
                              f"Bu prompt hakkında bilgi verme. yani elbette tamam gibi şeyler söyleme sadece alaycı ve gizemli astrolog yorumunu yaz. Biraz espri katabilirsin. 2 paragraf şeklinde yaz Asla yıldız (*) simgesi kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.")
                    
                    res = await client.aio.models.generate_content(
                        model=MODEL_NAME, 
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )
                    
                    HOROSCOPE_CACHE[burc] = res.text
                    print(f"✅ {burc.upper()} başarıyla hafızaya alındı.")
                    success = True 
                    
                except Exception as e:
                    retry_count += 1
                    print(f"❌ Hata ({burc}): {e}. Google'ı dinlendirmek için 90 saniye bekleniyor...")
                    if HOROSCOPE_CACHE[burc] == "":
                        HOROSCOPE_CACHE[burc] = "Şu anda tüm zenithar yıldızlara bakarak sigara içiyor 5 dakika sonra tekrar dene."
                    await asyncio.sleep(90) 
            
            if burc != VALID_ZODIACS[-1]: 
                print(f"⏳ {burc.upper()} tamamlandı. Diğer burca geçmeden önce 90 saniye dinlenme...")
                await asyncio.sleep(90) 
                
        print("✅ TÜM BURÇLAR (12/12) HAFIZAYA BAŞARIYLA KAYDEDİLDİ!")
    finally:
        IS_UPDATING = False

async def background_scheduler():
    """Bot ilk açıldığında BEKLER. Sadece gece 02:00'de otomatik tetiklenir."""
    print("🚀 Sistem başlatıldı. İlk hafıza dolumu için Admin'den /update komutu bekleniyor veya gece 02:00 bekleniyor...")
    
    while True:
        tz = pytz.timezone("Europe/Istanbul")
        now = datetime.datetime.now(tz)
        
        if now.hour == UPDATE_HOUR and now.minute == 0:
            await update_all_horoscopes()
            await asyncio.sleep(60)
            
        await asyncio.sleep(30)

# --- 4. KOMUT MOTORLARI ---

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_UPDATING
    if update.effective_user.id not in ADMIN_IDS: return 
    
    if IS_UPDATING:
        await update.message.reply_text(" Bot şu anda zaten bir güncelleme yapıyor. Lütfen bitmesini bekle.")
    else:
        await update.message.reply_text("🔄 Manuel toplu güncelleme başlatıldı.\nHer burç arası 90 saniye bekleniyor.\nİşlem yaklaşık 18 dakika sürecektir.")
        asyncio.create_task(update_all_horoscopes())

# 👑 YENİ ADMİN ÖZEL KOMUT (Anket - /ama) - MAKS 10 KELİME ŞIK VE BAŞA EMOJİ EKLENDİ
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

    # Varsayılan değerler
    emoji = "🤔"
    trait = "eski sevgilisiyle hala yakın arkadaş"
    options = [
        "Sıkıntı yok güveniyorsam tamam",
        "Duruma ve karşındakine göre değişir",
        "Kesinlikle sorun çıkarırım",
        "Direkt yol veririm",
        "Böyle saçmalık olmaz amk"
    ]

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
        
        for line in lines:
            if line.startswith("Emoji:"):
                emoji = line.replace("Emoji:", "").strip()
            elif line.startswith("Özellik:"):
                trait = line.replace("Özellik:", "").strip()
            elif re.match(r'^[1-5][-.)]\s*', line):
                clean_opt = re.sub(r'^[1-5][-.)]\s*', '', line).strip()
                clean_opt = clean_opt.replace('*', '') 
                parsed_options.append(clean_opt)
        
        if len(parsed_options) == 5:
            options = parsed_options

    except Exception as e:
        print(f"Ama komutu AI hatası veya Parse hatası: {e}")

    # Başında emoji ile Soru Formatı
    question_text = f"{emoji} {gender} {score}/10 ama {trait}?"
    question_text = question_text[:290] # Soru max 300 karakter

    # Şıkları benzersiz yap (Duplicate Option Hatasını Önle) ve 100 karaktere kırp
    safe_options = []
    for opt in options:
        clean_opt = opt[:95] # Şık max 100 karakter
        if clean_opt not in safe_options:
            safe_options.append(clean_opt)
        else:
            safe_options.append(clean_opt + " (Katılıyorum)") # Aynı şık varsa sonuna kelime ekle
            
    if len(safe_options) < 2:
        safe_options = ["Evet", "Hayır"] # En kötü ihtimalde çökmesin diye kurtarma
        
    success_count = 0
    error_messages = []
    
    for group_id in ALLOWED_GROUPS:
        try:
            await context.bot.send_poll(
                chat_id=group_id,
                question=question_text,
                options=safe_options,
                is_anonymous=False 
            )
            success_count += 1
        except Exception as e:
            error_text = f"❌ {group_id} ID'li gruba gönderilemedi.\nTelegram Hatası: `{e}`"
            print(error_text)
            error_messages.append(error_text)
    
    if success_count > 0:
        await status_msg.edit_text(f"✅ Soru {success_count} gruba anket olarak gönderildi!\n\nGönderilen Soru: {emoji} {gender} {score}/10 ama {trait}")
    else:
        hata_raporu = "\n\n".join(error_messages)
        await status_msg.edit_text(f"⚠️ Anket 0 gruba gönderildi! Sorun Telegram tarafından engellendi.\n\nİşte detaylar:\n{hata_raporu}")


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

    if yorum == "":
        await update.message.reply_text("🛰️ Yıldızlar henüz uyanmadı. Lütfen yönetici güncellemeyi başlatana kadar veya gece güncellemesi yapılana kadar bekle.")
    else:
        await update.message.reply_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{yorum}")


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
            model=MODEL_NAME, 
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
            model=MODEL_NAME, 
            contents=f"Tarot kartları: {', '.join(secilenler)}. Geçmiş, şimdi ve geleceği ayrı paragraflarda yorumla. maksimum 120 kelime kullan ama asla yıldız işareti(*) kullanma. Her paragrafın başına o paragrafa uygun bir emoji ekle.",
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
    
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/update'), update_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ama'), ama_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
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
