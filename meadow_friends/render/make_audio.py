#!/usr/bin/env python3
"""
make_audio.py - speaks the script, then builds the timeline the animation runs on.

For every line it: synthesises speech with Piper (one LibriTTS speaker per
character), shifts the pitch to give each animal its own cartoon register,
levels it, and measures two lip-sync curves straight off the waveform -
how open the mouth is, and how wide or round it is. The renderer reads those
curves, so the mouths cannot drift out of sync with the audio.

Outputs:
    out/audio.wav      the finished soundtrack
    out/timeline.json  beat timings, lip-sync curves, subtitle cues
"""
import argparse
import io
import json
import os
import struct
import subprocess
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voices as VOX

SR = 44100
GAP = 1.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ffmpeg_bin():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'


# --------------------------------------------------------------------- tts --
def wav_bytes(x, sr):
    pcm = (np.clip(x, -1, 1) * 32767).astype('<i2').tobytes()
    b = io.BytesIO()
    b.write(b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE')
    b.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, sr, sr * 2, 2, 16))
    b.write(b'data' + struct.pack('<I', len(pcm)) + pcm)
    return b.getvalue()


def read_wav(raw):
    with wave.open(io.BytesIO(raw)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768
    if ch == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    return x, sr


def pitch_shift(x, sr, factor, out_sr=SR):
    """Shift pitch without changing duration, via ffmpeg's asetrate/atempo."""
    if abs(factor - 1.0) < 0.005 and sr == out_sr:
        return x
    f = (f'asetrate={int(sr * factor)},atempo={1.0 / factor:.6f},aresample={out_sr}'
         if abs(factor - 1.0) >= 0.005 else f'aresample={out_sr}')
    p = subprocess.run(
        [ffmpeg_bin(), '-hide_banner', '-loglevel', 'error', '-f', 'wav', '-i', 'pipe:0',
         '-af', f, '-f', 'wav', '-ac', '1', 'pipe:1'],
        input=wav_bytes(x, sr), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    y, _ = read_wav(p.stdout)
    return y


def speak(voice, text, cfg, char):
    from piper import SynthesisConfig
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(
            speaker_id=char['speaker'], length_scale=1.0 / char.get('rate', 1.0),
            noise_scale=0.60, noise_w_scale=0.75))
    x, sr = read_wav(buf.getvalue())
    x = pitch_shift(x, sr, char.get('pitch', 1.0))
    x = trim_silence(x)
    peak = np.max(np.abs(x)) or 1.0
    return x / peak * 0.82                      # every character at one level


def trim_silence(x, thresh=0.012, pad=0.05):
    win = int(0.01 * SR)
    if len(x) < win * 3:
        return x
    rms = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, 'same'))
    idx = np.where(rms > thresh)[0]
    if len(idx) < 2:
        return x
    a = max(0, idx[0] - int(pad * SR))
    b = min(len(x), idx[-1] + int(pad * SR))
    return x[a:b]


# ---------------------------------------------------------------- lip sync --
def lipsync(x, fps):
    """Two curves per frame, taken from the audio itself.

    open  - how far the jaw drops, from short-window loudness
    wide  - vowel shape, from spectral centroid: an 'ee' is bright and wide,
            an 'oo' is dark and round
    """
    hop = SR / fps
    frames = max(1, int(np.ceil(len(x) / hop)))
    win = int(0.035 * SR)
    op = np.zeros(frames)
    wd = np.zeros(frames)
    for i in range(frames):
        c = int(i * hop)
        seg = x[max(0, c - win // 2): c + win // 2]
        if len(seg) < 64:
            continue
        op[i] = np.sqrt((seg ** 2).mean())
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) + 1e-9
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        wd[i] = float((sp * f).sum() / sp.sum())
    if op.max() > 0:
        op = np.clip(op / (np.percentile(op, 92) or 1), 0, 1) ** 0.72
    # fast to open, slower to close - a mouth does not snap shut
    sm = np.zeros_like(op)
    acc = 0.0
    for i, v in enumerate(op):
        acc = max(v, acc * 0.55) if v > acc else acc * 0.55 + v * 0.45
        sm[i] = acc
    wd = np.clip((wd - 700) / 1700, 0, 1)
    k = np.ones(3) / 3
    wd = np.convolve(wd, k, 'same')
    return np.round(sm, 3).tolist(), np.round(wd, 3).tolist()


# ------------------------------------------------------------------- build --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script', default=os.path.join(ROOT, 'script.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'out'))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    script = json.load(open(args.script))
    fps = script['meta']['fps']
    cast = script['cast']
    global GAP
    GAP = script['meta'].get('gap_scale', 1.0)

    from piper import PiperVoice
    model = os.path.join(ROOT, script['meta']['model'])
    print('loading', os.path.basename(model))
    voice = PiperVoice.load(model, config_path=model + '.json')

    events, cues = [], []
    t = 0.0
    for scene in script['scenes']:
        scene_start = t
        for beat in scene['beats']:
            kind = beat['t']
            ev = {'scene': scene['id'], 'set': scene['set'], 'sky': scene.get('sky', 'day'),
                  'shot': beat.get('shot', 'wide'), 'kind': kind, 'start': round(t, 4)}

            if kind == 'line':
                char = cast[beat['who']]
                audio = speak(voice, beat['text'], script, char)
                dur = len(audio) / SR
                op, wd = lipsync(audio, fps)
                ev.update({'who': beat['who'], 'text': beat['text'], 'dur': round(dur, 4),
                           'mood': beat.get('mood', 'neutral'), 'open': op, 'wide': wd,
                           '_audio': audio})
                cues.append((t, t + dur, f"{char['name']}: {beat['text']}"))
                t += dur + beat.get('gap', 0.3) * GAP
                print(f"  {t:7.2f}  {char['name']:<6} {dur:5.2f}s  {beat['text'][:52]}")

            elif kind == 'chorus':
                mix = None
                for i, who in enumerate(beat['who']):
                    a = speak(voice, beat['text'], script, cast[who])
                    off = int(i * 0.045 * SR)
                    buf = np.zeros(len(a) + off)
                    buf[off:] = a
                    if mix is None or len(buf) > len(mix):
                        mix2 = np.zeros(max(len(buf), len(mix) if mix is not None else 0))
                        if mix is not None:
                            mix2[:len(mix)] += mix
                        mix = mix2
                    mix[:len(buf)] += buf
                mix = mix / (np.max(np.abs(mix)) or 1.0) * 0.85
                dur = len(mix) / SR
                op, wd = lipsync(mix, fps)
                ev.update({'who': beat['who'][0], 'all': beat['who'], 'text': beat['text'],
                           'dur': round(dur, 4), 'mood': 'happy', 'open': op, 'wide': wd,
                           '_audio': mix})
                cues.append((t, t + dur, beat['text']))
                t += dur + beat.get('gap', 0.3) * GAP
                print(f"  {t:7.2f}  CHORUS {dur:5.2f}s  {beat['text']}")

            elif kind == 'sfx':
                a = VOX.SOUNDS[beat['sound']]() * 0.72
                dur = len(a) / SR
                ev.update({'sound': beat['sound'], 'dur': round(dur, 4), '_audio': a})
                t += dur + beat.get('gap', 0.3) * GAP

            elif kind == 'pause':
                ev.update({'dur': beat['dur']})
                t += beat['dur']

            elif kind == 'title':
                ev.update({'dur': beat['dur'], 'text': beat.get('text', '')})
                t += beat['dur']

            ev['end'] = round(t, 4)
            events.append(ev)
        print(f"-- scene '{scene['id']}' {scene_start:.1f} -> {t:.1f}s")

    total = t + 1.0

    # ------------------------------------------------------------- the mix --
    dialogue = np.zeros(int(total * SR) + SR)
    effects = np.zeros_like(dialogue)
    for ev in events:
        a = ev.pop('_audio', None)
        if a is None:
            continue
        s = int(ev['start'] * SR)
        bus = effects if ev['kind'] == 'sfx' else dialogue
        bus[s:s + len(a)] += a

    def fit(a, n):
        out = np.zeros(n)
        out[:min(n, len(a))] = a[:min(n, len(a))]
        return out

    N = len(dialogue)
    music = fit(underscore(total, events), N)
    ambience = fit(VOX.birds(total) * 0.55, N)

    # music ducks under anything anyone says
    env = np.abs(dialogue) + np.abs(effects)
    w = int(0.09 * SR)
    env = np.convolve(env, np.ones(w) / w, 'same')
    duck = 1.0 - 0.72 * np.clip(env / (np.percentile(env, 99) or 1) * 2.0, 0, 1)
    mono = dialogue * 1.0 + effects * 0.85 + music * duck + ambience * duck

    mono = mono - mono.mean()
    mono = np.tanh(mono / (np.percentile(np.abs(mono), 99.8) or 1) * 0.9)
    mono = mono / (np.max(np.abs(mono)) or 1) * 0.80
    delay = int(0.007 * SR)
    stereo = np.stack([mono, np.concatenate([np.zeros(delay), mono[:-delay]]) * 0.9 + mono * 0.1], 1)

    out_wav = os.path.join(args.out, 'audio.wav')
    write_wav(out_wav, stereo)

    for ev in events:
        ev.pop('_audio', None)
    json.dump({'meta': script['meta'], 'cast': cast, 'duration': round(total, 3),
               'events': events,
               'cues': [{'a': round(a, 3), 'b': round(b, 3), 'text': c} for a, b, c in cues]},
              open(os.path.join(args.out, 'timeline.json'), 'w'))

    print(f'\nwrote {out_wav}  {total:.1f}s')
    print(f'wrote {os.path.join(args.out, "timeline.json")}  '
          f'{len(events)} events, {len(cues)} subtitle cues')


def underscore(total, events):
    """A quiet, sparse bed - it must never compete with the dialogue."""
    n = int(total * SR) + SR
    out = np.zeros(n)
    bpm, beat = 96.0, 60.0 / 96.0
    chords = [[57, 60, 64], [53, 57, 60], [55, 59, 62], [52, 55, 60]]
    bar = 0
    t = 0.0
    while t < total:
        triad = chords[bar % len(chords)]
        for i, m in enumerate(triad):
            f = 440.0 * 2 ** ((m - 69) / 12)
            d = beat * 3.6
            ln = int(d * SR)
            tt = np.arange(ln) / SR
            x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)
                 + 0.12 * np.sin(6 * np.pi * f * tt))
            x *= np.exp(-tt / (d * 0.42)) * 0.055
            s = int((t + i * beat * 0.16) * SR)
            m = min(ln, len(out) - s)
            if m > 0:
                out[s:s + m] += x[:m]
        # a soft bass note under each bar
        fb = 440.0 * 2 ** ((triad[0] - 24 - 69) / 12)
        ln = int(beat * 3.4 * SR)
        tt = np.arange(ln) / SR
        s = int(t * SR)
        m = min(ln, len(out) - s)
        if m > 0:
            out[s:s + m] += (np.sin(2 * np.pi * fb * tt) * np.exp(-tt / 1.1) * 0.05)[:m]
        t += beat * 4
        bar += 1
    return out[:n]


def write_wav(path, stereo):
    pcm = (np.clip(stereo, -1, 1) * 32767).astype('<i2').tobytes()
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVE')
        f.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 2, SR, SR * 4, 4, 16))
        f.write(b'data' + struct.pack('<I', len(pcm)) + pcm)


if __name__ == '__main__':
    main()
