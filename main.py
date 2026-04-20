import os
import re 
import io
import random
import asyncio
import nest_asyncio
import requests 
import datetime
import pytz
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# --- 1. WEB SUNUCUSU (Keep Alive) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Zenithar Services Aktif! (Sticker Yasağı Kaldırıldı)"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. AYARLAR VE TANIMLAMALAR ---
nest_asyncio.apply()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_SERVICES")  
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL_NAME = 'gemini-2.0-flash'

client = genai.Client(api_key=GOOGLE_API_KEY)

ZODIAC_LIST = [
    "koç", "boğa", "ikizler", "yengeç", "aslan", "başak", 
    "terazi", "akrep", "yay", "oğlak", "kova", "balık"
]

TAROT_CARDS = [
    "Deli", "Büyücü", "Azize", "İmparatoriçe", "İmparator", "Aziz",
    "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı", "Adalet",
    "Asılan Adam", "Ölüm", "Denge", "Şeytan", "Yıkılan Kule", "Yıldız",
    "Ay", "Güneş", "Mahkeme", "Dünya"
]

# --- 3. YARDIMCI FONKSİYONLAR ---

def turkce_karakter_duzelt(metin):
    metin = metin.lower().strip()
    duzeltmeler = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'i̇': 'i'}
    for kaynak, hedef in duzeltmeler.items():
        metin = metin.replace(kaynak, hedef)
    return metin

# --- 4. KOMUT MOTORLARI ---

# ✨ GÜNCEL VERİ VE ARAMA DESTEKLİ BURÇ MOTORU
async def burcyorumla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = update.message.text.lower()
    temiz_args = re.sub(r'^/burcyorumla(?:@[a-zA-Z0-9_]+)?\s*', '', metin).strip()
    
    if not temiz_args:
        await update.message.reply_text("❗ Bir burç yazmalısın. Örnek: /burcyorumla akrep")
        return

    burc_input = turkce_karakter_duzelt(temiz_args)
    
    if burc_input not in ZODIAC_LIST:
        await update.message.reply_text("Mal mısın? Burç ismini doğru yaz.")
        return
    
    status_msg = await update.message.reply_text(f"🛰️ {burc_input.capitalize()} için bugünün gökyüzü haritası internetten taranıyor...")

    try:
        tz = pytz.timezone("Europe/Istanbul")
        bugun = datetime.datetime.now(tz).strftime("%d %B %Y")
        
        prompt = (f"Bugünün tarihi: {bugun}. İnternetten {burc_input} burcu için bugünkü gerçek astrolojik yorumları, "
                  f"gezegen konumlarını ve uzman yorumlarını araştır. Bu bilgileri sentezleyerek "
                  f"Zenithar tarzında, bilge, hafif gizemli ve etkileyici bir dille Türkçe yorumla. "
                  f"Maks 120 kelime olsun. Bilimsel/astrolojik terimlere (evler, açılar) yer ver.")
        
        res = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearchRetrieval())]
            )
        )
        await status_msg.edit_text(f"✨ {burc_input.upper()} YORUMU ({bugun}):\n\n{res.text}")
    except Exception as e:
        print(f"Burç Hatası: {e}")
        await status_msg.edit_text("❌ Yıldızlar şu an çok karışık, internetten veri çekemedim.")

# ☕ GELİŞMİŞ GÖRSEL ANALİZLİ KAHVE FALI
async def falbak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_obj = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    
    if not photo_obj:
        await update.message.reply_text("☕ Fal için fincan fotosu göndermeli veya bir fotoya yanıt vermelisin.")
        return

    status_msg = await update.message.reply_text("☕ Telveler inceleniyor, klişelerden uzak bir analiz yapılıyor...")
    
    try:
        photo_file = await photo_obj.get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
        
        prompt = ("Görseldeki kahve fincanı lekelerini çok dikkatli incele. "
                  "Lekelerin oluşturduğu şekilleri (örneğin: şahlanmış at, anahtar, çatallı yol, kuş silüeti, yaşlı adam yüzü vb.) somut nesnelere benzet. "
                  "KESİNLİKLE 'üç vakte kadar haber var', 'yolun açık', 'kısmetin geliyor' gibi klişeleri kullanma. "
                  "Gördüğün somut şekiller üzerinden mistik, derin ve biraz da dobra bir yorum yap. "
                  "Eğer görselde net şekiller yoksa kullanıcıyı 'fincanı düzgün çek' diye uyar.")
        
        res = client.models.generate_content(
            model=MODEL_NAME, 
            contents=[prompt, types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")]
        )
        await status_msg.edit_text(f"☕ Zenithar Falcı Teyze Diyor Ki:\n\n{res.text}")
    except Exception as e:
        print(f"Fal Hatası: {e}")
        await status_msg.edit_text("⚠️ Fincanın enerjisi çok ağır, okuyamadım.")

# 📝 ÖZETLEME MOTORU
async def ozetle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message if update.message.reply_to_message else update.message
    if not target: return

    if target.photo:
        status_msg = await update.message.reply_text("🖼️ Görsel analiz ediliyor...")
        try:
            photo_file = await target.photo[-1].get_file(); f = io.BytesIO(); await photo_file.download_to_memory(f); f.seek(0)
            res = client.models.generate_content(model=MODEL_NAME, contents=["Bu resmi Türkçe özetle. Maks 50 kelime.", types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")])
            await status_msg.edit_text(f"📝 GÖRSEL ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Görsel okunamadı.")
    elif target.text or target.caption:
        status_msg = await update.message.reply_text("📝 Metin özetleniyor...")
        try:
            res = client.models.generate_content(model=MODEL_NAME, contents=f"Aşağıdaki metni ana hatlarıyla Türkçe özetle: {target.text or target.caption}")
            await status_msg.edit_text(f"📝 METİN ÖZETİ:\n\n{res.text}")
        except: await status_msg.edit_text("❌ Metin özetlenemedi.")

# 🃏 TAROT MOTORU
async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secilenler = random.sample(TAROT_CARDS, 3)
    status = await update.message.reply_text("🃏 Kartlar karıştırılıyor...")
    try:
        prompt = (f"Tarot kartları: {', '.join(secilenler)}. Bu üç kartı geçmiş, şimdi ve gelecek olarak yorumla. "
                  "Mistik ama anlaşılır bir dil kullan. '*' sembolü kullanma. 3 ayrı paragraf olsun.")
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        await status.edit_text(f"🔮 TAROT FALI:\n\n🃏 Kartlar: {', '.join(secilenler)}\n\n📜 Yorum:\n{res.text}")
    except: await status.edit_text("❌ Ruhlar dünyasıyla bağlantı koptu.")

# --- 5. ANA ÇALIŞTIRICI ---

async def main():
    keep_alive()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Komut Yakalayıcılar
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/tarotbak'), tarot_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/burcyorumla'), burcyorumla_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/ozetle'), ozetle_command))
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^/falbak'), falbak_command))
    
    print("Zenithar Services Bot (Sticker Yasağı Kaldırıldı) Başlatıldı...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Kritik Hata: {e}")
