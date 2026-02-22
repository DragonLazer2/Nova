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


def laugh_giggle():
    """Quick light giggle — rapid high-pitched bursts."""
    import random
    samples = []
    for burst in range(5):
        n = int(SAMPLE_RATE * 0.06)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 600 + 200 * math.sin(t * 80) + random.uniform(-20, 20)
            vol = 0.5 * (1 - t / 0.06)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.04)
    _write_wav("laugh_giggle.wav", _fade(samples))


def laugh_chuckle():
    """Short low chuckle — 'heh heh heh'."""
    import random
    samples = []
    for burst in range(3):
        n = int(SAMPLE_RATE * 0.1)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 180 + 60 * math.sin(t * 40) + random.uniform(-10, 10)
            vol = 0.6 * (1 - t / 0.1)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.08)
    _write_wav("laugh_chuckle.wav", _fade(samples))


def laugh_hearty():
    """Big belly laugh — 'HA HA HA HA'."""
    import random
    samples = []
    for i_burst in range(6):
        dur = 0.12 - i_burst * 0.005
        n = int(SAMPLE_RATE * max(dur, 0.06))
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 160 + 80 * math.sin(t * 50) + random.uniform(-15, 15)
            vol = 0.7 * (1 - t / dur) * (1 - i_burst * 0.08)
            noise = random.uniform(-0.15, 0.15) * vol
            samples.append(vol * math.sin(2 * math.pi * freq * t) + noise)
        samples += _silence(0.06)
    _write_wav("laugh_hearty.wav", _fade(samples))


def laugh_nervous():
    """Awkward, uncertain laugh — short tight bursts."""
    import random
    samples = []
    for burst in range(4):
        n = int(SAMPLE_RATE * 0.05)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 350 + 100 * math.sin(t * 60) + random.uniform(-30, 30)
            vol = 0.35 * (1 - t / 0.05)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.1 + random.uniform(0, 0.05))
    _write_wav("laugh_nervous.wav", _fade(samples))


def bird_tweet():
    """Simple short tweet — quick upward sweep."""
    n = int(SAMPLE_RATE * 0.15)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 2000 + 3000 * (t / 0.15)
        vol = 0.5 * math.sin(math.pi * t / 0.15)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("bird_tweet.wav", _fade(samples, 10))


def bird_chirp():
    """Quick repeated chirps."""
    samples = []
    for _ in range(4):
        n = int(SAMPLE_RATE * 0.06)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 3500 + 1500 * math.sin(t * 120)
            vol = 0.45 * (1 - t / 0.06)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.08)
    _write_wav("bird_chirp.wav", _fade(samples, 10))


def bird_songbird():
    """Melodic songbird sequence."""
    samples = []
    notes = [(3000, 0.12), (3500, 0.08), (4000, 0.1), (3200, 0.15),
             (3800, 0.08), (4200, 0.06), (3600, 0.12)]
    for freq, dur in notes:
        n = int(SAMPLE_RATE * dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            f = freq + 200 * math.sin(t * 80)
            vol = 0.45 * math.sin(math.pi * t / dur)
            samples.append(vol * math.sin(2 * math.pi * f * t))
        samples += _silence(0.03)
    _write_wav("bird_songbird.wav", _fade(samples, 10))


def bird_crow():
    """Crow caw — harsh low call."""
    import random
    samples = []
    for _ in range(2):
        n = int(SAMPLE_RATE * 0.25)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 600 + 200 * math.sin(t * 15)
            vol = 0.55 * math.sin(math.pi * t / 0.25)
            noise = random.uniform(-0.2, 0.2) * vol
            samples.append(vol * math.sin(2 * math.pi * freq * t) + noise)
        samples += _silence(0.15)
    _write_wav("bird_crow.wav", _fade(samples))


def bird_owl():
    """Owl hoot — 'hoo hoo'."""
    samples = []
    for dur in [0.3, 0.4]:
        n = int(SAMPLE_RATE * dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 350 + 30 * math.sin(t * 8)
            vol = 0.5 * math.sin(math.pi * t / dur)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.2)
    _write_wav("bird_owl.wav", _fade(samples))


def bird_seagull():
    """Seagull call — rising then falling wail."""
    samples = []
    n = int(SAMPLE_RATE * 0.6)
    for i in range(n):
        t = i / SAMPLE_RATE
        # Rise then fall
        if t < 0.3:
            freq = 800 + 1500 * (t / 0.3)
        else:
            freq = 2300 - 1200 * ((t - 0.3) / 0.3)
        vol = 0.5 * math.sin(math.pi * t / 0.6)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("bird_seagull.wav", _fade(samples))


def bird_woodpecker():
    """Rapid woodpecker tapping."""
    import random
    samples = []
    for _ in range(8):
        n = int(SAMPLE_RATE * 0.015)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.6 * (1 - t / 0.015)
            samples.append(vol * random.uniform(-1, 1))
        samples += _silence(0.05)
    _write_wav("bird_woodpecker.wav", _fade(samples, 5))


def bird_dove():
    """Soft dove coo — low gentle cooing with vibrato."""
    samples = []
    for dur in [0.3, 0.25, 0.35]:
        n = int(SAMPLE_RATE * dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = 450 + 40 * math.sin(t * 25)
            vol = 0.4 * math.sin(math.pi * t / dur)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.12)
    _write_wav("bird_dove.wav", _fade(samples))


def another_one():
    """Deep punchy DJ drop — 'ANOTHER ONE' energy. Two low booming hits."""
    import random
    samples = []
    # First hit — "an-OTHER"
    for freq, dur in [(90, 0.18), (70, 0.25)]:
        n = int(SAMPLE_RATE * dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.8 * math.exp(-t * 4)
            # thick low tone + harmonics for voice-like quality
            s = vol * (math.sin(2 * math.pi * freq * t)
                       + 0.4 * math.sin(2 * math.pi * freq * 2 * t)
                       + 0.2 * math.sin(2 * math.pi * freq * 3 * t)
                       + 0.1 * random.uniform(-1, 1))
            samples.append(s)
        samples += _silence(0.06)
    # Little reverb tail
    tail_n = int(SAMPLE_RATE * 0.15)
    for i in range(tail_n):
        t = i / SAMPLE_RATE
        vol = 0.2 * math.exp(-t * 12)
        samples.append(vol * math.sin(2 * math.pi * 70 * t))
    _write_wav("another_one.wav", _fade(samples, 15))


def vocal_riff():
    """Fast melismatic vocal riff — rapid ascending/descending pitch run."""
    samples = []
    # Quick run up then down, like a vocal melisma
    notes_up = [400, 500, 600, 750, 900, 1100, 1300]
    notes_down = [1200, 1000, 800, 650, 500, 420]
    all_notes = notes_up + notes_down
    note_dur = 0.045  # very fast notes
    for idx, freq in enumerate(all_notes):
        n = int(SAMPLE_RATE * note_dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            # Add vibrato for vocal quality
            vibrato = 15 * math.sin(2 * math.pi * 35 * t)
            f = freq + vibrato
            vol = 0.5 * math.sin(math.pi * t / note_dur)
            # Harmonics to sound voice-like
            s = vol * (math.sin(2 * math.pi * f * t)
                       + 0.35 * math.sin(2 * math.pi * f * 2 * t)
                       + 0.15 * math.sin(2 * math.pi * f * 3 * t))
            samples.append(s)
    # Sustain the last note with vibrato
    n = int(SAMPLE_RATE * 0.2)
    for i in range(n):
        t = i / SAMPLE_RATE
        vibrato = 25 * math.sin(2 * math.pi * 30 * t)
        f = 420 + vibrato
        vol = 0.5 * math.exp(-t * 3)
        s = vol * (math.sin(2 * math.pi * f * t)
                   + 0.35 * math.sin(2 * math.pi * f * 2 * t))
        samples.append(s)
    _write_wav("vocal_riff.wav", _fade(samples, 10))


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
    laugh_giggle()
    laugh_chuckle()
    laugh_hearty()
    laugh_nervous()
    bird_tweet()
    bird_chirp()
    bird_songbird()
    bird_crow()
    bird_owl()
    bird_seagull()
    bird_woodpecker()
    bird_dove()
    another_one()
    vocal_riff()
    print(f"Generated {len(os.listdir(SOUNDS_DIR))} sounds in {SOUNDS_DIR}")
