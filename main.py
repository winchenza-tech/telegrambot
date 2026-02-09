import telebot
import time
from flask import Flask
from threading import Thread

# --- AYARLAR ---
# DİKKAT: Güvenliğin için bu tokenı kimseyle paylaşmamalısın!
TOKEN = "8483171566:AAFQvX8C4bFHLKvjLbjJErcu9TRCrqSANtY"

# Yasaklı paket listesi güncellendi
YASAKLI_PAKETLER = [
    "OldiesButGoldies5",
    "ino8723",
    "gq0bpksh8_1003369169896_by_QuotLyBot" # Yeni paket eklendi
]
# ----------------

bot = telebot.TeleBot(TOKEN)

# ### WEB SUNUCUSU KISMI ###
app = Flask('')

@app.route('/')
def home():
    return "Bot Çalışıyor! Ben buradayım."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# #########################

print("Bot aktif. Yasaklı paketler kontrol ediliyor...")

@bot.message_handler(content_types=['sticker'])
def sticker_kontrol(message):
    try:
        gelen_paket = message.sticker.set_name
        chat_id = message.chat.id
        message_id = message.message_id

        # Paketin listede olup olmadığını kontrol et
        if gelen_paket in YASAKLI_PAKETLER:
            bot.delete_message(chat_id, message_id)
            bot.send_message(chat_id, f"🚫 @{message.from_user.username}, bu sticker paketi yasaklı olduğu için mesajın silindi!")

    except Exception as e:
        print(f"Hata: {e}")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
