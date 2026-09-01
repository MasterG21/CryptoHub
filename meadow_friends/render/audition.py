#!/usr/bin/env python3
"""
audition.py - picks the cast from the 904-speaker LibriTTS model.

I cannot listen to these, so speakers are ranked on measurable things: median
pitch (which decides who can play a mouse and who can play a lion), how steady
that pitch is, how tonal rather than noisy the voice is, and the speaking rate.
"""
import io, json, sys, wave
import numpy as np
from piper import PiperVoice, SynthesisConfig

LINE = "Good morning! What a lovely sunny day it is today."
SR_TARGET = 22050


def synth(voice, text, speaker_id):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(speaker_id=speaker_id))
    buf.seek(0)
    with wave.open(buf) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768
    return x, sr


def f0_track(x, sr, fmin=60, fmax=400):
    """Autocorrelation pitch track over voiced frames."""
    win, hop = int(0.040 * sr), int(0.010 * sr)
    lo, hi = int(sr / fmax), int(sr / fmin)
    out = []
    for s in range(0, max(1, len(x) - win), hop):
        fr = x[s:s + win]
        if np.sqrt((fr ** 2).mean()) < 0.02:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, 'full')[len(fr) - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if len(seg) < 4:
            continue
        k = int(np.argmax(seg)) + lo
        if ac[k] / ac[0] > 0.35:
            out.append(sr / k)
    return np.array(out)


def flatness(x):
    """Spectral flatness over the loud part only - silence would skew it."""
    win = int(len(x) * 0.02) or 1
    rms = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, 'same'))
    loud = x[rms > rms.max() * 0.35]
    if len(loud) < 512:
        loud = x
    sp = np.abs(np.fft.rfft(loud * np.hanning(len(loud)))) + 1e-9
    return float(np.exp(np.log(sp).mean()) / sp.mean())


def main():
    if '--cached' in sys.argv:
        rows = json.load(open('out/audition_raw.json'))
        return select(rows)
    model = 'voices/en-us-libritts-high.onnx'
    voice = PiperVoice.load(model, config_path=model + '.json')
    ids = [int(i) for i in np.linspace(0, 903, 120).astype(int)]
    rows = []
    for sid in ids:
        try:
            x, sr = synth(voice, LINE, sid)
        except Exception as e:
            continue
        if len(x) < sr * 0.5:
            continue
        f0 = f0_track(x, sr)
        if len(f0) < 12:
            continue
        rows.append({
            'id': sid,
            'f0': float(np.median(f0)),
            'jitter': float(np.std(f0) / max(np.median(f0), 1)),
            'dur': len(x) / sr,
            'rms': float(np.sqrt((x ** 2).mean())),
            'flat': flatness(x),
            'voiced': len(f0),
        })
        print('.', end='', flush=True)
    print()
    json.dump(rows, open('out/audition_raw.json', 'w'))   # cache: filter offline
    select(rows)


def select(rows):
    # a usable voice is steady, loud enough, tonal, and not rushed
    good = [r for r in rows
            if r['jitter'] < 0.22 and r['rms'] > 0.12 and r['flat'] < 0.22
            and 2.5 < r['dur'] < 4.3 and r['voiced'] > 170]
    print(f'{len(rows)} auditioned, {len(good)} usable\n')

    # one voice per pitch band, picking the steadiest in each
    bands = [('deep  (lion)', 0, 125), ('low   (frog)', 125, 150),
             ('mid   (cow)', 150, 190), ('warm  (elephant)', 190, 215),
             ('bright(duck)', 215, 250), ('high  (mouse)', 250, 400)]
    cast = {}
    used = set()
    print(f"{'band':<18} {'id':>4} {'f0Hz':>7} {'jitter':>7} {'dur':>5} {'rms':>6} {'flat':>6}")
    for name, lo, hi in bands:
        cands = [r for r in good if lo <= r['f0'] < hi and r['id'] not in used]
        if not cands:
            print(f'{name:<18}   -- nothing in band --')
            continue
        best = min(cands, key=lambda r: r['jitter'] * 2 + r['flat'])
        used.add(best['id'])
        cast[name.split()[0]] = best
        print(f"{name:<18} {best['id']:>4} {best['f0']:>7.1f} {best['jitter']:>7.3f} "
              f"{best['dur']:>5.2f} {best['rms']:>6.3f} {best['flat']:>6.3f}")
    json.dump({'all': good, 'cast': cast}, open('out/audition.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
