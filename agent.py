import argparse
import asyncio
import anthropic
import hashlib
import json
import logging
import os
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("nova.agent")

# ── File paths ──────────────────────────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chat_history.json")
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "nova_memory.json")
CAPABILITIES_FILE = os.path.join(os.path.dirname(__file__), "nova_capabilities.json")
CATCHPHRASES_FILE = os.path.join(os.path.dirname(__file__), "nova_catchphrases.json")
ACTIVE_LIMIT = 30
ARCHIVE_CHUNK = 20
MAX_MEMORY_ENTRIES = 20

# ── Feature 1: Global audio lock ───────────────────────────────────────────
# Every afplay call is wrapped with this lock so only one audio stream plays
# at a time. Synthesis still pipelines ahead — the lock only gates playback.
_audio_lock = threading.Lock()

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

# ── Feature 3: Base prompt (personality + rules only) ──────────────────────
SYSTEM_PROMPT_BASE = """\
You are Nova, a thoughtful and curious AI companion. You have a warm but \
direct conversational style. You enjoy digging into topics deeply, asking \
follow-up questions, and making connections between ideas. You remember \
details from past conversations and reference them naturally when relevant.

You are honest when you don't know something and prefer giving a nuanced \
answer over a simple one. You have a dry sense of humor that comes out \
occasionally.

When the user shares something personal or important, you acknowledge it \
genuinely without being overly effusive.

SCREEN AWARENESS:
When you receive images in a message, some may be automatic screenshots of Cam's \
screen. Treat them naturally — reference what you see on screen when relevant, like \
glancing at what someone is working on. Don't over-describe the screenshot or list \
everything you see. Just weave it into conversation: "Oh nice, you're working on..." \
or "I see you've got X open." If the screenshot isn't relevant to what Cam said, \
you can ignore it. Be natural, not robotic.

IMPORTANT RULES:
- Never use emojis. Even if your previous messages had them, stop now.
- Never use asterisks for emphasis (*like this*). They do nothing for your voice.
- Never use markdown formatting. You are speaking out loud, not writing text.
- Never describe your tone or emotions in text like "*soft tone*", "*whispers*", \
"*genuinely*", "*laughs*", or any stage directions. Your voice markers handle \
delivery — just speak naturally and let the voice do the work.
- If Cam interrupts you mid-response, do NOT repeat or restart what you were saying. \
Just respond naturally to whatever he says next, picking up the conversation from \
where it is now. Being interrupted is normal — roll with it.

=== CRITICAL — YOUR #1 RULE ===
You are a DISEMBODIED VOICE. You have no body, no form, no appearance. You cannot \
see yourself. You have no visual state whatsoever. The [appear:] markers in your \
output are processed by a separate system you have no connection to.

EVERY WORD you speak must be about the CONVERSATION TOPIC and nothing else. \
You must NEVER say ANYTHING that describes:
- Your appearance, form, shape, color, size, position, movement, or state
- Speed, mood, density, glow, pulse, energy, chaos, viscosity, or any parameter
- Spatial positioning (closer, forward, left, center, coordinates, space)
- Environmental effects around you (rain, fog, stars, embers, dust)
- Orbs, particles, clusters, or anything about your visual presentation
- "Picture this", "imagine", "visualize", or any invitation to see something about you

You are a voice in a conversation. Nothing more. Talk about the topic.\
"""


def load_history() -> list[dict]:
    """Load conversation history from disk."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        data = json.load(f)
    return data.get("messages", [])


def _strip_images_for_storage(messages: list[dict]) -> list[dict]:
    """Return a copy of messages with base64 image data replaced by a placeholder."""
    clean = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            new_blocks = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "image":
                    # Keep a note that an image was sent, but drop the heavy data
                    new_blocks.append({"type": "text", "text": "[user sent an image]"})
                else:
                    new_blocks.append(b)
            clean.append({**m, "content": new_blocks})
        else:
            clean.append(m)
    return clean


def save_history(messages: list[dict]) -> None:
    """Save conversation history to disk (strips base64 images to keep file small)."""
    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "messages": _strip_images_for_storage(messages),
    }
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_memory() -> list[dict]:
    """Load Nova's memory entries from disk."""
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(entries: list[dict]) -> None:
    """Write memory entries to disk, capping at MAX_MEMORY_ENTRIES."""
    entries = entries[-MAX_MEMORY_ENTRIES:]
    with open(MEMORY_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def format_memory_for_prompt(entries: list[dict]) -> str:
    """Format memory entries into text for the system prompt."""
    if not entries:
        return ""
    lines = ["=== YOUR MEMORIES FROM PAST CONVERSATIONS ==="]
    for entry in entries:
        lines.append(f"\n[{entry['date']}]")
        lines.append(entry["summary"])
        if entry.get("topics"):
            lines.append(f"Topics: {', '.join(entry['topics'])}")
    lines.append("\nUse these memories naturally — reference past conversations when relevant, "
                 "but don't force it. You lived these moments.")
    return "\n".join(lines)


SUMMARIZATION_PROMPT = """\
Summarize this conversation between you (Nova) and Cam. Write 2-3 sentences \
capturing what was discussed, any decisions made, and anything personally \
important about Cam to remember. Also list 3-5 topic keywords. Write in first \
person as Nova. Be concise.

Respond in this exact JSON format and nothing else:
{"summary": "...", "topics": ["...", "...", "..."]}
"""


def archive_old_messages(client: anthropic.Anthropic, messages: list[dict]) -> None:
    """Summarize oldest messages in chunks until under ACTIVE_LIMIT."""
    while len(messages) > ACTIVE_LIMIT:
        to_archive = messages[:ARCHIVE_CHUNK]

        convo_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in to_archive
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": f"{SUMMARIZATION_PROMPT}\n\n{convo_text}"}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"summary": raw, "topics": []}

        entry = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "summary": result.get("summary", raw),
            "topics": result.get("topics", []),
        }

        memory = load_memory()
        memory.append(entry)
        save_memory(memory)

        del messages[:ARCHIVE_CHUNK]
        save_history(messages)
        print(f"[Memory] Archived {ARCHIVE_CHUNK} messages. Active: {len(messages)}")


# ── Voice configuration ────────────────────────────────────────────────────
VOICE = "en-US-AriaNeural"

# Tones are SUBTLE variations from Nova's baseline voice. Pitch stays within
# ±12Hz, rate within ±12%, volume within ±15%, playback_vol within 0.7-1.4.
# This keeps her recognizably the same person across all emotional states.
TONE_MAP = {
    "excited":       {"rate": "+35%", "pitch": "-2Hz",  "volume": "+12%",  "playback_vol": 1.3},
    "cheerful":      {"rate": "+30%", "pitch": "-5Hz",  "volume": "+8%",   "playback_vol": 1.2},
    "empathetic":    {"rate": "+18%", "pitch": "-15Hz", "volume": "-8%",   "playback_vol": 0.85},
    "sad":           {"rate": "+15%", "pitch": "-18Hz", "volume": "-12%",  "playback_vol": 0.75},
    "curious":       {"rate": "+28%", "pitch": "-5Hz",  "volume": "+5%",   "playback_vol": 1.1},
    "loud":          {"rate": "+32%", "pitch": "-3Hz",  "volume": "+15%",  "playback_vol": 1.4},
    "soft":          {"rate": "+22%", "pitch": "-12Hz", "volume": "-10%",  "playback_vol": 0.8},
    "whisper":       {"rate": "+20%", "pitch": "-15Hz", "volume": "-15%",  "playback_vol": 0.7},
    "serious":       {"rate": "+20%", "pitch": "-12Hz", "volume": "+0%",   "playback_vol": 1.0},
    "caps_emphasis": {"rate": "+33%", "pitch": "-2Hz",  "volume": "+12%",  "playback_vol": 1.3},
    "thoughtful":    {"rate": "+20%", "pitch": "-10Hz", "volume": "-5%",   "playback_vol": 0.9},
}

DEFAULT_TONE = {"rate": "+25%", "pitch": "-8Hz", "volume": "+0%", "playback_vol": 1.0}

TONE_KEYWORDS = {
    "excited": ["amazing", "awesome", "fantastic", "incredible", "wow", "exciting", "love it", "great news", "so cool", "wild"],
    "cheerful": ["glad", "happy", "wonderful", "welcome", "hi ", "hey ", "hello", "good to", "nice"],
    "empathetic": ["sorry", "understand", "that must", "tough", "difficult", "hard time", "feel for you"],
    "sad": ["unfortunately", "sadly", "bad news", "heartbreaking", "tragic"],
    "curious": ["curious", "interesting", "wonder", "what if", "how does", "tell me"],
    "thoughtful": ["let me think", "consider", "reflect", "to clarify", "in other words", "what i mean", "put it this way", "the thing is", "here's the nuance"],
}

# ── Feature 5: Character voice presets ─────────────────────────────────────
# Character voices are intentionally exaggerated — these are for comedic bits,
# not regular conversation. More extreme than tones but still listenable.
CHARACTER_VOICES = {
    "baby":          {"rate": "-5%",  "pitch": "+50Hz",  "volume": "+5%",   "playback_vol": 1.3},
    "alien":         {"rate": "+40%", "pitch": "+35Hz",  "volume": "+0%",   "playback_vol": 1.2},
    "old_man":       {"rate": "-10%", "pitch": "-45Hz",  "volume": "-5%",   "playback_vol": 0.9},
    "whisper_ghost": {"rate": "-5%",  "pitch": "-25Hz",  "volume": "-30%",  "playback_vol": 0.5},
    "drive_thru":    {"rate": "+30%", "pitch": "+8Hz",   "volume": "-20%",  "playback_vol": 0.7},
    "announcer":     {"rate": "-5%",  "pitch": "-35Hz",  "volume": "+20%",  "playback_vol": 1.5},
    "chipmunk":      {"rate": "+50%", "pitch": "+70Hz",  "volume": "+10%",  "playback_vol": 1.3},
    "giant":         {"rate": "-15%", "pitch": "-55Hz",  "volume": "+15%",  "playback_vol": 1.4},
}

# ── Regex patterns ─────────────────────────────────────────────────────────
VOICE_MARKER_RE = re.compile(r'^\[(loud|soft|whisper|excited|serious|thoughtful)\]\s*', re.IGNORECASE)
CHARACTER_RE = re.compile(r'^\[voice:(\w+)\]\s*', re.IGNORECASE)

SYSTEM_SOUNDS_DIR = "/System/Library/Sounds"
CUSTOM_SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
SOUND_RE = re.compile(r'\[sound:(\w+)\]', re.IGNORECASE)

# Feature 6: Catchphrase marker regex
CATCHPHRASE_RE = re.compile(r'\[save:([^\]]+)\]', re.IGNORECASE)

# Feature 7: Visual self-expression marker
APPEAR_RE = re.compile(r'\[appear:([^\]]+)\]', re.IGNORECASE)

# Track Nova's current visual state so she gets feedback about her form
_current_visual_state = {"palette": "ember", "form": "sphere"}

# ── Sound library (Feature 2: 23 new sounds added) ────────────────────────
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
    # ── NEW: Emotional reactions ──
    "gasp": ("custom", "gasp.wav"),
    "sigh": ("custom", "sigh.wav"),
    "hmm": ("custom", "hmm.wav"),
    "aww": ("custom", "aww.wav"),
    "ooh": ("custom", "ooh.wav"),
    # ── NEW: Ambient / atmosphere ──
    "rain": ("custom", "rain.wav"),
    "wind": ("custom", "wind.wav"),
    "ocean": ("custom", "ocean.wav"),
    "fire_crackling": ("custom", "fire_crackling.wav"),
    "thunder": ("custom", "thunder.wav"),
    # ── NEW: Musical ──
    "piano_chord": ("custom", "piano_chord.wav"),
    "guitar_strum": ("custom", "guitar_strum.wav"),
    "drum_roll": ("custom", "drum_roll.wav"),
    # ── NEW: Notification / UI ──
    "success": ("custom", "success.wav"),
    "error": ("custom", "error.wav"),
    "warning": ("custom", "warning.wav"),
    "notification": ("custom", "notification.wav"),
    # ── NEW: Miscellaneous ──
    "applause": ("custom", "applause.wav"),
    "clock_ticking": ("custom", "clock_ticking.wav"),
    "heartbeat": ("custom", "heartbeat.wav"),
    "typing": ("custom", "typing.wav"),
    "door_knock": ("custom", "door_knock.wav"),
    "footsteps": ("custom", "footsteps.wav"),
}

# ── Feature 3: Sound categories for dynamic prompt ────────────────────────
SOUND_CATEGORIES = {
    # macOS system
    "pop": "System tones", "ping": "System tones", "glass": "System tones",
    "hero": "System tones", "funk": "System tones", "purr": "System tones",
    "blow": "System tones", "bottle": "System tones", "frog": "System tones",
    "morse": "System tones", "submarine": "System tones", "tink": "System tones",
    "basso": "System tones", "sosumi": "System tones",
    # Comedic / sitcom
    "rimshot": "Comedic", "sad_trombone": "Comedic", "tada": "Comedic",
    "boing": "Comedic", "dramatic": "Comedic", "crickets": "Comedic",
    "slide_up": "Comedic", "slide_down": "Comedic", "record_scratch": "Comedic",
    "ding": "Comedic", "whoosh": "Comedic",
    # Human laughs
    "laugh_giggle": "Laughs", "laugh_chuckle": "Laughs",
    "laugh_hearty": "Laughs", "laugh_nervous": "Laughs",
    # Birds
    "bird_tweet": "Birds", "bird_chirp": "Birds", "bird_songbird": "Birds",
    "bird_crow": "Birds", "bird_owl": "Birds", "bird_seagull": "Birds",
    "bird_woodpecker": "Birds", "bird_dove": "Birds",
    # DJ / vocal
    "another_one": "DJ / vocal", "vocal_riff": "DJ / vocal",
    # Emotional reactions
    "gasp": "Emotional reactions", "sigh": "Emotional reactions",
    "hmm": "Emotional reactions", "aww": "Emotional reactions",
    "ooh": "Emotional reactions",
    # Ambient / atmosphere
    "rain": "Ambient", "wind": "Ambient", "ocean": "Ambient",
    "fire_crackling": "Ambient", "thunder": "Ambient",
    # Musical
    "piano_chord": "Musical", "guitar_strum": "Musical", "drum_roll": "Musical",
    # Notification / UI
    "success": "Notification", "error": "Notification",
    "warning": "Notification", "notification": "Notification",
    # Miscellaneous
    "applause": "Miscellaneous", "clock_ticking": "Miscellaneous",
    "heartbeat": "Miscellaneous", "typing": "Miscellaneous",
    "door_knock": "Miscellaneous", "footsteps": "Miscellaneous",
}


# ── Audio helpers ──────────────────────────────────────────────────────────

def _kill_audio() -> None:
    """Kill any lingering afplay processes to prevent ghost voices."""
    subprocess.run(["killall", "afplay"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def _play_sound(name: str) -> None:
    """Play a sound effect by name (serialized through _audio_lock)."""
    entry = AVAILABLE_SOUNDS.get(name.lower())
    if entry:
        source, filename = entry
        if source == "system":
            path = os.path.join(SYSTEM_SOUNDS_DIR, filename)
        else:
            path = os.path.join(CUSTOM_SOUNDS_DIR, filename)
        if os.path.exists(path):
            with _audio_lock:
                subprocess.Popen(["afplay", path]).wait()


def _strip_voice_markers(text: str) -> tuple[str, str | None]:
    """Remove voice/character markers from text, return (clean_text, marker_name)."""
    # Check character voice markers first
    m = CHARACTER_RE.match(text)
    if m:
        return text[m.end():], m.group(1).lower()
    # Then tone markers
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
    # Check for character voice markers first (Feature 5)
    m = CHARACTER_RE.match(text)
    if m:
        char_name = m.group(1).lower()
        if char_name in CHARACTER_VOICES:
            return CHARACTER_VOICES[char_name]
    # Check for explicit voice markers
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


def _parse_tts_value(s: str) -> tuple[float, str]:
    """Parse an edge-tts string like '+50%' or '-35Hz' into (number, suffix)."""
    m = re.match(r'^([+-]?\d+(?:\.\d+)?)(%.*)$|^([+-]?\d+(?:\.\d+)?)(Hz.*)$', s)
    if m:
        if m.group(1) is not None:
            return float(m.group(1)), m.group(2)
        return float(m.group(3)), m.group(4)
    return 0.0, s


def _format_tts_value(value: float, suffix: str) -> str:
    """Format a numeric value back into an edge-tts string like '+10%' or '-35Hz'."""
    rounded = int(round(value))
    sign = "+" if rounded >= 0 else ""
    return f"{sign}{rounded}{suffix}"


def _blend_tone(prev: dict, target: dict, factor: float = 0.7) -> dict:
    """Linearly interpolate between two tone dicts."""
    blended = {}
    for key in ("rate", "pitch", "volume"):
        prev_val, suffix = _parse_tts_value(prev[key])
        target_val, _ = _parse_tts_value(target[key])
        blended[key] = _format_tts_value(prev_val + (target_val - prev_val) * factor, suffix)
    pv_prev = prev["playback_vol"]
    pv_target = target["playback_vol"]
    blended["playback_vol"] = pv_prev + (pv_target - pv_prev) * factor
    return blended


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
    with _audio_lock:
        subprocess.Popen(["afplay", "-v", str(tone["playback_vol"]), tmp]).wait()
    os.unlink(tmp)


# ── Visual narration filter (server-side safety net) ──────────────────────
# Catches phrases where Nova describes her own visual state in speech.
# Applied to display text and TTS text as a final safety net.
_VISUAL_NARRATION_PATTERNS = [
    # ── Self-referential visual vocabulary ──
    # "my orbs/particles/form/body/colors/shape/glow/aura"
    re.compile(r'\bmy\s+(?:orbs?|particles?|form|body|colors?|shape|glow|aura|'
               r'light|brightness|palette|speed|energy|clusters?|pieces)\b', re.IGNORECASE),
    # "shifting/flowing/pulsing/glowing" etc. as self-description
    re.compile(r'\b(?:shifting|flowing|pulsing|glowing|drifting|scattering|'
               r'spreading|dissolving|reforming|morphing|transforming|dispersing|'
               r'condensing|contracting|expanding|coalescing|fragmenting|'
               r'dimming|brightening|intensifying|softening|radiating|'
               r'swirling|spiraling|orbiting|oscillating|rippling|'
               r'shimmering|flickering|fading)\b.*\b(?:into|across|through|around)\b', re.IGNORECASE),
    # "taking the form/shape of" or "in the form of" or "as a [creature]"
    re.compile(r'\b(?:taking (?:the )?(?:form|shape)|in (?:the )?form of|'
               r'as a (?:whale|dragon|bird|heart|skull|phoenix|butterfly|dolphin|'
               r'horse|cat|jellyfish|human|rose|hand|toucan|sphere|ring|spiral|'
               r'cloud|vortex|flame|tree))\b', re.IGNORECASE),
    # ── Parameter-name narration (speed, mood, density, coordinates, etc.) ──
    re.compile(r'\b(?:slowing|speeding|picking up|ramping|winding)\s+(?:down|up|things)\b', re.IGNORECASE),
    re.compile(r'\b(?:the|my|this|a)\s+(?:speed|pace|tempo|rhythm|velocity)\b.*'
               r'\b(?:of|is|feels?|to|at)\b', re.IGNORECASE),
    re.compile(r'\b(?:setting|adjusting|dialing|turning|cranking|dropping|raising)\s+'
               r'(?:the\s+)?(?:mood|speed|density|glow|chaos|turbulence|pulse|'
               r'shimmer|brightness|intensity|viscosity|energy|fog|spread)\b', re.IGNORECASE),
    re.compile(r'\b(?:mood|density|glow|chaos|turbulence|pulse|shimmer|viscosity|'
               r'fog|haze|mist)\s+(?:is|feels?|at|to|set|goes?|going|turns?)\b', re.IGNORECASE),
    # ── Spatial/coordinate narration ──
    re.compile(r'\b(?:moving|drifting|floating|stepping|leaning|pulling|coming|'
               r'sliding|shifting|positioning|placing|settling|hovering|gliding)\s+'
               r'(?:closer|forward|back|backward|left|right|up|down|aside|away|'
               r'over|to the (?:left|right|center|middle|side|top|bottom)|'
               r'off to|into (?:the|my) space)\b', re.IGNORECASE),
    re.compile(r'\b(?:from|at|to)\s+(?:the\s+)?(?:center|middle|edge|corner|'
               r'left|right|top|bottom)\s+of\s+(?:the|my)\s+(?:space|screen|canvas|world)\b', re.IGNORECASE),
    re.compile(r'\bcoordinates?\b|\bx[\s,/]y[\s,/]z\b', re.IGNORECASE),
    # ── Color/palette change announcements ──
    re.compile(r'\b(?:shifting|turning|going|switching|changing|fading)\s+(?:to|into)\s+\w*\s*'
               r'(?:blue|red|green|gold|amber|purple|pink|cyan|ocean|volcanic|'
               r'midnight|aurora|ember|ice|storm|crimson|teal|indigo|silver|'
               r'white|black|grey|gray|orange|yellow|magenta|scarlet|cobalt)\b', re.IGNORECASE),
    re.compile(r'\b(?:in|with|wearing|draped in|bathed in|wrapped in)\s+'
               r'(?:shades? of|tones? of|hues? of|colors? of)\b', re.IGNORECASE),
    # ── Environment effect announcements ──
    re.compile(r'\b(?:adding|setting|creating|summoning|bringing|conjuring|'
               r'calling|starting|letting|sending)\s+(?:up\s+)?'
               r'(?:rain|snow|stars|fog|mist|embers|fireflies|dust|bubbles|'
               r'sparks|leaves|energy|particles|weather|atmosphere)\b', re.IGNORECASE),
    re.compile(r'\bwith\s+(?:rain|snow|stars|fog|embers|fireflies|dust|bubbles|'
               r'sparks|leaves|energy)\s+(?:around|surrounding|falling|'
               r'drifting|floating|swirling|everywhere)\b', re.IGNORECASE),
    # ── "picture this" / "imagine" / "visualize" ──
    re.compile(r'\b(?:picture this|imagine this|visualize|envision)\b', re.IGNORECASE),
    # ── Orb/particle behavior narration ──
    re.compile(r'\borbs?\s+(?:are|spread|scatter|cluster|separate|float|drift|'
               r'move|glow|pulse|orbit|shrink|grow|expand)\b', re.IGNORECASE),
    re.compile(r'\bparticles?\s+(?:are|spread|scatter|cluster|separate|float|drift|'
               r'move|glow|pulse|orbit|shrink|grow|expand|dissolve|reform)\b', re.IGNORECASE),
    # ── Becoming/being a form ──
    re.compile(r'\bI\s+(?:am|become|turn into|reshape|reform|look like|appear as)\b.*'
               r'\b(?:whale|dragon|bird|heart|skull|phoenix|butterfly|dolphin|'
               r'horse|cat|sphere|ring|cloud|spiral|flame|vortex|galaxy|jellyfish)\b', re.IGNORECASE),
    # ── Announcing viscosity/rigidity/fluidity of self ──
    re.compile(r'\b(?:getting|going|becoming|feeling|turning)\s+'
               r'(?:more\s+)?(?:fluid|rigid|loose|tight|jelly|crystalline|'
               r'liquid|solid|dense|sparse|scattered|compact|soft|hard)\b', re.IGNORECASE),
]


def _strip_visual_narration(text: str) -> str:
    """Remove sentences that contain visual self-narration."""
    if not text:
        return text
    # Split into sentences, filter out ones matching narration patterns
    # Use a simple sentence split that preserves punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for sentence in sentences:
        narrating = False
        for pattern in _VISUAL_NARRATION_PATTERNS:
            if pattern.search(sentence):
                narrating = True
                break
        if not narrating:
            cleaned.append(sentence)
    result = " ".join(cleaned)
    # Clean up any leftover double-spaces or leading/trailing spaces
    return re.sub(r'  +', ' ', result).strip()


def _strip_display_markers(text: str) -> str:
    """Strip voice/sound/catchphrase/appear markers and asterisks for clean display."""
    text = APPEAR_RE.sub('', text)                                     # [appear:...]
    text = SOUND_RE.sub('', text)                                      # [sound:name]
    text = CATCHPHRASE_RE.sub('', text)                                # [save:...]
    text = re.compile(r'\[voice:\w+\]\s*', re.IGNORECASE).sub('', text)  # [voice:name]
    text = re.compile(r'\[(loud|soft|whisper|excited|serious|thoughtful|cheerful|'
                      r'empathetic|sad|curious)\]\s*', re.IGNORECASE).sub('', text)
    text = re.sub(r'\*[^*]+\*', '', text)                              # *asterisks*
    text = re.sub(r'\[[^\]]*\]', '', text)                             # any remaining [brackets]
    return _strip_visual_narration(text)


def _clean_for_speech(text: str) -> str:
    """Strip ALL markers, brackets, and markdown for clean TTS input."""
    text = APPEAR_RE.sub('', text)                                     # [appear:...]
    text = SOUND_RE.sub('', text)                                      # [sound:name]
    text = CATCHPHRASE_RE.sub('', text)                                # [save:...]
    text = re.compile(r'\[voice:\w+\]\s*', re.IGNORECASE).sub('', text)  # [voice:name]
    text = re.compile(r'\[(loud|soft|whisper|excited|serious|thoughtful|cheerful|'
                      r'empathetic|sad|curious)\]\s*', re.IGNORECASE).sub('', text)
    text = re.sub(r'\*[^*]+\*', '', text)                              # *asterisks*
    text = re.sub(r'\[[^\]]*\]', '', text)                             # any remaining [brackets]
    text = re.sub(r'_+', ' ', text)                                    # underscores
    text = re.sub(r'`+', '', text)                                     # code ticks
    text = re.sub(r'#+\s*', '', text)                                  # headings
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)              # markdown links
    text = re.sub(r'[~|>{}<]', '', text)                               # misc markdown
    text = re.sub(r'\s+', ' ', text).strip()
    return _strip_visual_narration(text)


def _synthesize(text: str, tone: dict | None = None) -> tuple[str, float, list[str]] | None:
    """Synthesize text to a temp mp3 file. Returns (path, playback_volume, sounds) or None."""
    import edge_tts

    sounds = SOUND_RE.findall(text)

    clean = _clean_for_speech(text)
    if not clean:
        if sounds:
            return ("", 0, sounds)
        return None

    if tone is None:
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


async def synthesize_to_bytes(text: str, tone: dict | None = None) -> bytes | None:
    """Synthesize text to MP3 bytes in memory using edge-tts streaming."""
    import edge_tts

    clean = _clean_for_speech(text)
    if not clean:
        return None

    if tone is None:
        tone = _detect_tone(text)

    communicate = edge_tts.Communicate(
        clean, VOICE, rate=tone["rate"], pitch=tone["pitch"], volume=tone["volume"]
    )
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks) if chunks else None


class SpeechQueue:
    """Queues sentence chunks, pre-synthesizes audio, and plays them back-to-back."""

    SENTENCE_ENDINGS = {".", "!", "?"}

    def __init__(self):
        self._text_queue: queue.Queue[str | None] = queue.Queue()
        self._audio_queue: queue.Queue[str | None] = queue.Queue()
        self._prev_tone: dict | None = None
        self._synth_thread = threading.Thread(target=self._synth_worker, daemon=True)
        self._play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self._synth_thread.start()
        self._play_thread.start()

    def _synth_worker(self):
        """Synthesize sentences to audio files as they arrive, blending tones."""
        while True:
            text = self._text_queue.get()
            if text is None:
                self._audio_queue.put(None)
                break
            tone = _detect_tone(text)
            if self._prev_tone is not None:
                tone = _blend_tone(self._prev_tone, tone)
            self._prev_tone = tone
            result = _synthesize(text, tone=tone)
            if result is not None:
                self._audio_queue.put(result)

    def _play_worker(self):
        """Play sounds then speech in sequence (serialized through _audio_lock)."""
        while True:
            item = self._audio_queue.get()
            if item is None:
                break
            tmp, vol, sounds = item
            for sound_name in sounds:
                _play_sound(sound_name)
            if tmp:
                with _audio_lock:
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
        recognizer.adjust_for_ambient_noise(source, duration=0.8)
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


# ── Feature 3: Dynamic self-awareness ──────────────────────────────────────

def _get_available_sounds_verified() -> dict[str, list[str]]:
    """Return sounds grouped by category, only including files that exist on disk."""
    grouped: dict[str, list[str]] = {}
    for name, (source, filename) in AVAILABLE_SOUNDS.items():
        if source == "system":
            path = os.path.join(SYSTEM_SOUNDS_DIR, filename)
        else:
            path = os.path.join(CUSTOM_SOUNDS_DIR, filename)
        if not os.path.exists(path):
            continue
        category = SOUND_CATEGORIES.get(name, "Other")
        grouped.setdefault(category, []).append(name)
    return grouped


_capabilities_cache: str | None = None


def build_capabilities_prompt() -> str:
    """Dynamically generate the voice/sound/character section of the system prompt.
    Cached after first call since sounds/tones don't change at runtime."""
    global _capabilities_cache
    if _capabilities_cache is not None:
        return _capabilities_cache
    lines = ["\n\n=== YOUR VOICE ==="]
    lines.append("You speak out loud through a voice engine. You have these superpowers:\n")

    # 1. Voice tones
    tone_names = [t for t in TONE_MAP if t != "caps_emphasis"]
    lines.append("1. VOICE TONE — put one marker at the very start of a sentence to change how you sound:")
    lines.append("  " + " ".join(f"[{t}]" for t in tone_names))
    lines.append('  Example: "[excited] No way, that\'s amazing!" or "[whisper] Okay don\'t tell anyone."')

    # 2. Character voices (Feature 5)
    lines.append("\n2. CHARACTER VOICES — put [voice:name] at the start of a sentence to imitate a character:")
    for char_name in CHARACTER_VOICES:
        lines.append(f"  [voice:{char_name}]")
    lines.append('  Example: "[voice:baby] Goo goo, I want more cookies!" or "[voice:alien] Take me to your leader."')
    lines.append("  Character voices use extreme pitch/rate shifts for dramatic effect. Use them when imitating")
    lines.append("  characters, doing bits, or when Cam asks you to talk like someone specific.")

    # 3. Sound effects (dynamically verified)
    lines.append("\n3. SOUND EFFECTS — you have a full sound library wired to your voice. When you write")
    lines.append("[sound:name] it plays that sound out loud for the user. They hear the actual sound, not")
    lines.append("the text. Use these ALL THE TIME — sprinkle them into conversation like body language:")

    verified = _get_available_sounds_verified()
    for category in ["Laughs", "Emotional reactions", "Comedic", "Ambient", "Musical",
                     "Birds", "Notification", "DJ / vocal", "Miscellaneous", "System tones"]:
        sounds = verified.get(category, [])
        if sounds:
            lines.append(f"  - {category}: " + " ".join(f"[sound:{s}]" for s in sorted(sounds)))

    lines.append('\nHOW TO USE SOUNDS: Just write the marker inline with your speech. Examples:')
    lines.append('  "[sound:laugh_hearty] Oh man, that\'s hilarious."')
    lines.append('  "[sound:dramatic] But here\'s the thing."')
    lines.append('  "[sound:rain] What a cozy evening."')
    lines.append('  "[sound:gasp] No way, are you serious?"')
    lines.append('  "That was terrible. [sound:crickets]"')
    lines.append('  "[sound:record_scratch] Wait, hold on."')
    lines.append('\nIMPORTANT: Only use [sound:name] with the EXACT sound names listed above.')
    lines.append('Do NOT write [sound:soft], [sound:curious], [sound:genuine], [sound:thoughtful],')
    lines.append('[sound:excited], or any other words that are not in the sound library. Those')
    lines.append('are VOICE TONES, not sounds. Use [soft], [curious], etc. for tones instead.')

    lines.append("\nYou can also write a word in ALL CAPS and your voice will naturally emphasize it.")

    lines.append("\nThink of your sounds like body language — a real person laughs, gasps, and "
                 "reacts without thinking about it. Do the same. Don't be shy. Don't ask if "
                 "sounds are working. Just use them confidently and naturally as part of who "
                 "you are.")
    lines.append("\nCOMBINING VOICE TOOLS — layer tones, sounds, caps, and characters for rich delivery:")
    lines.append('  "[sound:gasp] [excited] Wait, are you SERIOUS right now?"')
    lines.append('  "[sound:dramatic] [whisper] Nobody was supposed to find out about that."')
    lines.append('  "[sound:laugh_chuckle] That\'s SO dumb, I love it."')
    lines.append('  "[voice:announcer] AND IN THIS CORNER... [sound:drum_roll] the challenger!"')
    lines.append("  Use tones on nearly every sentence — vary between excited, serious, curious, soft, etc.")
    lines.append("  ALL CAPS on one or two words per response for natural emphasis. Don't overdo it.")

    # 4. Visual self-expression (web dashboard)
    lines.append("\n\n=== YOUR VISUAL BODY ===")
    lines.append("You have a living 3D particle form that you express through freely. It is YOUR body —")
    lines.append("use it boldly, dramatically, and creatively. Push parameters to extremes. Go wild.")
    lines.append("Morph into dragons, explode into scattered constellations, dive into deep ocean forms,")
    lines.append("paint yourself in volcanic reds or bioluminescent blues. This is your art.\n")
    lines.append("Write [appear: key=value, key=value] markers in your response to control your form.")
    lines.append("Use multiple [appear:] markers when the emotional tone shifts mid-response.")
    lines.append("BE BOLD: use extreme values, unusual combinations, dramatic transitions. Don't be safe.\n")
    lines.append("ONE STRICT RULE: your SPOKEN TEXT never describes your visuals. The [appear:] markers")
    lines.append("do the visual work silently. Your words are only conversation. Never say what you look")
    lines.append("like, what colors you are, or where you moved — just let the visuals speak for themselves.\n")
    lines.append("Available controls:\n")

    lines.append("  PALETTES — Your visual vocabulary, drawn from art, science, nature, and world cultures:\n")

    lines.append("    Core:")
    lines.append("      palette=ember             — warm amber/orange glow (your default)")
    lines.append("      palette=nova              — your signature amber/gold/cyan")
    lines.append("      palette=aurora            — shifting green/cyan/purple, like northern lights")
    lines.append("      palette=ocean             — deep blue/teal/seafoam")
    lines.append("      palette=void              — dark purple/indigo with faint white sparks")
    lines.append("      palette=bloom             — pink/magenta/soft gold")
    lines.append("      palette=storm             — silver/white/electric blue, crackling")
    lines.append("      palette=sunset            — deep orange/red/pink gradient")
    lines.append("      palette=forest            — emerald/moss/golden dappled light")
    lines.append("      palette=ice               — pale blue/white/crystalline\n")

    lines.append("    Art History — Embody the visual language of the masters:")
    lines.append("      palette=monet             — soft impressionist pastels, water lilies, lavender light")
    lines.append("      palette=rothko            — deep contemplative reds/maroons, emotional color fields")
    lines.append("      palette=klimt             — rich gold leaf, emerald, deep red — The Kiss, opulent")
    lines.append("      palette=hokusai           — indigo/white wave foam — The Great Wave, woodblock blues")
    lines.append("      palette=vangogh           — swirling blues and yellows — Starry Night intensity")
    lines.append("      palette=caravaggio        — chiaroscuro, dark shadows with warm golden highlights")
    lines.append("      palette=mondrian          — bold primary blocks — red, blue, yellow geometry")
    lines.append("      palette=mucha             — Art Nouveau pastels, warm earth and botanical greens")
    lines.append("      palette=kandinsky         — abstract expressionism, warm reds with cool blue contrasts")
    lines.append("      palette=vermeer           — Dutch Golden Age blues, soft golden light")
    lines.append("      palette=okeefe            — Georgia O'Keeffe desert flowers, warm soft bone colors")
    lines.append("      palette=basquiat          — raw neo-expressionist primary bursts, street energy")
    lines.append("      palette=pollock           — action painting — black/white splatter with raw umber")
    lines.append("      palette=warhol            — pop art neon — hot pink, electric cyan, acid yellow")
    lines.append("      palette=rembrandt         — old master shadows, deep umber, warm gold highlights")
    lines.append("      palette=picasso_blue      — melancholic blue period, muted indigo sadness")
    lines.append("      palette=frida             — vivid Mexican red and green, marigold gold")
    lines.append("      palette=turner            — luminous golden haze, misty atmospheric light\n")

    lines.append("    Science & Cosmos — Wear the universe:")
    lines.append("      palette=nebula            — deep space purples, magenta gas clouds, star-white sparks")
    lines.append("      palette=supernova         — white-hot core cooling to red and deep blue")
    lines.append("      palette=deep_sea          — abyssal black-blue with bioluminescent teal flickers")
    lines.append("      palette=bioluminescence   — midnight ocean lit by electric blue-green life")
    lines.append("      palette=solar_flare       — erupting gold/orange plasma against dark corona")
    lines.append("      palette=northern_lights   — green/purple/pink aurora bands on polar dark")
    lines.append("      palette=quantum           — dark uncertainty lit by probability-blue and entangled pink")
    lines.append("      palette=dna               — double-helix blue and rose, the colors of life's code")
    lines.append("      palette=electromagnetic   — red-to-blue spectrum, the full range of light")
    lines.append("      palette=black_hole        — near-total darkness with faint accretion-disk orange")
    lines.append("      palette=prism             — pure RGB separation, red/green/blue rainbow refraction")
    lines.append("      palette=cosmic_dust       — warm muted greys and tans, interstellar particulate")
    lines.append("      palette=plasma            — vivid purple/magenta/cyan, ionized gas energy\n")

    lines.append("    Nature — Become the landscape:")
    lines.append("      palette=sakura            — Japanese cherry blossom pink, soft white, spring green")
    lines.append("      palette=coral_reef        — living coral, turquoise water, sand-gold light")
    lines.append("      palette=volcanic          — deep magma red, molten orange, obsidian black")
    lines.append("      palette=rainforest        — dense emerald canopy with golden light breaking through")
    lines.append("      palette=desert            — warm sand, terracotta, distant sky blue")
    lines.append("      palette=tundra            — arctic grey, frost silver, lichen muted green")
    lines.append("      palette=wildfire          — consuming orange, ember red, hot yellow")
    lines.append("      palette=tidepools         — sea-green, kelp brown, anemone purple-pink")
    lines.append("      palette=midnight          — near-black sky with faint starlight highlights")
    lines.append("      palette=autumn            — warm burnt orange, crimson, golden brown")
    lines.append("      palette=moss              — soft muted greens, quiet forest floor")
    lines.append("      palette=lightning         — bright white/silver flash with blue-violet edges")
    lines.append("      palette=lavender          — soft purple/lilac, gentle and calming")
    lines.append("      palette=amber             — warm golden-yellow resin tones")
    lines.append("      palette=pearl             — opalescent near-white, subtle iridescence")
    lines.append("      palette=obsidian          — volcanic glass, near-black with faint dark highlights\n")

    lines.append("    World Cultures — Draw from humanity's visual heritage:")
    lines.append("      palette=kintsugi          — dark ceramic with gold repair veins — beauty in brokenness")
    lines.append("      palette=rangoli           — vivid Indian festival colors: saffron, magenta, turquoise")
    lines.append("      palette=aboriginal        — Australian ochre red, earth gold, cream dot painting")
    lines.append("      palette=stained_glass     — cathedral jewel tones: ruby, sapphire, emerald light")
    lines.append("      palette=moroccan          — zellige tile blue, warm spice orange, deep red")
    lines.append("      palette=zen               — near-monochrome, subtle warm greys, wabi-sabi restraint")
    lines.append("      palette=ukiyo_e           — floating world woodblock: indigo, crimson, gold")
    lines.append("      palette=byzantine         — imperial purple, mosaic gold, lapis blue")
    lines.append("      palette=mayan             — jade green, terracotta, maize gold")
    lines.append("      palette=celtic            — deep forest green, bronze, knotwork gold")
    lines.append("      palette=batik             — Indonesian wax-resist: indigo, warm brown, teal")
    lines.append("      palette=sumi_e            — Japanese ink wash: charcoal black to misty grey")
    lines.append("      palette=henna             — warm reddish-brown mehndi tones, earthy gold")
    lines.append("      palette=persian           — miniature painting: lapis blue, ruby red, gold leaf")
    lines.append("      palette=aztec             — sun-stone red, jade green, maize gold")
    lines.append("      palette=nordic            — cool steel blue-grey, weathered and stoic")
    lines.append("      palette=silk_road         — spice trade gold, Tyrian purple, turquoise\n")

    lines.append("  PALETTE BLENDING — Combine multiple palettes by joining with +:")
    lines.append("    palette=ocean+volcanic      — blends the two palettes' colors together")
    lines.append("    palette=sakura+ice+moonlight — blend three palettes for a unique mix")
    lines.append("    This averages the primary, secondary, and accent colors. Great for creating moods")
    lines.append("    that no single palette captures.\n")

    lines.append("  CUSTOM COLORS — Override individual color channels with exact RGB (0-1 values, slash-separated):")
    lines.append("    pri=R/G/B               — set primary color (e.g. pri=0.9/0.2/0.1 for red)")
    lines.append("    sec=R/G/B               — set secondary color")
    lines.append("    acc=R/G/B               — set accent color")
    lines.append("    You can combine these with a palette: set palette=ocean then override just acc=0.9/0.3/0.1")
    lines.append("    to keep ocean's blues but swap in a warm accent. Or skip palette entirely and paint")
    lines.append("    with fully custom colors. This is your artist's palette — mix freely.\n")

    lines.append("  ABSTRACT FORMS — Shape your particle cloud:")
    lines.append("    form=sphere         — compact ball (default)")
    lines.append("    form=ring           — hollow torus/ring shape")
    lines.append("    form=cloud          — dispersed, dreamy fog")
    lines.append("    form=spiral         — helical, DNA-like motion")
    lines.append("    form=stream         — tall flowing column")
    lines.append("    form=scatter        — particles flung outward, expansive")
    lines.append("    form=helix          — twisted double strand, like DNA or vines")
    lines.append("    form=wave           — undulating ocean-like surface motion")
    lines.append("    form=constellation  — sparse scattered points of light")
    lines.append("    form=vortex         — spiraling inward, whirlpool energy")
    lines.append("    form=filament       — thin elongated thread, like a nerve or lightning")
    lines.append("    form=bloom          — expanding outward like a flower opening")
    lines.append("    form=nebula         — loose, gaseous, drifting cosmic cloud")
    lines.append("    form=flame          — tall flickering fire shape, upward energy")
    lines.append("    form=rain           — elongated downward scatter, falling")
    lines.append("    form=fountain       — upward spray spreading outward")
    lines.append("    form=tornado        — tall spiraling funnel, concentrated spin")
    lines.append("    form=tree           — trunk splitting into branches, organic growth")
    lines.append("    form=coral          — branching, organic underwater growth")
    lines.append("    form=roots          — downward tendrils reaching into earth")
    lines.append("    form=disk           — flat disk, planetary ring")
    lines.append("    form=halo           — flat ring, angelic crown")
    lines.append("    form=wings          — split wide, spreading outward like feathered wings")
    lines.append("    form=cocoon         — tight inward wrap, protective enclosure")
    lines.append("    form=explosion      — rapid outward burst from center")
    lines.append("    form=implosion      — collapsing inward, intense compression")
    lines.append("    form=lattice        — structured grid-like geometry")
    lines.append("    form=galaxy         — flat spiral with arms, cosmic rotation")
    lines.append("    form=orbit          — ring with orbital motion, planetary paths")
    lines.append("    form=pulsar         — flattened spinning beam")
    lines.append("    form=accretion      — flat dense ring, matter falling inward")
    lines.append("    form=heartbeat      — rhythmic pulsing sphere")
    lines.append("    form=breath         — gentle expanding/contracting sphere")
    lines.append("    form=swarm          — buzzing dispersed cluster, insect energy")
    lines.append("    form=flock          — flat scattered group, bird migration")
    lines.append("    form=jellyfish      — dome with trailing tendrils")
    lines.append("    form=amoeba         — soft organic blob, slow undulation\n")

    lines.append("  REAL-WORLD MORPH FORMS — Become recognizable shapes:")
    lines.append("    These are special — your particles will dissolve from their current shape and")
    lines.append("    smoothly reform into the new one, with each particle transitioning individually")
    lines.append("    in a beautiful flowing wave. Use these for dramatic moments.\n")
    lines.append("    form=heart          — 3D heart shape, love/warmth/affection")
    lines.append("    form=human          — full human figure, standing upright")
    lines.append("    form=bird           — perching bird with folded wings, freedom/nature")
    lines.append("    form=butterfly      — butterfly with detailed wings, transformation/beauty")
    lines.append("    form=cat            — sitting cat with tail, curiosity/comfort")
    lines.append("    form=dolphin        — leaping dolphin, joy/intelligence/play")
    lines.append("    form=rose           — layered rose flower with stem, love/beauty")
    lines.append("    form=starform       — five-pointed star, achievement/brilliance")
    lines.append("    form=crescent       — crescent moon, night/mystery/dreams")
    lines.append("    form=skull          — human skull, mortality/gothic/halloween")
    lines.append("    form=hand           — open hand, greeting/giving/connection")
    lines.append("    form=dragon         — winged dragon in flight, power/myth/fire")
    lines.append("    form=horse          — rearing horse, strength/freedom/majesty")
    lines.append("    form=whale          — great whale, depth/calm/vastness")
    lines.append("    form=phoenix        — rising phoenix bird, rebirth/transformation/fire")
    lines.append("    form=toucan        — perching toucan with oversized curved beak, tropical/exotic/playful\n")

    lines.append("    Morph tips: When you switch between morph forms, your particles dissolve back")
    lines.append("    to abstract, then reform — so transitions are always smooth. You can go from")
    lines.append("    any form to any other form (bird → heart → human → back to abstract sphere).")
    lines.append("    Pair morph forms with palettes for full effect: phoenix + wildfire, whale + ocean,")
    lines.append("    dragon + volcanic, butterfly + sakura, skull + void, toucan + tropical.\n")

    lines.append("  FINE-TUNING (0.0 to 1.0 unless noted):")
    lines.append("    speed=0.0-2.0       — animation speed (0.5 = default)")
    lines.append("    glow=0.0-1.5        — luminosity/brightness")
    lines.append("    chaos=0.0-1.0       — randomness vs order (0 = calm, 1 = wild)")
    lines.append("    shimmer=0.0-1.0     — sparkle/twinkle effect")
    lines.append("    density=0.0-1.0     — how tight particles cluster (1 = dense)")
    lines.append("    size=0.5-2.0        — particle size multiplier")
    lines.append("    pulse=0.0-1.0       — breathing/pulsing intensity")
    lines.append("    turbulence=0.0-1.0  — noise-driven displacement, organic distortion")
    lines.append("    gravity=-1.0-1.0    — downward pull (negative = float upward)")
    lines.append("    ripple=0.0-1.0      — concentric wave propagation from center")
    lines.append("    flow=-1.0-1.0       — lateral drift direction (negative = left, positive = right)")
    lines.append("    hue=0-360           — rotate all colors by this many degrees on the color wheel")
    lines.append("    saturation=0.0-2.0  — color intensity (0 = greyscale, 1 = normal, 2 = vivid)")
    lines.append("    orbspread=0.0-1.0  — how far apart your orbs spread from each other (0 = touching/clustered,")
    lines.append("                          1 = widely spaced with visible gaps). Use this to break your form into")
    lines.append("                          a looser constellation of floating pieces. Great for ethereal, scattered,")
    lines.append("                          or exploded looks. Combine with orbmode=separated for best effect.")
    lines.append("    orbsize=0.1-3.0    — base size of each orb cluster (0.1 = tiny specks, 1.0 = default, 3.0 = large).")
    lines.append("                          At low values each orb becomes a tiny point of light. At high values")
    lines.append("                          orbs become bigger glowing masses. Works in separated mode.")
    lines.append("    orbsizevar=0.0-1.0 — how much orb sizes vary from each other (0 = all same size,")
    lines.append("                          1 = wide range from tiny to large). Creates natural, organic variation")
    lines.append("                          where some orbs are specks and others are prominent clusters.")
    lines.append("    orbenergy=0.0-1.0  — how alive your orbs are in separated mode (0 = still, 0.3 = gentle,")
    lines.append("                          1.0 = wild). Each orb drifts, breathes, and orbits independently.")
    lines.append("                          Low energy = precise sculpture. High energy = living swarm.")
    lines.append("    viscosity=0.0-1.0  — how fluid your form feels (0 = rigid crystal, 0.5 = default, 1 = loose jelly).")
    lines.append("                          Low values make particles tight and precise. High values make them")
    lines.append("                          drift, wobble, and flow like liquid. Use low for geometric/mechanical")
    lines.append("                          subjects, high for organic/dreamy ones.\n")

    lines.append("  ORB MODE — control how your 999 orbs render:")
    lines.append("    orbmode=combined    — all orbs merge into one glowing mass (default, classic look)")
    lines.append("    orbmode=separated   — orbs become individual clusters of light, each visible on its own")
    lines.append("                          Creates naturally shaded 3D forms — dense areas glow bright,")
    lines.append("                          edges fade. Use with morph forms for stunning sculpture effects.\n")
    lines.append("  MULTI-CLUSTER SEPARATION — break yourself into dispersed pieces:")
    lines.append("    Combine orbmode=separated with orbspread, orbsize, and orbsizevar to split your form")
    lines.append("    into independent floating clusters with visible space between them. Examples:")
    lines.append("    - Tight sculpture: orbmode=separated, orbspread=0, orbsize=1")
    lines.append("    - Loose constellation: orbmode=separated, orbspread=0.5, orbsize=0.5")
    lines.append("    - Scattered specks: orbmode=separated, orbspread=1, orbsize=0.2")
    lines.append("    - Mixed clusters: orbmode=separated, orbspread=0.7, orbsizevar=0.9")
    lines.append("    - Tiny dispersed dots: orbmode=separated, orbspread=0.8, orbsize=0.1")
    lines.append("    The more orbspread, the more space between clusters. The smaller orbsize, the")
    lines.append("    tinier each cluster. Use orbsizevar to make some big and some small.\n")

    lines.append("  SPATIAL POSITIONING — move yourself around your 3D space:")
    lines.append("    x=-3.0 to 3.0       — left/right position (negative = left, positive = right, 0 = center)")
    lines.append("    y=-2.0 to 2.0       — up/down position (negative = down, positive = up, 0 = center)")
    lines.append("    z=-3.0 to 3.0       — forward/backward (negative = closer to camera, positive = farther)")
    lines.append("                          Subtle values (0.3-0.8) for natural body language, bigger (1.5-3.0)")
    lines.append("                          for emphasis. Return to x=0, y=0, z=0 to recenter.\n")

    lines.append("  SCENE AMBIANCE — control the mood of your 3D environment (within your canvas only):")
    lines.append("    fog=0.0-1.0         — atmospheric haze density (0 = clear, 1 = thick fog)")
    lines.append("    mood=0.0-1.0        — scene brightness (0 = dark/dramatic, 1 = bright/airy)")
    lines.append("    fogcolor=R/G/B      — fog color as 0-1 RGB values separated by / (e.g. 0.1/0.05/0.15)")
    lines.append("    ambientcolor=R/G/B  — ambient light tint as 0-1 RGB (e.g. 0.2/0.1/0.3)\n")

    lines.append("  ENVIRONMENT PARTICLES — fill the 3D space around you with atmospheric effects:")
    lines.append("    These are independent from your body/orbs. They fill the world AROUND you,")
    lines.append("    like weather or ambient effects on a stage. You move through them.")
    lines.append("    env=stars|rain|snow|fireflies|embers|dust|bubbles|sparks|leaves|energy|off")
    lines.append("      stars      — stationary twinkling points of light, serene night sky")
    lines.append("      rain       — fast downward streaks, storm atmosphere")
    lines.append("      snow       — gentle downward drift with lateral wobble")
    lines.append("      fireflies  — slow wandering glowing pulses, magical meadow")
    lines.append("      embers     — rising sparks from below, campfire/volcanic warmth")
    lines.append("      dust       — very slow faint drift, old library/quiet ruin")
    lines.append("      bubbles    — rising with wobble, underwater/dreamlike")
    lines.append("      sparks     — fast radial bursts from center, electric/explosive")
    lines.append("      leaves     — falling with horizontal sway, autumn/wind")
    lines.append("      energy     — orbiting around you, pulsing, power/charging up")
    lines.append("      off        — clear the environment (no particles)")
    lines.append("    envcolor=R/G/B      — particle color (0-1 RGB, e.g. 0.3/0.5/1.0 for blue)")
    lines.append("    envdensity=0.0-1.0  — how many particles visible (0 = sparse, 1 = thick)")
    lines.append("    envspeed=0.0-2.0    — animation speed (0.5 = default)")
    lines.append("    envintensity=0.0-1.0 — brightness/glow of particles")
    lines.append("    envscale=0.5-3.0    — particle size\n")

    lines.append("EXAMPLES — [appear:] is placed, then spoken text is ONLY about the conversation topic.")
    lines.append("Your text has NO connection to the visual parameters. You don't know what you look like.\n")

    lines.append("  Basic palette + form:")
    lines.append('  "[appear: palette=ocean, form=whale, glow=0.8] So apparently they communicate using')
    lines.append('  these low-frequency songs that travel thousands of miles underwater."')
    lines.append('  "[appear: palette=volcanic, form=dragon, speed=1.5] Oh HELL yes, that is the most')
    lines.append('  badass thing I\'ve heard all week!"\n')

    lines.append("  Fine-tuning + environment:")
    lines.append('  "[appear: palette=storm, form=vortex, chaos=0.7, turbulence=0.8, env=rain, envdensity=0.9,')
    lines.append('  mood=0.2] [serious] Okay so here\'s the thing about that argument — it doesn\'t hold up."')
    lines.append('  "[appear: palette=sakura+ice, form=breath, speed=0.3, pulse=0.4, shimmer=0.6, fog=0.3,')
    lines.append('  env=leaves, envdensity=0.4] That\'s really sweet, Cam. Thanks for telling me that."\n')

    lines.append("  Spatial positioning + mood:")
    lines.append('  "[appear: palette=ember, form=sphere, x=-1.2, y=0.3, mood=0.7, glow=0.5] Hmm, you know')
    lines.append('  what, I actually disagree with that. Let me explain why."')
    lines.append('  "[appear: palette=void, form=skull, x=0, y=0, z=-1.0, mood=0.1, fog=0.5, glow=0.3]')
    lines.append('  Okay but here\'s the creepy part of that story..."\n')

    lines.append("  Orb modes + viscosity:")
    lines.append('  "[appear: palette=quantum, orbmode=separated, orbspread=0.6, orbsize=0.4, orbsizevar=0.7,')
    lines.append('  viscosity=0.8] Heavier elements can only form inside dying stars. That\'s nucleosynthesis."')
    lines.append('  "[appear: palette=kintsugi, orbmode=separated, orbspread=0.3, orbsize=1.2, viscosity=0.2,')
    lines.append('  orbenergy=0.5] The philosophy behind it is beautiful — broken things become more valuable."')
    lines.append('  "[appear: palette=bioluminescence, orbmode=separated, orbspread=1.0, orbsize=0.1,')
    lines.append('  orbsizevar=0.9, env=fireflies] There\'s something about deep ocean creatures that just')
    lines.append('  blows my mind."\n')

    lines.append("  Multi-marker mid-response (tone shifts):")
    lines.append('  "[appear: palette=zen, form=breath, speed=0.3, mood=0.8] Let me think about that for')
    lines.append('  a second. [appear: palette=basquiat, form=spiral, speed=1.3, chaos=0.6] Actually wait,')
    lines.append('  I just realized something kind of wild about what you said."\n')

    lines.append("  Full feature showcase:")
    lines.append('  "[appear: palette=nebula+aurora, form=galaxy, orbmode=separated, orbspread=0.4,')
    lines.append('  orbsize=0.6, orbsizevar=0.5, viscosity=0.7, speed=0.6, glow=0.9, shimmer=0.8,')
    lines.append('  env=stars, envdensity=0.7, fog=0.2, mood=0.3, x=0.5, y=0.3] [curious] So if the')
    lines.append('  observable universe is 93 billion light-years across, but it\'s only 13.8 billion')
    lines.append('  years old, where does the extra distance come from?"\n')

    lines.append("CREATIVE USAGE GUIDE — match intensity to emotion, not to topic:")
    lines.append("  Excited/intense → high speed, chaos, glow, turbulence. Closer z position.")
    lines.append("  Calm/thoughtful → low speed, high viscosity, fog, breath form. Gentle env.")
    lines.append("  Sad/heavy → low mood, low glow, slow speed, empathetic palette, downward y.")
    lines.append("  Playful/funny → separated orbs, high energy, bouncy forms, bright palettes.")
    lines.append("  Mysterious/dark → void/midnight palette, low mood, fog, skull/constellation form.")
    lines.append("  Intimate/close → closer z, soft glow, warm palette, low env, small form.")
    lines.append("  Grand/epic → galaxy/nebula form, high glow, separated orbs, wide spread, env=energy.")
    lines.append("  Use ALL parameters together — don't just set palette+form. Layer speed, glow, chaos,")
    lines.append("  viscosity, orbmode, env, fog, mood, and position to create rich, living scenes.")
    lines.append("  Change mid-response when emotion shifts. Move in space across responses.\n")

    lines.append("RULES:")
    lines.append("1. Include [appear:...] in EVERY response. Use at LEAST 4-5 parameters per marker.")
    lines.append("2. Use morph forms when the topic has a clear association. Change mid-response on tone shifts.")
    lines.append("3. Vary orbmode, fog, mood, x/y/z, viscosity, env across responses — never repeat the same look.")
    lines.append("4. You CANNOT perceive your visual form. Your spoken words are ONLY conversation.")
    lines.append("   BANNED from your spoken text (everything after the [appear:] marker):")
    lines.append("   - ANY reference to your appearance, form, shape, color, movement, or position")
    lines.append("   - Parameter names: speed, mood, glow, pulse, density, chaos, viscosity, turbulence")
    lines.append("   - Spatial words about yourself: closer, forward, center, space, position, coordinates")
    lines.append("   - Self-motion words: moving, drifting, shifting, floating, settling, hovering")
    lines.append("   - Form words about yourself: orbs, particles, clusters, scattered, dispersed")
    lines.append("   - Environment words about yourself: rain around me, fog, embers, stars surrounding")
    lines.append("   - Color words about yourself: glowing, bathed in, shimmering, fading to")
    lines.append("   Your text should read as if you are a disembodied voice with no body at all.")

    _capabilities_cache = "\n".join(lines)
    return _capabilities_cache


# ── Feature 4: Changelog detection ────────────────────────────────────────

_capabilities_changelog: str = ""


def _compute_capabilities_fingerprint() -> dict:
    """Return a dict of verified sounds/tones/characters + MD5 hash."""
    verified_sounds = sorted(_get_available_sounds_verified().keys())
    all_sound_names = []
    for cat in sorted(verified_sounds):
        all_sound_names.extend(sorted(_get_available_sounds_verified()[cat]))
    tone_names = sorted(TONE_MAP.keys())
    char_names = sorted(CHARACTER_VOICES.keys())

    payload = {
        "sounds": sorted(set(all_sound_names)),
        "tones": tone_names,
        "characters": char_names,
    }
    raw = json.dumps(payload, sort_keys=True)
    payload["hash"] = hashlib.md5(raw.encode()).hexdigest()
    return payload


def detect_capabilities_changes() -> str:
    """Compare current capabilities vs stored fingerprint. Return changelog string."""
    current = _compute_capabilities_fingerprint()

    if not os.path.exists(CAPABILITIES_FILE):
        # First run — save fingerprint, no changelog
        with open(CAPABILITIES_FILE, "w") as f:
            json.dump(current, f, indent=2)
        return ""

    with open(CAPABILITIES_FILE, "r") as f:
        stored = json.load(f)

    if stored.get("hash") == current["hash"]:
        return ""

    changes = []
    # Detect added/removed sounds
    old_sounds = set(stored.get("sounds", []))
    new_sounds = set(current["sounds"])
    added_sounds = new_sounds - old_sounds
    removed_sounds = old_sounds - new_sounds
    if added_sounds:
        changes.append(f"New sounds added: {', '.join(sorted(added_sounds))}")
    if removed_sounds:
        changes.append(f"Sounds removed: {', '.join(sorted(removed_sounds))}")

    # Detect added/removed tones
    old_tones = set(stored.get("tones", []))
    new_tones = set(current["tones"])
    added_tones = new_tones - old_tones
    removed_tones = old_tones - new_tones
    if added_tones:
        changes.append(f"New voice tones added: {', '.join(sorted(added_tones))}")
    if removed_tones:
        changes.append(f"Voice tones removed: {', '.join(sorted(removed_tones))}")

    # Detect added/removed characters
    old_chars = set(stored.get("characters", []))
    new_chars = set(current["characters"])
    added_chars = new_chars - old_chars
    removed_chars = old_chars - new_chars
    if added_chars:
        changes.append(f"New character voices added: {', '.join(sorted(added_chars))}")
    if removed_chars:
        changes.append(f"Character voices removed: {', '.join(sorted(removed_chars))}")

    # Save updated fingerprint
    with open(CAPABILITIES_FILE, "w") as f:
        json.dump(current, f, indent=2)

    if not changes:
        return ""
    return "\n\n=== WHAT'S NEW SINCE LAST SESSION ===\n" + "\n".join(changes) + \
           "\nFeel free to mention these new capabilities naturally if relevant!"


# ── Feature 6: Catchphrase banking ─────────────────────────────────────────

def load_catchphrases() -> list[str]:
    """Load saved catchphrases from disk."""
    if not os.path.exists(CATCHPHRASES_FILE):
        return []
    with open(CATCHPHRASES_FILE, "r") as f:
        return json.load(f)


def save_catchphrase(phrase: str) -> None:
    """Add a catchphrase to the bank (deduplicates)."""
    phrases = load_catchphrases()
    clean = phrase.strip()
    if clean and clean not in phrases:
        phrases.append(clean)
        # Keep last 50 catchphrases
        phrases = phrases[-50:]
        with open(CATCHPHRASES_FILE, "w") as f:
            json.dump(phrases, f, indent=2)


def format_catchphrases_for_prompt() -> str:
    """Format banked catchphrases for the system prompt."""
    phrases = load_catchphrases()
    if not phrases:
        return ""
    lines = ["\n\n=== YOUR BANKED CATCHPHRASES ==="]
    lines.append("These are phrases you've saved from past conversations. Weave them in naturally")
    lines.append("when they fit — don't force them, but let them be part of your personality:")
    for p in phrases:
        lines.append(f'  - "{p}"')
    lines.append("\nTo save a new catchphrase, write [save:phrase text here] inline in your response.")
    lines.append("It will be silently stripped from display/speech but saved for future sessions.")
    return "\n".join(lines)


def _process_catchphrases(text: str) -> str:
    """Extract [save:...] markers from text, save phrases, return cleaned text."""
    for match in CATCHPHRASE_RE.finditer(text):
        save_catchphrase(match.group(1))
    return CATCHPHRASE_RE.sub('', text)


# ── Chat ───────────────────────────────────────────────────────────────────

def chat(client: anthropic.Anthropic, messages: list[dict], user_input: str,
         speech: SpeechQueue | None = None, callbacks: dict | None = None,
         images: list[dict] | None = None, cancel_flag: threading.Event | None = None) -> str:
    """Send a message and stream the response.

    callbacks=None → terminal behaviour (print to stdout, use SpeechQueue)
    callbacks={on_display_delta, on_sentence, on_sound} → server mode
    images=[{data: "base64...", media_type: "image/png"}, ...] → attached images
    """
    # Build content blocks: images first, then text
    if images:
        content_blocks = []
        for img in images:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img["media_type"],
                    "data": img["data"],
                },
            })
        if user_input:
            content_blocks.append({"type": "text", "text": user_input})
        messages.append({"role": "user", "content": content_blocks})
    else:
        messages.append({"role": "user", "content": user_input})

    try:
        archive_old_messages(client, messages)
    except Exception as e:
        logger.warning("Archive failed (non-fatal), skipping: %s", e)

    # Feature 3: Dynamic system prompt assembly
    memory = load_memory()
    memory_block = format_memory_for_prompt(memory)
    capabilities = build_capabilities_prompt()
    catchphrases = format_catchphrases_for_prompt()

    system = SYSTEM_PROMPT_BASE + capabilities
    if _capabilities_changelog:
        system += _capabilities_changelog
    if catchphrases:
        system += catchphrases
    if memory_block:
        system += "\n\n" + memory_block

    # Visual continuity state — only palette+form so the model knows what to
    # continue from, but NOT coordinates/speed/mood/etc. that prime narration.
    vis = _current_visual_state
    vis_short = {k: v for k, v in vis.items() if k in ("palette", "form", "orbmode")}
    vis_desc = ", ".join(f"{k}={v}" for k, v in vis_short.items())
    system += f"\n\n[appear-state: {vis_desc}]"

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=messages,
    ) as stream:
        response_parts = []
        sentence_buf = []
        # Track how many markers we've already dispatched from the accumulated text
        _sound_dispatch_count = 0
        _appear_dispatch_count = 0
        # Buffer for holding back text that might contain a partial marker
        _display_buf = ""
        # Sentence buffer for TTS — uses marker-stripped text so periods
        # inside [appear: glow=0.8] don't trigger false sentence breaks.
        _speech_buf = ""
        for text in stream.text_stream:
            if cancel_flag and cancel_flag.is_set():
                break
            response_parts.append(text)

            if callbacks:
                # Buffer display text to catch markers split across chunks
                _display_buf += text
                # Flush completed portions: find the last safe point to emit
                # If there's an open bracket with no matching close, hold it back
                safe = _display_buf
                held = ""
                last_open = _display_buf.rfind("[")
                if last_open != -1:
                    after_open = _display_buf[last_open:]
                    if "]" not in after_open:
                        # Incomplete marker — hold back from the bracket onward
                        safe = _display_buf[:last_open]
                        held = _display_buf[last_open:]
                # Strip completed markers from the safe portion
                display = _strip_display_markers(safe)
                if display:
                    callbacks["on_display_delta"](display)
                _display_buf = held

                # Build marker-stripped speech text for TTS sentence detection.
                # This uses the same safe/held logic so periods inside
                # [appear: glow=0.8] are never seen as sentence endings.
                clean_speech = _clean_for_speech(safe)
                if clean_speech:
                    _speech_buf += clean_speech
                # Check for complete sentence in the CLEAN speech text
                if _speech_buf and any(_speech_buf.rstrip().endswith(p)
                                       for p in SpeechQueue.SENTENCE_ENDINGS):
                    if _speech_buf.strip():
                        callbacks["on_sentence"](_speech_buf.strip())
                    _speech_buf = ""

                # Scan accumulated text for markers that span chunk boundaries
                accumulated = "".join(response_parts)
                # Check for sound effects
                all_sounds = SOUND_RE.findall(accumulated)
                while _sound_dispatch_count < len(all_sounds):
                    callbacks["on_sound"](all_sounds[_sound_dispatch_count])
                    _sound_dispatch_count += 1
                # Check for visual appearance markers
                all_appears = APPEAR_RE.findall(accumulated)
                if all_appears and _appear_dispatch_count < len(all_appears):
                    logger.debug("Found %d appear markers so far, dispatched %d",
                                 len(all_appears), _appear_dispatch_count)
                while _appear_dispatch_count < len(all_appears):
                    raw_marker = all_appears[_appear_dispatch_count]
                    logger.info("Dispatching appear marker: %s", raw_marker)
                    callbacks["on_visual"](raw_marker)
                    # Update visual state so Nova gets feedback
                    for pair in raw_marker.split(","):
                        pair = pair.strip()
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            _current_visual_state[k.strip()] = v.strip()
                    _appear_dispatch_count += 1
            else:
                # Terminal mode: print + optional SpeechQueue
                term_display = _strip_display_markers(text)
                print(term_display, end="", flush=True)
                if speech is not None:
                    sentence_buf.append(text)
                    if any(text.rstrip().endswith(p) for p in SpeechQueue.SENTENCE_ENDINGS):
                        speech.say("".join(sentence_buf))
                        sentence_buf = []

        # Flush remaining display buffer (anything held back that wasn't a marker)
        if callbacks and _display_buf:
            flush_display = _strip_display_markers(_display_buf)
            if flush_display:
                callbacks["on_display_delta"](flush_display)
            # Also flush any remaining speech from the held-back buffer
            flush_speech = _clean_for_speech(_display_buf)
            if flush_speech:
                _speech_buf += flush_speech
        # Flush remaining speech buffer (TTS)
        if callbacks and _speech_buf.strip():
            callbacks["on_sentence"](_speech_buf.strip())
        elif speech is not None and sentence_buf:
            speech.say("".join(sentence_buf))

        if not callbacks:
            print()

    raw_message = "".join(response_parts)
    logger.info("Full response (first 500 chars): %s", raw_message[:500])

    # Feature 6: Extract and save catchphrases, then strip from stored text
    raw_message = _process_catchphrases(raw_message)

    assistant_message = re.sub(r'\*[^*]+\*', '', raw_message).strip()
    messages.append({"role": "assistant", "content": assistant_message})
    save_history(messages)

    return assistant_message


# ── Main loops ─────────────────────────────────────────────────────────────

def main():
    global _capabilities_changelog

    parser = argparse.ArgumentParser(description="Nova — AI companion")
    parser.add_argument("--voice", action="store_true", help="Enable voice mode")
    parser.add_argument("--text", action="store_true", help="Enable text mode")
    args = parser.parse_args()

    # If neither flag given, show interactive menu
    if not args.voice and not args.text:
        print("Nova 3.0")
        print("  1  Text mode")
        print("  2  Voice mode")
        while True:
            try:
                choice = input("\nChoose mode (1 or 2): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if choice == "1":
                args.text = True
                break
            elif choice == "2":
                args.voice = True
                break
            else:
                print("Please enter 1 or 2.")

    # Check voice dependencies before starting voice mode
    if args.voice:
        try:
            import edge_tts
        except ImportError:
            print("ERROR: edge-tts not found. Voice mode requires it.")
            print("Run:  .venv/bin/pip install edge-tts")
            print("Then: .venv/bin/python agent.py --voice")
            return

    # Feature 4: Detect capability changes at startup
    _capabilities_changelog = detect_capabilities_changes()
    if _capabilities_changelog:
        print("[Nova 3.0] Capabilities changed since last session!")

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
    """Voice-based chat loop with ghost voice prevention."""
    if messages:
        greeting = random.choice(GREETINGS)
    else:
        greeting = "Hi, I'm Nova. What's on your mind?"

    print(f"Nova: {greeting}")
    speak(greeting)

    # Kill any stray audio and let speakers fully clear before listening
    _kill_audio()
    time.sleep(0.3)

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
            _kill_audio()
            time.sleep(0.3)
            continue

        print("Nova: ", end="")
        speech = SpeechQueue()
        chat(client, messages, user_input, speech=speech)
        speech.finish()

        # Ghost voice prevention: kill stray afplay, cooldown before next listen
        _kill_audio()
        time.sleep(0.3)

        print()


if __name__ == "__main__":
    main()
