"""Generate sound effects as WAV files — Nova 3.0 sound library."""
import math
import random
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


# ── Original sounds (Nova 2.0) ─────────────────────────────────────────────

def rimshot():
    """Ba-dum-tss!"""
    samples = _tone(200, 0.08, 0.7) + _silence(0.05)
    samples += _tone(250, 0.08, 0.7) + _silence(0.05)
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
    n = int(SAMPLE_RATE * 0.4)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.sin(math.pi * t / 0.4)
        samples.append(0.4 * env * random.uniform(-1, 1))
    _write_wav("whoosh.wav", samples)


def laugh_giggle():
    """Quick light giggle — rapid high-pitched bursts."""
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
        if t < 0.3:
            freq = 800 + 1500 * (t / 0.3)
        else:
            freq = 2300 - 1200 * ((t - 0.3) / 0.3)
        vol = 0.5 * math.sin(math.pi * t / 0.6)
        samples.append(vol * math.sin(2 * math.pi * freq * t))
    _write_wav("bird_seagull.wav", _fade(samples))


def bird_woodpecker():
    """Rapid woodpecker tapping."""
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
    """Deep punchy DJ drop — 'ANOTHER ONE' energy."""
    samples = []
    for freq, dur in [(90, 0.18), (70, 0.25)]:
        n = int(SAMPLE_RATE * dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.8 * math.exp(-t * 4)
            s = vol * (math.sin(2 * math.pi * freq * t)
                       + 0.4 * math.sin(2 * math.pi * freq * 2 * t)
                       + 0.2 * math.sin(2 * math.pi * freq * 3 * t)
                       + 0.1 * random.uniform(-1, 1))
            samples.append(s)
        samples += _silence(0.06)
    tail_n = int(SAMPLE_RATE * 0.15)
    for i in range(tail_n):
        t = i / SAMPLE_RATE
        vol = 0.2 * math.exp(-t * 12)
        samples.append(vol * math.sin(2 * math.pi * 70 * t))
    _write_wav("another_one.wav", _fade(samples, 15))


def vocal_riff():
    """Fast melismatic vocal riff — rapid ascending/descending pitch run."""
    samples = []
    notes_up = [400, 500, 600, 750, 900, 1100, 1300]
    notes_down = [1200, 1000, 800, 650, 500, 420]
    all_notes = notes_up + notes_down
    note_dur = 0.045
    for idx, freq in enumerate(all_notes):
        n = int(SAMPLE_RATE * note_dur)
        for i in range(n):
            t = i / SAMPLE_RATE
            vibrato = 15 * math.sin(2 * math.pi * 35 * t)
            f = freq + vibrato
            vol = 0.5 * math.sin(math.pi * t / note_dur)
            s = vol * (math.sin(2 * math.pi * f * t)
                       + 0.35 * math.sin(2 * math.pi * f * 2 * t)
                       + 0.15 * math.sin(2 * math.pi * f * 3 * t))
            samples.append(s)
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


# ── NEW: Emotional reactions (Nova 3.0) ────────────────────────────────────

def gasp():
    """Sharp intake of breath — rising noise burst."""
    n = int(SAMPLE_RATE * 0.3)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Quick rise then plateau
        env = min(1.0, t / 0.05) * math.exp(-t * 3)
        noise = random.uniform(-1, 1)
        # Breathy quality — filtered noise with slight pitch
        breath = 0.3 * math.sin(2 * math.pi * 800 * t) * env
        samples.append(0.5 * (env * noise * 0.4 + breath))
    _write_wav("gasp.wav", _fade(samples, 10))


def sigh():
    """Soft exhale — descending breathy tone."""
    n = int(SAMPLE_RATE * 0.8)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 400 - 150 * (t / 0.8)
        env = math.sin(math.pi * t / 0.8) * 0.4
        noise = random.uniform(-0.15, 0.15)
        samples.append(env * (math.sin(2 * math.pi * freq * t) * 0.3 + noise))
    _write_wav("sigh.wav", _fade(samples, 40))


def hmm():
    """Thinking hum — steady low tone with slight vibrato."""
    n = int(SAMPLE_RATE * 0.6)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 220 + 15 * math.sin(2 * math.pi * 4 * t)
        env = math.sin(math.pi * t / 0.6) * 0.5
        # Harmonics for voice quality
        s = env * (math.sin(2 * math.pi * freq * t)
                   + 0.4 * math.sin(2 * math.pi * freq * 2 * t)
                   + 0.15 * math.sin(2 * math.pi * freq * 3 * t))
        samples.append(s)
    _write_wav("hmm.wav", _fade(samples, 30))


def aww():
    """Sympathetic / cute reaction — warm descending tone."""
    n = int(SAMPLE_RATE * 0.5)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 500 - 100 * (t / 0.5)
        vibrato = 10 * math.sin(2 * math.pi * 5 * t)
        env = math.sin(math.pi * t / 0.5) * 0.5
        s = env * (math.sin(2 * math.pi * (freq + vibrato) * t)
                   + 0.35 * math.sin(2 * math.pi * (freq + vibrato) * 2 * t))
        samples.append(s)
    _write_wav("aww.wav", _fade(samples, 25))


def ooh():
    """Impressed / amazed reaction — rising then holding tone."""
    n = int(SAMPLE_RATE * 0.5)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        if t < 0.2:
            freq = 300 + 400 * (t / 0.2)
        else:
            freq = 700 + 20 * math.sin(2 * math.pi * 5 * t)
        env = math.sin(math.pi * t / 0.5) * 0.5
        s = env * (math.sin(2 * math.pi * freq * t)
                   + 0.3 * math.sin(2 * math.pi * freq * 2 * t))
        samples.append(s)
    _write_wav("ooh.wav", _fade(samples, 25))


# ── NEW: Ambient / atmosphere ──────────────────────────────────────────────

def rain():
    """Steady rain ambience — filtered noise with droplet pings."""
    duration = 3.0
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Base rain — soft noise
        base = random.uniform(-0.2, 0.2)
        # Random droplet pings
        droplet = 0.0
        if random.random() < 0.002:
            droplet = 0.3
        samples.append(base + droplet * math.exp(-((t * 100) % 1) * 10))
    # Smooth it slightly
    for i in range(1, len(samples)):
        samples[i] = 0.7 * samples[i] + 0.3 * samples[i - 1]
    _write_wav("rain.wav", _fade(samples, 100))


def wind():
    """Howling wind ambience — modulated noise."""
    duration = 3.0
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Slow modulation for gusting effect
        gust = 0.3 + 0.3 * math.sin(2 * math.pi * 0.5 * t) + 0.15 * math.sin(2 * math.pi * 1.3 * t)
        noise = random.uniform(-1, 1)
        samples.append(gust * noise * 0.3)
    # Low-pass smoothing
    for i in range(1, len(samples)):
        samples[i] = 0.8 * samples[i] + 0.2 * samples[i - 1]
    _write_wav("wind.wav", _fade(samples, 150))


def ocean():
    """Ocean waves — rhythmic noise swells."""
    duration = 4.0
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Wave envelope — rises and falls like surf
        wave_env = 0.2 + 0.3 * (math.sin(2 * math.pi * 0.3 * t) ** 2)
        noise = random.uniform(-1, 1)
        samples.append(wave_env * noise * 0.35)
    # Heavy smoothing for that deep ocean sound
    for _ in range(3):
        for i in range(1, len(samples)):
            samples[i] = 0.85 * samples[i] + 0.15 * samples[i - 1]
    _write_wav("ocean.wav", _fade(samples, 200))


def fire_crackling():
    """Crackling fire — random pops over warm base."""
    duration = 3.0
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Warm low rumble
        base = 0.1 * math.sin(2 * math.pi * 80 * t + random.uniform(-0.5, 0.5))
        # Random crackles
        crackle = 0.0
        if random.random() < 0.005:
            crackle = random.uniform(0.3, 0.6) * random.choice([-1, 1])
        samples.append(base + crackle)
    # Light smoothing
    for i in range(1, len(samples)):
        samples[i] = 0.6 * samples[i] + 0.4 * samples[i - 1]
    _write_wav("fire_crackling.wav", _fade(samples, 100))


def thunder():
    """Rolling thunder — deep rumble with sharp crack."""
    samples = []
    # Initial crack — bright noise burst
    crack_n = int(SAMPLE_RATE * 0.1)
    for i in range(crack_n):
        t = i / SAMPLE_RATE
        vol = 0.8 * math.exp(-t * 20)
        samples.append(vol * random.uniform(-1, 1))
    # Rolling rumble — low modulated noise
    rumble_n = int(SAMPLE_RATE * 2.5)
    for i in range(rumble_n):
        t = i / SAMPLE_RATE
        vol = 0.5 * math.exp(-t * 1.2) * (0.5 + 0.5 * math.sin(2 * math.pi * 3 * t))
        low = 0.4 * math.sin(2 * math.pi * 40 * t + random.uniform(-0.3, 0.3))
        noise = random.uniform(-0.5, 0.5)
        samples.append(vol * (low + noise * 0.3))
    # Smooth for depth
    for _ in range(2):
        for i in range(1, len(samples)):
            samples[i] = 0.75 * samples[i] + 0.25 * samples[i - 1]
    _write_wav("thunder.wav", _fade(samples, 50))


# ── NEW: Musical ───────────────────────────────────────────────────────────

def piano_chord():
    """Rich piano chord — C major with harmonics and decay."""
    duration = 1.5
    n = int(SAMPLE_RATE * duration)
    # C major: C4, E4, G4, C5
    freqs = [261.6, 329.6, 392.0, 523.3]
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for f in freqs:
            env = 0.8 * math.exp(-t * 2.5)
            # Piano has strong fundamental + decaying harmonics
            s += env * (math.sin(2 * math.pi * f * t)
                        + 0.3 * math.sin(2 * math.pi * f * 2 * t) * math.exp(-t * 4)
                        + 0.1 * math.sin(2 * math.pi * f * 3 * t) * math.exp(-t * 6))
        samples.append(s / len(freqs))
    _write_wav("piano_chord.wav", _fade(samples, 20))


def guitar_strum():
    """Acoustic guitar strum — staggered string attacks."""
    duration = 1.2
    n = int(SAMPLE_RATE * duration)
    # Open G chord: G2, B2, D3, G3, B3, D4
    freqs = [98.0, 123.5, 146.8, 196.0, 246.9, 293.7]
    samples = [0.0] * n
    for idx, f in enumerate(freqs):
        delay = idx * 0.015  # stagger each string
        for i in range(n):
            t = i / SAMPLE_RATE - delay
            if t < 0:
                continue
            env = 0.5 * math.exp(-t * 3)
            s = env * (math.sin(2 * math.pi * f * t)
                       + 0.25 * math.sin(2 * math.pi * f * 2 * t)
                       + 0.1 * math.sin(2 * math.pi * f * 3 * t))
            samples[i] += s / len(freqs)
    _write_wav("guitar_strum.wav", _fade(samples, 15))


def drum_roll():
    """Snare drum roll — rapid alternating hits building to a crash."""
    samples = []
    # Accelerating hits
    hit_count = 20
    for h in range(hit_count):
        # Gap shrinks as roll builds
        gap = 0.08 * (1 - h / hit_count * 0.7)
        hit_dur = 0.03
        n = int(SAMPLE_RATE * hit_dur)
        vol = 0.3 + 0.4 * (h / hit_count)
        for i in range(n):
            t = i / SAMPLE_RATE
            env = vol * math.exp(-t * 40)
            samples.append(env * random.uniform(-1, 1))
        samples += _silence(gap)
    # Final crash — noise burst
    crash_n = int(SAMPLE_RATE * 0.4)
    for i in range(crash_n):
        t = i / SAMPLE_RATE
        vol = 0.7 * math.exp(-t * 4)
        samples.append(vol * random.uniform(-1, 1))
    _write_wav("drum_roll.wav", _fade(samples, 15))


# ── NEW: Notification / UI ─────────────────────────────────────────────────

def success():
    """Success chime — bright ascending two-tone."""
    samples = _fade(_tone(880, 0.15, 0.5), 15)
    samples += _fade(_tone(1320, 0.25, 0.5), 15)
    _write_wav("success.wav", samples)


def error_sound():
    """Error buzz — low harsh double-buzz."""
    samples = []
    for _ in range(2):
        n = int(SAMPLE_RATE * 0.12)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.5 * (1 - t / 0.12)
            # Square-ish wave for harsh buzzy sound
            samples.append(vol * (1 if math.sin(2 * math.pi * 200 * t) > 0 else -1) * 0.4)
        samples += _silence(0.08)
    _write_wav("error.wav", _fade(samples, 10))


def warning_sound():
    """Warning tone — two descending alert beeps."""
    samples = _fade(_tone(800, 0.15, 0.5), 15)
    samples += _silence(0.08)
    samples += _fade(_tone(600, 0.2, 0.5), 15)
    _write_wav("warning.wav", samples)


def notification():
    """Soft notification — gentle two-note chime."""
    n1 = int(SAMPLE_RATE * 0.15)
    samples = []
    for i in range(n1):
        t = i / SAMPLE_RATE
        vol = 0.4 * math.exp(-t * 8)
        samples.append(vol * math.sin(2 * math.pi * 1047 * t))
    samples += _silence(0.05)
    n2 = int(SAMPLE_RATE * 0.2)
    for i in range(n2):
        t = i / SAMPLE_RATE
        vol = 0.4 * math.exp(-t * 6)
        samples.append(vol * math.sin(2 * math.pi * 1319 * t))
    _write_wav("notification.wav", _fade(samples, 10))


# ── NEW: Miscellaneous ─────────────────────────────────────────────────────

def applause():
    """Crowd applause — overlapping random claps."""
    duration = 2.5
    n = int(SAMPLE_RATE * duration)
    samples = [0.0] * n
    # Generate many individual claps
    for _ in range(80):
        start = random.randint(0, n - int(SAMPLE_RATE * 0.05))
        clap_len = int(SAMPLE_RATE * random.uniform(0.01, 0.04))
        vol = random.uniform(0.1, 0.3)
        for j in range(clap_len):
            if start + j < n:
                t = j / SAMPLE_RATE
                env = vol * math.exp(-t * 50)
                samples[start + j] += env * random.uniform(-1, 1)
    # Clip
    peak = max(abs(s) for s in samples) or 1
    samples = [s / peak * 0.6 for s in samples]
    _write_wav("applause.wav", _fade(samples, 100))


def clock_ticking():
    """Steady clock tick-tock."""
    samples = []
    for tick in range(8):
        # Tick — higher
        freq = 1200 if tick % 2 == 0 else 900
        n = int(SAMPLE_RATE * 0.02)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.5 * math.exp(-t * 80)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(0.48)
    _write_wav("clock_ticking.wav", _fade(samples, 10))


def heartbeat():
    """Rhythmic heartbeat — lub-dub pattern."""
    samples = []
    for beat in range(4):
        # Lub — deep thump
        n = int(SAMPLE_RATE * 0.08)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.7 * math.exp(-t * 25)
            samples.append(vol * math.sin(2 * math.pi * 60 * t))
        samples += _silence(0.1)
        # Dub — slightly higher, softer
        n = int(SAMPLE_RATE * 0.06)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.5 * math.exp(-t * 30)
            samples.append(vol * math.sin(2 * math.pi * 80 * t))
        samples += _silence(0.46)
    _write_wav("heartbeat.wav", _fade(samples, 10))


def typing():
    """Keyboard typing — rapid key clicks."""
    samples = []
    for _ in range(15):
        # Individual key click
        n = int(SAMPLE_RATE * 0.008)
        freq = random.uniform(3000, 5000)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.4 * math.exp(-t * 200)
            samples.append(vol * math.sin(2 * math.pi * freq * t))
        samples += _silence(random.uniform(0.04, 0.12))
    _write_wav("typing.wav", _fade(samples, 5))


def door_knock():
    """Three knocks on a wooden door."""
    samples = []
    for _ in range(3):
        n = int(SAMPLE_RATE * 0.05)
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.7 * math.exp(-t * 40)
            # Low thud + noise for wood character
            thud = math.sin(2 * math.pi * 150 * t)
            wood = random.uniform(-0.3, 0.3)
            samples.append(vol * (thud * 0.7 + wood * 0.3))
        samples += _silence(0.2)
    _write_wav("door_knock.wav", _fade(samples, 10))


def footsteps():
    """Walking footsteps — alternating left/right steps."""
    samples = []
    for step in range(6):
        n = int(SAMPLE_RATE * 0.06)
        # Alternate slightly different tones for L/R foot
        base_freq = 120 if step % 2 == 0 else 140
        for i in range(n):
            t = i / SAMPLE_RATE
            vol = 0.5 * math.exp(-t * 30)
            thud = math.sin(2 * math.pi * base_freq * t)
            noise = random.uniform(-0.2, 0.2)
            samples.append(vol * (thud * 0.6 + noise * 0.4))
        samples += _silence(0.35)
    _write_wav("footsteps.wav", _fade(samples, 10))


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(SOUNDS_DIR, exist_ok=True)

    # Original Nova 2.0 sounds
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

    # Nova 3.0 — Emotional reactions
    gasp()
    sigh()
    hmm()
    aww()
    ooh()

    # Nova 3.0 — Ambient / atmosphere
    rain()
    wind()
    ocean()
    fire_crackling()
    thunder()

    # Nova 3.0 — Musical
    piano_chord()
    guitar_strum()
    drum_roll()

    # Nova 3.0 — Notification / UI
    success()
    error_sound()
    warning_sound()
    notification()

    # Nova 3.0 — Miscellaneous
    applause()
    clock_ticking()
    heartbeat()
    typing()
    door_knock()
    footsteps()

    count = len([f for f in os.listdir(SOUNDS_DIR) if f.endswith('.wav')])
    print(f"Generated {count} sounds in {SOUNDS_DIR}")
