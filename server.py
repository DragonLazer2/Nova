"""Nova Web Dashboard — FastAPI + WebSocket server."""

import asyncio
import base64
import io
import json
import logging
import os
import random
import threading
import traceback

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import agent

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("nova.server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

# Static file mounts
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/sounds", StaticFiles(directory=os.path.join(BASE_DIR, "sounds")), name="sounds")


@app.get("/")
async def root():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


async def _synthesize_greeting(text: str) -> str | None:
    """Synthesize greeting text to base64-encoded MP3."""
    tone = agent._detect_tone(text)
    audio_bytes = await agent.synthesize_to_bytes(text, tone)
    if audio_bytes:
        return base64.b64encode(audio_bytes).decode("ascii")
    return None


async def _synthesize_sentence(text: str) -> tuple[str | None, float, str]:
    """Synthesize a sentence to base64 MP3, return (b64, playback_vol, tone_name)."""
    tone = agent._detect_tone(text)

    # Determine tone name for the client
    tone_name = "neutral"
    m = agent.CHARACTER_RE.match(text)
    if m:
        tone_name = "voice:" + m.group(1).lower()
    else:
        _, marker = agent._strip_voice_markers(text)
        if marker and marker in agent.TONE_MAP:
            tone_name = marker
        elif agent._has_caps_emphasis(text):
            tone_name = "caps_emphasis"
        else:
            lower = text.lower()
            for t, keywords in agent.TONE_KEYWORDS.items():
                if any(kw in lower for kw in keywords):
                    tone_name = t
                    break

    audio_bytes = await agent.synthesize_to_bytes(text, tone)
    b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None
    return b64, tone.get("playback_vol", 1.0), tone_name


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # Initialise per-connection state
    client = anthropic.Anthropic()
    messages = agent.load_history()

    # Detect capabilities at connect time
    agent.detect_capabilities_changes()

    # Send existing chat history to client so it persists across refreshes
    if messages:
        # Send last 30 messages to avoid overwhelming the client
        recent = messages[-30:]
        history_msgs = []
        for m in recent:
            role = m["role"]  # "user" or "assistant"
            # Content can be a string or list of blocks
            if isinstance(m["content"], str):
                text = m["content"]
            else:
                # Extract text from content blocks
                text = " ".join(
                    b.get("text", "") for b in m["content"] if isinstance(b, dict) and b.get("type") == "text"
                )
            # Strip appear/sound markers from assistant messages for clean display
            if role == "assistant":
                text = agent.APPEAR_RE.sub("", text)
                text = agent.SOUND_RE.sub("", text)
                text = agent.CATCHPHRASE_RE.sub("", text)
                text = agent.CHARACTER_RE.sub("", text)
                text = agent.VOICE_MARKER_RE.sub("", text)
                import re as _re
                text = _re.sub(r'\*[^*]+\*', '', text)
                text = text.strip()
            if text:
                history_msgs.append({"role": "nova" if role == "assistant" else "user", "text": text})
        if history_msgs:
            await ws.send_json({"type": "chat_history", "messages": history_msgs})

    # Send greeting
    if messages:
        greeting_text = random.choice(agent.GREETINGS)
    else:
        greeting_text = "Hi, I'm Nova. What's on your mind?"

    greeting_audio = await _synthesize_greeting(greeting_text)
    await ws.send_json({
        "type": "greeting",
        "text": greeting_text,
        "audio": greeting_audio,
    })

    # ── Transcription helper ──────────────────────────────────────────────
    async def _transcribe(audio_b64: str) -> str:
        import speech_recognition as sr

        def _do_recognize():
            audio_bytes = base64.b64decode(audio_b64)
            recognizer = sr.Recognizer()
            audio_file = sr.AudioFile(io.BytesIO(audio_bytes))
            with audio_file as source:
                audio = recognizer.record(source)
            try:
                return recognizer.recognize_google(audio)
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                logger.error("Speech recognition API error: %s", e)
                return ""

        return await asyncio.to_thread(_do_recognize)

    # ── Incoming message queue + background receiver ──────────────────────
    incoming: asyncio.Queue = asyncio.Queue()

    async def _ws_receiver():
        try:
            while True:
                raw = await ws.receive_text()
                await incoming.put(json.loads(raw))
        except WebSocketDisconnect:
            await incoming.put(None)

    receiver_task = asyncio.ensure_future(_ws_receiver())

    # ── Event handler (shared between normal + interrupt-aware loops) ────
    async def handle_event(event):
        if event["type"] == "text_delta":
            await ws.send_json(event)
        elif event["type"] == "visual_update":
            await ws.send_json(event)
        elif event["type"] == "sound_effect":
            await ws.send_json(event)
        elif event["type"] == "_sentence":
            b64, vol, tone_name = await _synthesize_sentence(event["text"])
            await ws.send_json({"type": "tone_update", "tone": tone_name})
            if b64:
                await ws.send_json({
                    "type": "sentence_audio",
                    "audio": b64,
                    "playback_vol": vol,
                    "seq": event["seq"],
                })

    try:
        while True:
            data = await incoming.get()
            if data is None:
                break  # Disconnected

            if data["type"] == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if data["type"] == "clear_history":
                messages.clear()
                agent.save_history(messages)
                await ws.send_json({"type": "history_cleared"})
                continue

            if data["type"] == "audio_input":
                try:
                    text = await _transcribe(data["audio"])
                    await ws.send_json({"type": "transcript", "text": text.strip()})
                except Exception as e:
                    logger.error("Transcription error: %s", e)
                    await ws.send_json({"type": "transcript", "text": ""})
                continue

            if data["type"] == "user_message":
                user_text = data["text"].strip()
                user_images = data.get("images", [])
                if not user_text and not user_images:
                    continue

                try:
                    await ws.send_json({"type": "response_start"})

                    event_queue: asyncio.Queue = asyncio.Queue()
                    loop = asyncio.get_event_loop()
                    cancel_flag = threading.Event()

                    def on_display_delta(text):
                        loop.call_soon_threadsafe(event_queue.put_nowait,
                                                  {"type": "text_delta", "text": text})

                    sentence_seq = [0]

                    def on_sentence(sentence_text):
                        sentence_seq[0] += 1
                        loop.call_soon_threadsafe(event_queue.put_nowait,
                                                  {"type": "_sentence", "text": sentence_text,
                                                   "seq": sentence_seq[0]})

                    def on_sound(name):
                        loop.call_soon_threadsafe(event_queue.put_nowait,
                                                  {"type": "sound_effect", "name": name})

                    def on_visual(raw):
                        logger.info("on_visual called with: %s", raw)
                        params = {}
                        for pair in raw.split(","):
                            pair = pair.strip()
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                k, v = k.strip(), v.strip()
                                try:
                                    v = float(v)
                                except ValueError:
                                    pass
                                params[k] = v
                            else:
                                params["preset"] = pair.strip()
                        logger.info("visual_update params: %s", params)
                        loop.call_soon_threadsafe(event_queue.put_nowait,
                                                  {"type": "visual_update", "params": params})

                    callbacks = {
                        "on_display_delta": on_display_delta,
                        "on_sentence": on_sentence,
                        "on_sound": on_sound,
                        "on_visual": on_visual,
                    }

                    chat_task = asyncio.ensure_future(
                        asyncio.to_thread(agent.chat, client, messages, user_text,
                                          None, callbacks, user_images, cancel_flag)
                    )

                    # Process events with interrupt support
                    interrupted_data = None
                    while True:
                        # Drain chat events
                        while not event_queue.empty():
                            await handle_event(event_queue.get_nowait())

                        # Check for incoming messages (interrupt)
                        try:
                            new_data = incoming.get_nowait()
                            if new_data is None:
                                cancel_flag.set()
                                break
                            if new_data["type"] == "user_message":
                                logger.info("Interrupt: new user_message during response")
                                cancel_flag.set()
                                interrupted_data = new_data
                                break
                            elif new_data["type"] == "interrupt":
                                logger.info("Interrupt: mic button pressed during response")
                                cancel_flag.set()
                                break
                            elif new_data["type"] == "ping":
                                await ws.send_json({"type": "pong"})
                            elif new_data["type"] == "clear_history":
                                messages.clear()
                                agent.save_history(messages)
                                await ws.send_json({"type": "history_cleared"})
                            elif new_data["type"] == "audio_input":
                                # Transcribe without blocking event processing
                                async def _bg_transcribe(audio_data):
                                    try:
                                        text = await _transcribe(audio_data)
                                        await ws.send_json({"type": "transcript", "text": text.strip()})
                                    except Exception:
                                        await ws.send_json({"type": "transcript", "text": ""})
                                asyncio.ensure_future(_bg_transcribe(new_data["audio"]))
                        except asyncio.QueueEmpty:
                            pass

                        # Check if chat is done
                        if chat_task.done():
                            while not event_queue.empty():
                                await handle_event(event_queue.get_nowait())
                            break

                        await asyncio.sleep(0.02)

                    # Wait for chat thread to finish
                    try:
                        await asyncio.wait_for(asyncio.shield(chat_task), timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        logger.warning("Chat thread slow to finish after interrupt")

                    await ws.send_json({"type": "response_end"})

                    # Re-queue interrupted message for next loop iteration
                    if interrupted_data:
                        await incoming.put(interrupted_data)

                except Exception as e:
                    logger.error("Error handling message: %s\n%s", e, traceback.format_exc())
                    try:
                        await ws.send_json({"type": "response_end"})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s\n%s", e, traceback.format_exc())
    finally:
        receiver_task.cancel()
