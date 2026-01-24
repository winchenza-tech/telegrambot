
import telebot
import time
from flask import Flask
from threading import Thread
# --- AYARLAR ---
TOKEN = "8483171566:AAFQvX8C4bFHLKvjLbjJErcu9TRCrqSANtY"

# BURAYA DİKKAT: Artık tek bir isim değil, bir liste var.
# İstediğiniz kadar paketi tırnak içinde, aralarına virgül koyarak ekleyebilirsiniz.
YASAKLI_PAKETLER = [
    "OldiesButGoldies5",
    "ino8723"

]
# ----------------

bot = telebot.TeleBot(TOKEN)

# ### YENİ EKLENEN WEB SUNUCUSU KISMI ###
# Bu kısım Render'ın botu "aktif bir websitesi" sanmasını sağlar.
app = Flask('')

@app.route('/')
def home():
    return "Bot Çalışıyor! Ben buradayım."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ### YENİ EKLENEN WEB SUNUCUSU BİTİŞİ ###

print("Bot aktif. Birden fazla paket kontrol ediliyor...")

@bot.message_handler(content_types=['sticker'])
def sticker_kontrol(message):
    try:
        gelen_paket = message.sticker.set_name
        chat_id = message.chat.id
        message_id = message.message_id


        if gelen_paket in YASAKLI_PAKETLER:
            bot.delete_message(chat_id, message_id)
            bot.send_message(chat_id, "🚫 Bu sticker yasaklı stickerlar arasında. Mesaj silindi!")


    except Exception as e:
        print(f"Hata: {e}")
keep_alive()
bot.infinity_polling()



