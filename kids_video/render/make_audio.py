#!/usr/bin/env python3
"""
make_audio.py - builds the soundtrack from scratch with numpy.

Everything is synthesised: no samples, no loops, nothing licensed. The song
structure and the animal voices are driven by the same script.json the
animation uses, so the "MOO!" you hear lands on the frame the speech bubble
pops.

    python3 render/make_audio.py [-o out/animal-sounds-song.wav]
"""
import argparse
import json
import os
import struct
import numpy as np

SR = 44100
BPM = 120.0
BEAT = 60.0 / BPM          # 0.5 s
BAR = 4 * BEAT             # 2.0 s

# ------------------------------------------------------------------ helpers --
def env_ad(n, attack, decay, sr=SR):
    """Attack/decay envelope, exponential tail - the shape of a struck note."""
    a = max(1, int(attack * sr))
    out = np.ones(n)
    out[:a] = np.linspace(0, 1, a)
    tail = np.arange(n - a) / sr
    out[a:] = np.exp(-tail / max(decay, 1e-4))
    return out


def env_adsr(n, a, d, s, r, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    a, d, r = max(1, a), max(1, d), max(1, r)
    sus = max(0, n - a - d - r)
    return np.concatenate([
        np.linspace(0, 1, a),
        np.linspace(1, s, d),
        np.full(sus, s),
        np.linspace(s, 0, r),
    ])[:n]


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def lowpass(x, cutoff, sr=SR):
    """One-pole lowpass - enough to take the fizz off noise and saw waves."""
    a = np.exp(-2 * np.pi * cutoff / sr)
    out = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        out[i] = acc
    return out


def lowpass_fast(x, cutoff, sr=SR):
    """Vectorised approximation via FFT brick wall - fine for our purposes."""
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec *= 1.0 / (1.0 + (freqs / cutoff) ** 2)
    return np.fft.irfft(spec, n)


# ---------------------------------------------------------------- voices ----
def pluck(freq, dur, amp=1.0):
    """Marimba-ish tone: a few harmonics with a quick exponential decay."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    parts = [(1.0, 1.0), (2.0, 0.32), (3.0, 0.12), (4.01, 0.05)]
    x = sum(a * np.sin(2 * np.pi * freq * m * t) for m, a in parts)
    return x * env_ad(n, 0.004, dur * 0.34) * amp * 0.25


def bell(freq, dur, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    parts = [(1.0, 1.0), (2.76, 0.5), (5.4, 0.22), (8.9, 0.08)]
    x = sum(a * np.sin(2 * np.pi * freq * m * t) for m, a in parts)
    return x * env_ad(n, 0.002, dur * 0.5) * amp * 0.18


def bass(freq, dur, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.28 * np.sin(4 * np.pi * freq * t)
    return x * env_adsr(n, 0.012, 0.10, 0.72, 0.10) * amp * 0.34


def pad(freq, dur, amp=1.0):
    """Soft breathy chord tone that fills the space under the melody."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * freq * t)
         + 0.5 * np.sin(2 * np.pi * freq * 2 * t + 0.4)
         + 0.25 * np.sin(2 * np.pi * freq * 3 * t + 1.1))
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t)
    return x * vib * env_adsr(n, 0.09, 0.18, 0.55, 0.30) * amp * 0.10


def kick():
    n = int(0.26 * SR)
    t = np.arange(n) / SR
    f = 128 * np.exp(-t * 26) + 46
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return x * env_ad(n, 0.001, 0.075) * 0.55


def shaker(seed, amp=1.0):
    n = int(0.075 * SR)
    x = noise(n, seed)
    x = x - lowpass_fast(x, 3000)          # high-passed hiss
    return x * env_ad(n, 0.001, 0.020) * 0.16 * amp


def clap(seed):
    n = int(0.20 * SR)
    x = noise(n, seed)
    x = x - lowpass_fast(x, 900)
    return x * env_ad(n, 0.002, 0.055) * 0.24


# ------------------------------------------------------- animal "voices" ----
# Cartoon approximations, all synthesised. Each returns a mono float array.
def v_moo():
    dur, n = 0.75, int(0.75 * SR)
    t = np.arange(n) / SR
    f = np.linspace(196, 150, n) * (1 + 0.03 * np.sin(2 * np.pi * 5 * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.55 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)
    return x * env_adsr(n, 0.09, 0.12, 0.75, 0.30) * 0.30


def v_quack():
    out = np.zeros(int(0.42 * SR))
    for k, off in enumerate((0.0, 0.22)):
        n = int(0.17 * SR)
        t = np.arange(n) / SR
        f = np.linspace(520, 400, n)
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = np.sign(np.sin(ph)) * 0.5 + np.sin(ph)      # buzzy
        x *= (0.6 + 0.4 * np.sin(2 * np.pi * 42 * t))   # nasal AM
        x *= env_ad(n, 0.006, 0.045)
        s = int(off * SR)
        out[s:s + n] += x * 0.26
    return out


def v_meow():
    n = int(0.62 * SR)
    t = np.arange(n) / SR
    f = np.interp(t, [0, 0.18, 0.36, 0.62], [520, 780, 700, 430])
    f *= 1 + 0.035 * np.sin(2 * np.pi * 6.5 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.16 * np.sin(3 * ph)
    return x * env_adsr(n, 0.05, 0.10, 0.8, 0.28) * 0.24


def v_woof():
    out = np.zeros(int(0.46 * SR))
    for k, off in enumerate((0.0, 0.24)):
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        f = np.linspace(300, 165, n)
        ph = 2 * np.pi * np.cumsum(f) / SR
        body = np.sin(ph) + 0.45 * np.sin(2 * ph)
        grit = lowpass_fast(noise(n, 11 + k), 1400) * 1.6
        x = (body + grit) * env_ad(n, 0.004, 0.05)
        s = int(off * SR)
        out[s:s + n] += x * 0.26
    return out


def v_ribbit():
    out = np.zeros(int(0.5 * SR))
    for k, (off, f0) in enumerate(((0.0, 210), (0.2, 150))):
        n = int(0.18 * SR)
        t = np.arange(n) / SR
        ph = 2 * np.pi * f0 * t
        x = np.sign(np.sin(ph)) * (0.5 + 0.5 * np.sin(2 * np.pi * 55 * t))
        x = lowpass_fast(x, 1200) * env_ad(n, 0.004, 0.05)
        s = int(off * SR)
        out[s:s + n] += x * 0.30
    return out


def v_roar():
    n = int(0.95 * SR)
    t = np.arange(n) / SR
    f = np.interp(t, [0, 0.3, 0.95], [110, 96, 78])
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.6 * np.sin(2 * ph) + 0.3 * np.sin(3 * ph)
    rasp = lowpass_fast(noise(n, 23), 900) * 2.2
    x = (tone + rasp) * (1 + 0.25 * np.sin(2 * np.pi * 22 * t))
    return x * env_adsr(n, 0.10, 0.18, 0.7, 0.34) * 0.22


def v_monkey():
    out = np.zeros(int(1.0 * SR))
    hoots = [(0.00, 540, 760), (0.20, 540, 760), (0.42, 800, 500), (0.62, 800, 490)]
    for k, (off, f0, f1) in enumerate(hoots):
        n = int(0.19 * SR)
        t = np.arange(n) / SR
        f = np.linspace(f0, f1, n) * (1 + 0.05 * np.sin(2 * np.pi * 9 * t))
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * env_ad(n, 0.012, 0.05)
        s = int(off * SR)
        out[s:s + n] += x * 0.22
    return out


def v_toot():
    n = int(0.68 * SR)
    t = np.arange(n) / SR
    f = np.interp(t, [0, 0.1, 0.68], [300, 392, 384])
    f *= 1 + 0.02 * np.sin(2 * np.pi * 6 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    saw = 2 * (ph / (2 * np.pi) % 1.0) - 1                 # brassy
    x = lowpass_fast(saw, 2600) + 0.4 * np.sin(ph)
    return x * env_adsr(n, 0.035, 0.12, 0.78, 0.22) * 0.20


def _levelled(fn):
    """Every animal lands at the same peak, so none of them gets lost."""
    def wrapped():
        x = fn()
        return x / (np.max(np.abs(x)) or 1.0) * 0.85
    return wrapped


VOICES = {k: _levelled(v) for k, v in {
    'cow': v_moo, 'duck': v_quack, 'cat': v_meow, 'dog': v_woof,
    'frog': v_ribbit, 'lion': v_roar, 'monkey': v_monkey,
    'elephant': v_toot}.items()}


def sfx_sparkle(seed=0):
    """Ascending chime - plays with every confetti burst."""
    out = np.zeros(int(1.1 * SR))
    for i, m in enumerate([72, 76, 79, 84, 88]):
        s = int(i * 0.055 * SR)
        b = bell(midi_hz(m), 0.85, 0.75)
        out[s:s + len(b)] += b
    return out


def sfx_whoosh(seed=1):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    x = lowpass_fast(noise(n, 100 + seed), 2400)
    x *= np.sin(np.pi * t / t[-1]) ** 2
    return x * 0.16


def sfx_pop():
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    f = np.linspace(340, 1100, n)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return x * env_ad(n, 0.002, 0.03) * 0.18


# ------------------------------------------------------------- arrangement --
CHORDS = {                       # root, then the notes of the triad
    'C':  (36, [60, 64, 67]),
    'G':  (31, [59, 62, 67]),
    'Am': (33, [57, 60, 64]),
    'F':  (29, [57, 60, 65]),
    'Dm': (26, [57, 62, 65]),
    'Em': (28, [59, 64, 67]),
}

# Melody phrase over six bars, as (beat, midi, beats-long). Beat = 0.5 s.
VERSE_MELODY = [
    (0.0, 67, 0.5), (0.5, 69, 0.5), (1.0, 67, 1.0), (2.0, 64, 1.0), (3.0, 60, 1.0),
    (4.0, 62, 0.5), (4.5, 67, 0.5), (5.0, 71, 1.5),
    (8.0, 69, 0.5), (9.0, 72, 0.5), (10.0, 69, 0.5), (11.0, 67, 1.0),
    (12.0, 65, 0.5), (13.0, 69, 0.5), (14.0, 72, 1.5),
    (16.0, 64, 0.5), (17.0, 67, 0.5), (18.0, 72, 0.5), (19.0, 67, 1.0),
    (20.0, 74, 0.5), (21.0, 71, 0.5), (22.0, 67, 2.0),
]
VERSE_CHORDS = ['C', 'G', 'Am', 'F', 'C', 'G']

GUESS_MELODY = [(0.0, 64, 0.5), (0.5, 65, 0.5), (1.0, 67, 1.0),
                (2.0, 69, 0.5), (2.5, 67, 0.5), (3.0, 64, 1.0),
                (8.0, 72, 0.5), (9.0, 76, 0.5), (10.0, 79, 1.5), (12.0, 72, 2.0)]
GUESS_CHORDS = ['Am', 'F', 'C', 'G']

CHORUS_MELODY = [
    (0.0, 72, 0.5), (0.5, 71, 0.5), (1.0, 69, 0.5), (1.5, 67, 0.5), (2.0, 72, 2.0),
    (4.0, 71, 0.5), (4.5, 69, 0.5), (5.0, 67, 0.5), (5.5, 65, 0.5), (6.0, 67, 2.0),
    (8.0, 69, 0.5), (8.5, 71, 0.5), (9.0, 72, 1.0), (10.0, 76, 2.0),
    (12.0, 74, 0.5), (12.5, 72, 0.5), (13.0, 71, 0.5), (13.5, 69, 0.5), (14.0, 72, 2.0),
]
CHORUS_CHORDS = ['C', 'G', 'Am', 'F', 'C', 'G', 'F', 'G']

OUTRO_MELODY = [(0.0, 72, 1.0), (1.0, 69, 1.0), (2.0, 67, 2.0),
                (4.0, 65, 1.0), (5.0, 64, 1.0), (6.0, 62, 2.0),
                (8.0, 60, 1.0), (9.0, 64, 1.0), (10.0, 67, 1.0), (11.0, 72, 4.0)]
OUTRO_CHORDS = ['C', 'Am', 'F', 'G', 'C', 'C']

INTRO_MELODY = [(4.0, 60, 0.5), (4.5, 64, 0.5), (5.0, 67, 0.5), (5.5, 72, 1.5),
                (8.0, 71, 0.5), (8.5, 67, 0.5), (9.0, 64, 0.5), (9.5, 67, 0.5),
                (10.0, 72, 2.0)]
INTRO_CHORDS = ['C', 'C', 'F', 'G', 'C', 'G']


class Mix:
    """Two buses: the band, and the animals on top of it.

    The animal call is the whole point of the video, so it gets its own bus and
    the music ducks underneath it - the same trick a radio voiceover uses.
    """

    def __init__(self, seconds):
        self.n = int(seconds * SR) + SR
        self.music = np.zeros(self.n)
        self.voice = np.zeros(self.n)

    def add(self, sig, at, gain=1.0, bus='music'):
        buf = self.voice if bus == 'voice' else self.music
        s = int(at * SR)
        if s < 0:
            sig, s = sig[-s:], 0
        e = min(self.n, s + len(sig))
        if e > s:
            buf[s:e] += sig[:e - s] * gain

    def render(self):
        env = np.abs(self.voice)
        win = int(0.06 * SR)                       # 60 ms envelope follower
        env = np.convolve(env, np.ones(win) / win, mode='same')
        peak = np.max(env) or 1.0
        duck = 1.0 - 0.62 * np.clip(env / peak * 2.4, 0, 1)
        return self.music * duck + self.voice * 1.8


def lay_section(mix, t0, bars, chords, melody, *, drums=True, density=1.0,
                octave_double=False, seed=0):
    """Drop one section of the arrangement onto the timeline."""
    for b in range(bars):
        bt = t0 + b * BAR
        name = chords[b % len(chords)]
        root, triad = CHORDS[name]
        mix.add(bass(midi_hz(root), BAR * 0.92), bt, 0.9)
        mix.add(bass(midi_hz(root + 12), BEAT * 0.9), bt + 2 * BEAT, 0.35)
        for m in triad:                                  # off-beat chord stabs
            for k in (1, 3):
                mix.add(pluck(midi_hz(m), BEAT * 0.85, 0.5 * density),
                        bt + k * BEAT, 0.55)
            mix.add(pad(midi_hz(m), BAR * 0.95, 0.8), bt, 0.8)
        if drums:
            mix.add(kick(), bt, 1.0)
            mix.add(kick(), bt + 2 * BEAT, 0.85)
            mix.add(clap(seed + b), bt + 2 * BEAT, 0.8)
            for h in range(8):
                mix.add(shaker(seed * 31 + b * 8 + h, 1.0 if h % 2 == 0 else 0.6),
                        bt + h * BEAT / 2, 0.9)
    for (beat, m, length) in melody:
        at = t0 + beat * BEAT
        mix.add(pluck(midi_hz(m), max(0.28, length * BEAT), 1.0), at, 1.0)
        mix.add(bell(midi_hz(m + 12), max(0.3, length * BEAT * 0.8), 0.55), at, 0.7)
        if octave_double:
            mix.add(pluck(midi_hz(m + 12), max(0.24, length * BEAT * 0.7), 0.7), at, 0.6)


def build(script):
    scenes, t, total = [], 0.0, 0.0
    for sc in script['scenes']:
        scenes.append((sc, t))
        t += sc['dur']
    total = t
    mix = Mix(total + 2)

    for idx, (sc, t0) in enumerate(scenes):
        bars = int(round(sc['dur'] / BAR))
        kind = sc['type']
        if kind == 'intro':
            lay_section(mix, t0, bars, INTRO_CHORDS, INTRO_MELODY,
                        drums=True, density=0.8, seed=idx)
            mix.add(sfx_sparkle(), t0 + 0.35, 1.0)
            mix.add(sfx_sparkle(), t0 + 8.6, 0.9)
        elif kind == 'verse':
            lay_section(mix, t0, bars, VERSE_CHORDS, VERSE_MELODY, seed=idx)
            voice = VOICES[sc['animal']]
            for at in (3.35, 4.15, 4.95, 9.35, 10.15, 10.95):
                mix.add(sfx_pop(), t0 + at - 0.05, 0.5)
                mix.add(voice(), t0 + at, 1.0, bus='voice')
            for at in (9.35, 10.15, 10.95):
                mix.add(sfx_sparkle(), t0 + at, 0.35)
        elif kind == 'guess':
            lay_section(mix, t0, bars, GUESS_CHORDS, GUESS_MELODY,
                        drums=True, density=0.6, seed=idx)
            voice = VOICES[sc['animal']]
            mix.add(sfx_whoosh(idx), t0 + 3.75, 1.0)
            mix.add(sfx_sparkle(), t0 + 3.95, 1.0)
            for at in (4.5, 5.4, 6.3, 7.1):
                mix.add(sfx_pop(), t0 + at - 0.05, 0.45)
                mix.add(voice(), t0 + at, 1.0, bus='voice')
        elif kind == 'chorus':
            lay_section(mix, t0, bars, CHORUS_CHORDS, CHORUS_MELODY,
                        octave_double=True, seed=idx)
            # every animal calls out once, in order, across the section
            for i, key in enumerate(['cow', 'duck', 'cat', 'dog',
                                     'frog', 'lion', 'monkey', 'elephant']):
                mix.add(VOICES[key](), t0 + 4.1 + i * 0.95, 0.9, bus='voice')
            for at in (0.3, 4.2, 8.2, 12.2):
                mix.add(sfx_sparkle(), t0 + at, 0.6)
        elif kind == 'outro':
            lay_section(mix, t0, bars, OUTRO_CHORDS, OUTRO_MELODY,
                        drums=True, density=0.7, seed=idx)
            mix.add(sfx_sparkle(), t0 + 0.4, 0.9)
            mix.add(sfx_sparkle(), t0 + 8.4, 0.9)
            for m in [60, 64, 67, 72]:                    # final chord swell
                mix.add(bell(midi_hz(m), 3.4, 1.0), t0 + sc['dur'] - 3.6, 0.9)
        if idx + 1 < len(scenes):                          # transition whoosh
            mix.add(sfx_whoosh(idx), t0 + sc['dur'] - 0.28, 0.8)

    return mix.render()[:int(total * SR)], total


def master(x):
    """Gentle soft-clip then normalise - keeps it loud but never harsh."""
    x = x - np.mean(x)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak * 1.25
    x = np.tanh(x)                       # soft limiter
    x = x / (np.max(np.abs(x)) or 1.0) * 0.77   # lands near -14 LUFS, ~-2 dBTP
    # tiny stereo spread so it does not feel like a mono phone speaker
    delay = int(0.008 * SR)
    left = x.copy()
    right = np.concatenate([np.zeros(delay), x[:-delay]]) * 0.94 + x * 0.06
    return np.stack([left, right], axis=1)


def write_wav(path, stereo):
    data = np.clip(stereo, -1, 1)
    pcm = (data * 32767).astype('<i2').tobytes()
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE')
        f.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 2, SR, SR * 4, 4, 16))
        f.write(b'data' + struct.pack('<I', len(pcm)) + pcm)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default=os.path.join(root, 'out', 'animal-sounds-song.wav'))
    ap.add_argument('-s', '--script', default=os.path.join(root, 'script.json'))
    args = ap.parse_args()

    script = json.load(open(args.script))
    mono, total = build(script)
    stereo = master(mono)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    write_wav(args.out, stereo)
    print(f'wrote {args.out}  {total:.1f}s  {os.path.getsize(args.out)/1e6:.1f} MB')


if __name__ == '__main__':
    main()
