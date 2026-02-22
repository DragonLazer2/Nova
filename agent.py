import argparse
import asyncio
import anthropic
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chat_history.json")

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

Never use emojis in your responses.\
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
    "excited": {"rate": "+20%", "pitch": "+8%"},
    "cheerful": {"rate": "+15%", "pitch": "+5%"},
    "empathetic": {"rate": "+5%", "pitch": "-3%"},
    "sad": {"rate": "+5%", "pitch": "-5%"},
    "curious": {"rate": "+15%", "pitch": "+3%"},
}

TONE_KEYWORDS = {
    "excited": ["amazing", "awesome", "fantastic", "incredible", "wow", "exciting", "love it", "great news", "so cool", "wild"],
    "cheerful": ["glad", "happy", "wonderful", "welcome", "hi ", "hey ", "hello", "good to", "nice"],
    "empathetic": ["sorry", "understand", "that must", "tough", "difficult", "hard time", "feel for you"],
    "sad": ["unfortunately", "sadly", "bad news", "heartbreaking", "tragic"],
    "curious": ["curious", "interesting", "wonder", "what if", "how does", "tell me"],
}


def _detect_tone(text: str) -> dict:
    """Detect emotional tone and return pitch/rate adjustments."""
    lower = text.lower()
    for tone, keywords in TONE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return TONE_MAP[tone]
    return {"rate": "+15%", "pitch": "+0Hz"}


def speak(text: str) -> None:
    """Speak text aloud using edge-tts neural voice with emotional inflection."""
    import edge_tts

    tone = _detect_tone(text)

    async def _synth():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        communicate = edge_tts.Communicate(text, VOICE, rate=tone["rate"], pitch=tone["pitch"])
        await communicate.save(tmp)
        return tmp

    tmp = asyncio.run(_synth())
    subprocess.Popen(["afplay", tmp]).wait()
    os.unlink(tmp)


class SpeechQueue:
    """Queues sentence chunks and speaks them in a background thread."""

    SENTENCE_ENDINGS = {".","!","?"}

    def __init__(self):
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while True:
            chunk = self._queue.get()
            if chunk is None:
                break
            speak(chunk)

    def say(self, sentence: str) -> None:
        """Add a sentence to be spoken."""
        self._queue.put(sentence)

    def finish(self) -> None:
        """Signal no more sentences and wait for speech to complete."""
        self._queue.put(None)
        self._thread.join()


def listen() -> str | None:
    """Listen to the microphone and return recognized speech, or None on failure."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.0
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
            print(text, end="", flush=True)
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

    assistant_message = "".join(response_parts)
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
        print("Nova: Welcome back! I remember our previous conversations.")
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
        greeting = "Welcome back! I remember our previous conversations."
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
