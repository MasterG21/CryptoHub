#!/usr/bin/env python3
"""
voices.py - the animal noises, synthesised from scratch with numpy.

These are the non-speech sounds (a moo, a quack, a roar). Cartoon
approximations built from oscillators and filtered noise, so there is nothing
sampled or licensed anywhere in the soundtrack.
"""
import numpy as np

SR = 44100


def env_ad(n, attack, decay, sr=SR):
    a = max(1, int(attack * sr))
    out = np.ones(n)
    out[:a] = np.linspace(0, 1, a)
    out[a:] = np.exp(-(np.arange(n - a) / sr) / max(decay, 1e-4))
    return out


def env_adsr(n, a, d, s, r, sr=SR):
    a, d, r = max(1, int(a * sr)), max(1, int(d * sr)), max(1, int(r * sr))
    sus = max(0, n - a - d - r)
    return np.concatenate([np.linspace(0, 1, a), np.linspace(1, s, d),
                           np.full(sus, s), np.linspace(s, 0, r)])[:n]


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def lowpass(x, cutoff, sr=SR):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return np.fft.irfft(spec / (1 + (f / cutoff) ** 2), len(x))


def _moo():
    n = int(0.85 * SR); t = np.arange(n) / SR
    f = np.interp(t, [0, 0.25, 0.85], [200, 186, 148]) * (1 + 0.03 * np.sin(2 * np.pi * 5 * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.55 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph) + 0.1 * np.sin(4 * ph)
    return x * env_adsr(n, 0.10, 0.14, 0.78, 0.34)


def _quack():
    out = np.zeros(int(0.5 * SR))
    for k, off in enumerate((0.0, 0.24)):
        n = int(0.18 * SR); t = np.arange(n) / SR
        f = np.linspace(540, 405, n)
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = (np.sin(ph) + 0.5 * np.sign(np.sin(ph))) * (0.6 + 0.4 * np.sin(2 * np.pi * 44 * t))
        out[int(off * SR):int(off * SR) + n] += x * env_ad(n, 0.006, 0.05)
    return out


def _ribbit():
    out = np.zeros(int(0.56 * SR))
    for off, f0 in ((0.0, 215), (0.22, 152)):
        n = int(0.2 * SR); t = np.arange(n) / SR
        x = np.sign(np.sin(2 * np.pi * f0 * t)) * (0.5 + 0.5 * np.sin(2 * np.pi * 56 * t))
        out[int(off * SR):int(off * SR) + n] += lowpass(x, 1300) * env_ad(n, 0.005, 0.055)
    return out


def _roar():
    n = int(1.05 * SR); t = np.arange(n) / SR
    f = np.interp(t, [0, 0.3, 1.05], [112, 98, 80])
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.6 * np.sin(2 * ph) + 0.3 * np.sin(3 * ph)
    rasp = lowpass(noise(n, 23), 950) * 2.2
    return (tone + rasp) * (1 + 0.22 * np.sin(2 * np.pi * 21 * t)) * env_adsr(n, 0.12, 0.2, 0.7, 0.36)


def _toot():
    out = np.zeros(int(1.15 * SR))
    for off in (0.0, 0.55):
        n = int(0.5 * SR); t = np.arange(n) / SR
        f = np.interp(t, [0, 0.08, 0.5], [300, 396, 388]) * (1 + 0.02 * np.sin(2 * np.pi * 6 * t))
        ph = 2 * np.pi * np.cumsum(f) / SR
        saw = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
        x = lowpass(saw, 2700) + 0.4 * np.sin(ph)
        out[int(off * SR):int(off * SR) + n] += x * env_adsr(n, 0.03, 0.1, 0.8, 0.2)
    return out


def _squeak():
    n = int(0.22 * SR); t = np.arange(n) / SR
    f = np.interp(t, [0, 0.1, 0.22], [900, 1500, 1100])
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) + 0.3 * np.sin(2 * ph)) * env_ad(n, 0.008, 0.05)


def _levelled(fn):
    def wrapped():
        x = fn()
        return x / (np.max(np.abs(x)) or 1.0)
    return wrapped


SOUNDS = {k: _levelled(v) for k, v in {
    'moo': _moo, 'quack': _quack, 'ribbit': _ribbit, 'roar': _roar,
    'toot': _toot, 'squeak': _squeak}.items()}


def birds(seconds, seed=7):
    """Sparse birdsong for the meadow ambience."""
    n = int(seconds * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(seed)
    t_at = 0.6
    while t_at < seconds - 1.5:
        chirps = rng.integers(2, 5)
        base = rng.uniform(2200, 3400)
        for c in range(int(chirps)):
            d = rng.uniform(0.05, 0.11)
            m = int(d * SR); tt = np.arange(m) / SR
            f = base * np.interp(tt, [0, d], [1.0, rng.uniform(1.15, 1.5)])
            x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(m, 0.006, 0.03)
            s = int((t_at + c * rng.uniform(0.09, 0.16)) * SR)
            if s + m < n:
                out[s:s + m] += x * rng.uniform(0.10, 0.2)
        t_at += rng.uniform(2.6, 6.0)
    return out
