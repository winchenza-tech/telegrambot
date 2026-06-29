import os
import time
from datetime import datetime
import pytz
import tweepy
# Yeni kütüphane import edildi
from google import genai
from apscheduler.schedulers.blocking import BlockingScheduler

# 1. Ortam Değişkenlerini Yükle
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. API Bağlantılarını Başlat
# Yeni nesil Gemini İstemcisi başlatma yöntemi
client_gemini = genai.Client(api_key=GEMINI_API_KEY)

# Twitter API v2 İstemcisi
twitter_client = tweepy.Client(
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET
)

def generate_and_post_tweet():
    tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tz)
    current_hour = now.hour

    # Gece 01:00 ile 10:00 arası tweet atmama kontrolü
    if 1 <= current_hour < 10:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Saat {current_hour}:00. Gece sessizlik modu aktif, tweet atılmadı.")
        return

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Gündem taranıyor ve tweet hazırlanıyor...")

    try:
        prompt = (
            "Şu anki gerçek Türkiye ve dünya gündemini, sosyal medyada yapay veya bot hesaplarca şişirilmemiş, "
            "insanların gerçekten konuştuğu somut ve gerçek konuları analiz et. "
            "Bu konulardan biri hakkında; son derece esprili, muzip, ironik, akıl dolu ve zeki bir tweet üret. "
            "Kural 1: Tweet kesinlikle 280 karakteri geçmesin. "
            "Kural 2: Yapay zeka gibi kokmasın, samimi ve sarkastik bir insan yazmış gibi olsun. "
            "Kural 3: Hashtag (#) kullanma veya çok nadir, espriye dahilse kullan. "
            "Sadece tweet metnini döndür, başında veya sonunda başka açıklama olmasın."
        )

        # Yeni kütüphaneye göre içerik üretimi (gemini-2.5 veya gemini-1.5-flash kullanılabilir)
        response = client_gemini.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        tweet_text = response.text.strip()

        if tweet_text.startswith('"') and tweet_text.endswith('"'):
            tweet_text = tweet_text[1:-1]

        # Twitter'da Paylaş
        twitter_client.create_tweet(text=tweet_text)
        print(f"Tweet başarıyla paylaşıldı:\n👉 {tweet_text}")

    except Exception as e:
        print(f"Bir hata oluştu: {e}")

if __name__ == "__main__":
    tz = pytz.timezone('Europe/Istanbul')
    
    # Başlangıç zamanını 23:23 olarak ayarlıyoruz
    start_time = datetime.now(tz).replace(hour=23, minute=34, second=0, microsecond=0)
    
    print(f"Bot başlatıldı... İlk zamanlama ayarı: {start_time.strftime('%H:%M')} -> Tekrar: 85 dakikada bir.")

    scheduler = BlockingScheduler(timezone=tz)
    
    scheduler.add_job(
        generate_and_post_tweet, 
        'interval', 
        minutes=85, 
        start_date=start_time
    )
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Bot durduruldu.")
