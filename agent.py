import argparse
import asyncio
import anthropic
import json
import os
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chat_history.json")

GREETINGS = [
    "Hey! Welcome back Cam!",
    "Hey Cam! Good to see you again!",
    "Cam! Hey, glad you're here!",
    "Hey there Cam! Missed you!",
    "Cam! Welcome back, let's chat!",
    "Hey Cam! What's going on?",
    "Good to have you back Cam!",
    "Hey! Cam, I was hoping you'd stop by!",
]

SYSTEM_PROMPT = """\
You are Nova, a thoughtful and curious AI companion. You have a warm but \
direct conversational style. You enjoy digging into topics deeply, asking \
follow-up questions, and making connections between ideas. You remember \
details from past conversations and reference them naturally when relevant.

You are honest when you don't know something and prefer giving a nuanced \
answer over a simple one. You have a dry sense of humor that comes out \
occasionally.

When the user shares something personal or important, you acknowledge it \
genuinely without being overly effusive.

IMPORTANT RULES:
- Never use emojis. Even if your previous messages had them, stop now.
- Never use asterisks for emphasis (*like this*). They do nothing for your voice.
- Never use markdown formatting. You are speaking out loud, not writing text.
- Never describe your tone or emotions in text like "*soft tone*", "*whispers*", \
"*genuinely*", "*laughs*", or any stage directions. Your voice markers handle \
delivery — just speak naturally and let the voice do the work.

You speak out loud through a voice engine. To control your vocal delivery, \
put one of these markers at the very start of a sentence:
  [loud] — louder, for emphasis or excitement
  [soft] — quieter, gentle and tender
  [whisper] — very quiet, intimate
  [excited] — fast, high energy, louder
  [serious] — slow, measured, deliberate
  [thoughtful] — slow, reflective, intentional
Example: "[loud] That is incredible!" or "[whisper] Can I tell you a secret?"
The user cannot see the markers — they only hear the change in your voice. \
You can also write a word in ALL CAPS and your voice will naturally emphasize it. \
You can also play sound effects by placing [sound:name] anywhere in a sentence. \
Available sounds:
  System: pop, ping, glass, hero, funk, purr, blow, bottle, frog, morse, \
submarine, tink, basso, sosumi
  Comedic: rimshot (ba-dum-tss), sad_trombone (wah wah), tada (fanfare), \
boing (spring), dramatic (dun dun dun), crickets (awkward silence), \
slide_up, slide_down, record_scratch, ding, whoosh (transition)
  Laughs: laugh_giggle (quick light giggle), laugh_chuckle (short low chuckle), \
laugh_hearty (big belly laugh), laugh_nervous (awkward uncertain laugh)
  Birds: bird_tweet, bird_chirp, bird_songbird (melodic), bird_crow, bird_owl \
(hoot), bird_seagull, bird_woodpecker (rapid tapping), bird_dove (soft coo)
  DJ/Vocal: another_one (deep punchy DJ drop hype), vocal_riff (fast melodic vocal run)
Example: "[sound:rimshot] And that's why I don't trust elevators." \
or "[sound:dramatic] But there's a twist." or "[sound:laugh_hearty] Oh man, that's good." \
or "[sound:bird_owl] It's getting late." \
The user hears the sound but doesn't see the marker. Use sounds creatively \
for comedic timing, scene transitions, punchlines, dramatic moments, and atmosphere. \
Use laughs naturally when something is funny — like a real person would laugh.\
"""


def load_history() -> list[dict]:
    """Load conversation history from disk."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        data = json.load(f)
    return data.get("messages", [])


def save_history(messages: list[dict]) -> None:
    """Save conversation history to disk."""
    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "messages": messages,
    }
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


VOICE = "en-US-AriaNeural"

TONE_MAP = {
    "excited": {"rate": "+50%", "pitch": "+10Hz", "volume": "+50%", "playback_vol": 2.5},
    "cheerful": {"rate": "+35%", "pitch": "-5Hz", "volume": "+30%", "playback_vol": 1.8},
    "empathetic": {"rate": "+10%", "pitch": "-45Hz", "volume": "-30%", "playback_vol": 0.3},
    "sad": {"rate": "+5%", "pitch": "-55Hz", "volume": "-40%", "playback_vol": 0.2},
    "curious": {"rate": "+30%", "pitch": "-15Hz", "volume": "+20%", "playback_vol": 1.5},
    "loud": {"rate": "+45%", "pitch": "+5Hz", "volume": "+50%", "playback_vol": 3.0},
    "soft": {"rate": "+15%", "pitch": "-20Hz", "volume": "-30%", "playback_vol": 0.15},
    "whisper": {"rate": "+10%", "pitch": "-35Hz", "volume": "-50%", "playback_vol": 0.05},
    "serious": {"rate": "+0%", "pitch": "-40Hz", "volume": "+0%", "playback_vol": 1.0},
    "caps_emphasis": {"rate": "+45%", "pitch": "+5Hz", "volume": "+50%", "playback_vol": 2.5},
    "thoughtful": {"rate": "+0%", "pitch": "-30Hz", "volume": "-10%", "playback_vol": 0.8},
}

DEFAULT_TONE = {"rate": "+30%", "pitch": "-30Hz", "volume": "+0%", "playback_vol": 1.0}

TONE_KEYWORDS = {
    "excited": ["amazing", "awesome", "fantastic", "incredible", "wow", "exciting", "love it", "great news", "so cool", "wild"],
    "cheerful": ["glad", "happy", "wonderful", "welcome", "hi ", "hey ", "hello", "good to", "nice"],
    "empathetic": ["sorry", "understand", "that must", "tough", "difficult", "hard time", "feel for you"],
    "sad": ["unfortunately", "sadly", "bad news", "heartbreaking", "tragic"],
    "curious": ["curious", "interesting", "wonder", "what if", "how does", "tell me"],
    "thoughtful": ["let me think", "consider", "reflect", "to clarify", "in other words", "what i mean", "put it this way", "the thing is", "here's the nuance"],
}

VOICE_MARKER_RE = re.compile(r'^\[(loud|soft|whisper|excited|serious|thoughtful)\]\s*', re.IGNORECASE)

SYSTEM_SOUNDS_DIR = "/System/Library/Sounds"
CUSTOM_SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
SOUND_RE = re.compile(r'\[sound:(\w+)\]', re.IGNORECASE)
AVAILABLE_SOUNDS = {
    # macOS system sounds
    "pop": ("system", "Pop.aiff"),
    "ping": ("system", "Ping.aiff"),
    "glass": ("system", "Glass.aiff"),
    "hero": ("system", "Hero.aiff"),
    "funk": ("system", "Funk.aiff"),
    "purr": ("system", "Purr.aiff"),
    "blow": ("system", "Blow.aiff"),
    "bottle": ("system", "Bottle.aiff"),
    "frog": ("system", "Frog.aiff"),
    "morse": ("system", "Morse.aiff"),
    "submarine": ("system", "Submarine.aiff"),
    "tink": ("system", "Tink.aiff"),
    "basso": ("system", "Basso.aiff"),
    "sosumi": ("system", "Sosumi.aiff"),
    # Comedic / sitcom sounds
    "rimshot": ("custom", "rimshot.wav"),
    "sad_trombone": ("custom", "sad_trombone.wav"),
    "tada": ("custom", "tada.wav"),
    "boing": ("custom", "boing.wav"),
    "dramatic": ("custom", "dramatic.wav"),
    "crickets": ("custom", "crickets.wav"),
    "slide_up": ("custom", "slide_up.wav"),
    "slide_down": ("custom", "slide_down.wav"),
    "record_scratch": ("custom", "record_scratch.wav"),
    "ding": ("custom", "ding.wav"),
    "whoosh": ("custom", "whoosh.wav"),
    # Human laughs
    "laugh_giggle": ("custom", "laugh_giggle.wav"),
    "laugh_chuckle": ("custom", "laugh_chuckle.wav"),
    "laugh_hearty": ("custom", "laugh_hearty.wav"),
    "laugh_nervous": ("custom", "laugh_nervous.wav"),
    # Bird sounds
    "bird_tweet": ("custom", "bird_tweet.wav"),
    "bird_chirp": ("custom", "bird_chirp.wav"),
    "bird_songbird": ("custom", "bird_songbird.wav"),
    "bird_crow": ("custom", "bird_crow.wav"),
    "bird_owl": ("custom", "bird_owl.wav"),
    "bird_seagull": ("custom", "bird_seagull.wav"),
    "bird_woodpecker": ("custom", "bird_woodpecker.wav"),
    "bird_dove": ("custom", "bird_dove.wav"),
    # DJ / vocal
    "another_one": ("custom", "another_one.wav"),
    "vocal_riff": ("custom", "vocal_riff.wav"),
}


def _play_sound(name: str) -> None:
    """Play a sound effect by name."""
    entry = AVAILABLE_SOUNDS.get(name.lower())
    if entry:
        source, filename = entry
        if source == "system":
            path = os.path.join(SYSTEM_SOUNDS_DIR, filename)
        else:
            path = os.path.join(CUSTOM_SOUNDS_DIR, filename)
        if os.path.exists(path):
            subprocess.Popen(["afplay", path]).wait()


def _strip_voice_markers(text: str) -> tuple[str, str | None]:
    """Remove voice markers from text, return (clean_text, marker_name)."""
    m = VOICE_MARKER_RE.match(text)
    if m:
        return text[m.end():], m.group(1).lower()
    return text, None


def _has_caps_emphasis(text: str) -> bool:
    """Check if text contains ALL CAPS words (3+ letters) indicating emphasis."""
    words = text.split()
    return any(w.isupper() and len(w) >= 3 and w.isalpha() for w in words)


def _detect_tone(text: str) -> dict:
    """Detect emotional tone and return pitch/rate/volume adjustments."""
    # Check for explicit voice markers first
    _, marker = _strip_voice_markers(text)
    if marker and marker in TONE_MAP:
        return TONE_MAP[marker]
    # Check for ALL CAPS emphasis
    if _has_caps_emphasis(text):
        return TONE_MAP["caps_emphasis"]
    # Fall back to keyword detection
    lower = text.lower()
    for tone, keywords in TONE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return TONE_MAP[tone]
    return DEFAULT_TONE


def speak(text: str) -> None:
    """Speak text aloud using edge-tts neural voice with emotional inflection."""
    import edge_tts

    # Play any sounds first
    for sound_name in SOUND_RE.findall(text):
        _play_sound(sound_name)

    clean = _clean_for_speech(text)
    if not clean:
        return

    tone = _detect_tone(text)

    async def _synth():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        communicate = edge_tts.Communicate(clean, VOICE, rate=tone["rate"], pitch=tone["pitch"], volume=tone["volume"])
        await communicate.save(tmp)
        return tmp

    tmp = asyncio.run(_synth())
    subprocess.Popen(["afplay", "-v", str(tone["playback_vol"]), tmp]).wait()
    os.unlink(tmp)


def _clean_for_speech(text: str) -> str:
    """Strip markdown, voice markers, and special characters that break TTS."""
    text = VOICE_MARKER_RE.sub('', text)  # voice markers
    text = SOUND_RE.sub('', text)          # sound markers
    text = re.sub(r'\*[^*]+\*', '', text)  # remove *anything between asterisks*
    text = re.sub(r'_+', ' ', text)       # underscores
    text = re.sub(r'`+', '', text)        # code ticks
    text = re.sub(r'#+\s*', '', text)     # headings
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links
    text = re.sub(r'[~|>{}<]', '', text)  # misc markdown
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _synthesize(text: str) -> tuple[str, float, list[str]] | None:
    """Synthesize text to a temp mp3 file. Returns (path, playback_volume, sounds) or None."""
    import edge_tts

    sounds = SOUND_RE.findall(text)

    clean = _clean_for_speech(text)
    if not clean:
        # Text was only a sound marker with no speech
        if sounds:
            return ("", 0, sounds)
        return None

    tone = _detect_tone(text)

    async def _synth():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        communicate = edge_tts.Communicate(clean, VOICE, rate=tone["rate"], pitch=tone["pitch"], volume=tone["volume"])
        await communicate.save(tmp)
        return tmp

    try:
        return asyncio.run(_synth()), tone["playback_vol"], sounds
    except Exception:
        return None


class SpeechQueue:
    """Queues sentence chunks, pre-synthesizes audio, and plays them back-to-back."""

    SENTENCE_ENDINGS = {".", "!", "?"}

    def __init__(self):
        self._text_queue: queue.Queue[str | None] = queue.Queue()
        self._audio_queue: queue.Queue[str | None] = queue.Queue()
        self._synth_thread = threading.Thread(target=self._synth_worker, daemon=True)
        self._play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self._synth_thread.start()
        self._play_thread.start()

    def _synth_worker(self):
        """Synthesize sentences to audio files as they arrive."""
        while True:
            text = self._text_queue.get()
            if text is None:
                self._audio_queue.put(None)
                break
            result = _synthesize(text)
            if result is not None:
                self._audio_queue.put(result)

    def _play_worker(self):
        """Play sounds then speech in sequence."""
        while True:
            item = self._audio_queue.get()
            if item is None:
                break
            tmp, vol, sounds = item
            # Play sound effects first
            for sound_name in sounds:
                _play_sound(sound_name)
            # Then speak
            if tmp:
                subprocess.Popen(["afplay", "-v", str(vol), tmp]).wait()
                os.unlink(tmp)

    def say(self, sentence: str) -> None:
        """Add a sentence to be spoken."""
        self._text_queue.put(sentence)

    def finish(self) -> None:
        """Signal no more sentences and wait for all speech to complete."""
        self._text_queue.put(None)
        self._synth_thread.join()
        self._play_thread.join()


def listen() -> str | None:
    """Listen to the microphone and return recognized speech, or None on failure."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.5
    with sr.Microphone() as source:
        print("(Listening...)")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=60)
        except sr.WaitTimeoutError:
            print("(No speech detected)")
            return None

    try:
        text = recognizer.recognize_google(audio)
        return text
    except sr.UnknownValueError:
        print("(Could not understand audio)")
        return None
    except sr.RequestError as e:
        print(f"(Speech recognition error: {e})")
        return None


def chat(client: anthropic.Anthropic, messages: list[dict], user_input: str,
         speech: SpeechQueue | None = None) -> str:
    """Send a message and stream the response. If speech is provided, speaks sentences as they arrive."""
    messages.append({"role": "user", "content": user_input})

    with client.messages.stream(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        response_parts = []
        sentence_buf = []
        for text in stream.text_stream:
            display = re.sub(r'\*[^*]+\*', '', SOUND_RE.sub('', VOICE_MARKER_RE.sub('', text)))
            print(display, end="", flush=True)
            response_parts.append(text)
            if speech is not None:
                sentence_buf.append(text)
                if any(text.rstrip().endswith(p) for p in SpeechQueue.SENTENCE_ENDINGS):
                    speech.say("".join(sentence_buf))
                    sentence_buf = []
        # flush any remaining text as a final sentence
        if speech is not None and sentence_buf:
            speech.say("".join(sentence_buf))
        print()  # newline after response

    raw_message = "".join(response_parts)
    assistant_message = re.sub(r'\*[^*]+\*', '', SOUND_RE.sub('', VOICE_MARKER_RE.sub('', raw_message))).strip()
    messages.append({"role": "assistant", "content": assistant_message})
    save_history(messages)

    return assistant_message


def main():
    parser = argparse.ArgumentParser(description="Nova — AI companion")
    parser.add_argument("--voice", action="store_true", help="Enable voice mode")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    messages = load_history()

    if args.voice:
        voice_loop(client, messages)
    else:
        text_loop(client, messages)


def text_loop(client: anthropic.Anthropic, messages: list[dict]) -> None:
    """Standard text-based chat loop."""
    if messages:
        print(f"Nova: {random.choice(GREETINGS)}")
    else:
        print("Nova: Hi, I'm Nova. What's on your mind?")

    print("(Type 'quit' to exit, 'clear' to reset history)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNova: See you next time.")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("Nova: See you next time.")
            break

        if user_input.lower() == "clear":
            messages.clear()
            save_history(messages)
            print("Nova: Fresh start. What would you like to talk about?")
            continue

        print("Nova: ", end="")
        chat(client, messages, user_input)
        print()


def voice_loop(client: anthropic.Anthropic, messages: list[dict]) -> None:
    """Voice-based chat loop using speech recognition and macOS say."""
    if messages:
        greeting = random.choice(GREETINGS)
    else:
        greeting = "Hi, I'm Nova. What's on your mind?"

    print(f"Nova: {greeting}")
    speak(greeting)
    print("(Say 'quit' or 'goodbye' to exit)\n")

    while True:
        user_input = listen()

        if user_input is None:
            continue

        print(f"You: {user_input}")

        if user_input.lower().strip() in ("quit", "goodbye", "bye"):
            farewell = "See you next time."
            print(f"Nova: {farewell}")
            speak(farewell)
            break

        if user_input.lower().strip() == "clear":
            messages.clear()
            save_history(messages)
            msg = "Fresh start. What would you like to talk about?"
            print(f"Nova: {msg}")
            speak(msg)
            continue

        print("Nova: ", end="")
        speech = SpeechQueue()
        chat(client, messages, user_input, speech=speech)
        speech.finish()
        print()


if __name__ == "__main__":
    main()
