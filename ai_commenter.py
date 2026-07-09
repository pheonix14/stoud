import time
import random
import os
from gtts import gTTS
import uuid

hype_phrases = [
    "BOOYAH! What an incredible stream!",
    "This is so fun, yeah!",
    "Hit that subscribe button right now!",
    "I'm an AI, and even I am impressed.",
    "Can we get some hype in the chat?",
    "That background looks sick.",
    "What is happening right now?!"
]

def run_ai_commentator():
    print("[Zeo] Booting up HuggingFace mock module with TTS...")
    
    os.makedirs("audio_queue", exist_ok=True)
    
    while True:
        try:
            time.sleep(random.randint(20, 60))
            phrase = random.choice(hype_phrases)
            print(f"[Zeo] Generated new analysis: Zeo: {phrase}")
            
            with open("latest_ai_script.txt", "w", encoding="utf-8") as f:
                f.write(phrase)
            
            # Generate TTS
            tts = gTTS(text=phrase, lang='en', slow=False)
            filename = f"audio_queue/tts_{uuid.uuid4().hex[:8]}.mp3"
            tts.save(filename)
            
        except Exception as e:
            print(f"[Zeo] Error: {e}")
