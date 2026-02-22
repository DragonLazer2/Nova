"""Generate comedic/sitcom sound effects as WAV files."""
import math
import struct
import wave
import os

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
SAMPLE_RATE = 44100


def _write_wav(filename, samples):
    path = os.path.join(SOUNDS_DIR, filename)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        for s in samples:
            f.writeframes(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))))


def _tone(freq, duration, volume=0.5):
    n = int(SAMPLE_RATE * duration)
    return [volume * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) for i in range(n)]


def _silence(duration):
    return [0.0] * int(SAMPLE_RATE * duration)


def _fade(samples, fade_ms=30):
    n = int(SAMPLE_RATE * fade_ms / 1000)
    for i in range(min(n, len(samples))):
        samples[i] *= i / n
    for i in range(min(n, len(samples))):
        samples[-(i + 1)] *= i / n
    return samples


def rimshot():
    """Ba-dum-tss!"""
    samples = _tone(200, 0.08, 0.7) + _silence(0.05)
    samples += _tone(250, 0.08, 0.7) + _silence(0.05)
    # "tss" - noise burst
    import random
    tss = [random.uniform(-0.5, 0.5) * (1 - i / (SAMPLE_RATE * 0.15))
           for i in range(int(SAMPLE_RATE * 0.15))]
    samples += tss
    _write_wav("rimshot.wav", _fade(samples))


def sad_trombone():
    """Wah wah wah wahhh."""
    samples = []
    for freq, dur in [(350, 0.35), (310, 0.35), (290, 0.35), (260, 0.6)]:
        samples += _fade(_tone(freq, dur, 0.6), 20)
        samples += _silence(0.05)
    _write_wav("sad_trombone.wav", samples)


def tada():
    """Triumphant fanfare."""
    samples = []
    for freq, dur in [(523, 0.15), (659, 0.15), (784, 0.15), (1047, 0.4)]:
        samples += _fade(_tone(freq, dur, 0.6), 15)
    _write_wav("tada.wav", samples)


def boing():
    """Bouncy spring sound."""
    n = int(SAMPLE_RATE * 0.4)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 300 + 700 * math.sin(t * 15)
        vol = 0.5 * (1 - t / 0.4)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("boing.wav", _fade(samples))


def dramatic():
    """DUN DUN DUNNN."""
    samples = []
    for freq, dur in [(130, 0.25), (130, 0.25), (98, 0.6)]:
        samples += _fade(_tone(freq, dur, 0.8), 20)
        samples += _silence(0.1)
    _write_wav("dramatic.wav", samples)


def crickets():
    """Awkward silence with crickets."""
    import random
    duration = 1.5
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        chirp = 0.0
        for offset in [0.0, 0.4, 0.8, 1.2]:
            dt = t - offset
            if 0 < dt < 0.1:
                chirp += 0.3 * math.sin(2 * math.pi * 4500 * dt) * math.sin(2 * math.pi * 40 * dt)
        samples.append(chirp)
    _write_wav("crickets.wav", samples)


def slide_whistle_up():
    """Rising slide whistle."""
    n = int(SAMPLE_RATE * 0.5)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 500 + 1500 * (t / 0.5)
        vol = 0.4 * (1 - 0.3 * t / 0.5)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("slide_up.wav", _fade(samples))


def slide_whistle_down():
    """Falling slide whistle."""
    n = int(SAMPLE_RATE * 0.5)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 2000 - 1500 * (t / 0.5)
        vol = 0.4 * (1 - 0.3 * t / 0.5)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("slide_down.wav", _fade(samples))


def record_scratch():
    """Record scratch / rewind."""
    import random
    n = int(SAMPLE_RATE * 0.3)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        noise = random.uniform(-1, 1)
        sweep = math.sin(2 * math.pi * (200 + 3000 * (1 - t / 0.3)) * t)
        vol = 0.5 * (1 - t / 0.3)
        samples.append(vol * (0.3 * noise + 0.7 * sweep))
    _write_wav("record_scratch.wav", _fade(samples))


def ding():
    """Simple bright ding."""
    n = int(SAMPLE_RATE * 0.5)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        vol = 0.6 * math.exp(-t * 5)
        samples.append(vol * (math.sin(2 * math.pi * 1200 * t) +
                              0.3 * math.sin(2 * math.pi * 2400 * t)))
    _write_wav("ding.wav", samples)


def whoosh():
    """Transition whoosh."""
    import random
    n = int(SAMPLE_RATE * 0.4)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.sin(math.pi * t / 0.4)
        samples.append(0.4 * env * random.uniform(-1, 1))
    _write_wav("whoosh.wav", samples)


if __name__ == "__main__":
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    rimshot()
    sad_trombone()
    tada()
    boing()
    dramatic()
    crickets()
    slide_whistle_up()
    slide_whistle_down()
    record_scratch()
    ding()
    whoosh()
    print(f"Generated {len(os.listdir(SOUNDS_DIR))} sounds in {SOUNDS_DIR}")
