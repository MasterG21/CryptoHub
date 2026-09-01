#!/usr/bin/env python3
"""
make_subs.py - English subtitles and the video description, from the timeline.

The cues come from the same file the animation reads, so the .srt cannot drift
out of sync with the picture, and the chapter timestamps cannot drift from the
cut.

    python3 render/make_subs.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ts(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def main():
    tl = json.load(open(os.path.join(ROOT, 'out', 'timeline.json')))
    script = json.load(open(os.path.join(ROOT, 'script.json')))
    out_dir = os.path.join(ROOT, 'out')

    cues = [(c['a'], c['b'], c['text']) for c in tl['cues']]
    for i in range(len(cues) - 1):                       # never overlap
        if cues[i][1] > cues[i + 1][0] - 0.05:
            cues[i] = (cues[i][0], cues[i + 1][0] - 0.05, cues[i][2])

    srt = os.path.join(out_dir, 'meadow-friends.en.srt')
    with open(srt, 'w', encoding='utf-8') as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{text}\n\n')

    # transcript
    with open(os.path.join(out_dir, 'transcript.txt'), 'w', encoding='utf-8') as f:
        f.write(f"{script['meta']['title']} - {script['meta']['episode']}\n\n")
        scene = None
        for ev in tl['events']:
            if ev['scene'] != scene:
                scene = ev['scene']
                mm, ss = divmod(int(ev['start']), 60)
                f.write(f'\n[{mm}:{ss:02d}] {scene.upper()}\n')
            if ev['kind'] in ('line', 'chorus'):
                who = tl['cast'][ev['who']]['name'] if ev['kind'] == 'line' else 'EVERYONE'
                f.write(f"    {who}: {ev['text']}\n")
            elif ev['kind'] == 'sfx':
                f.write(f"    ({ev['sound']})\n")

    # chapters, one per scene
    titles = {
        'morning': 'A sunny morning in the meadow',
        'cow': 'Bella the cow says moo',
        'duck': 'Pip the duck says quack',
        'frog': 'Hop the frog says ribbit',
        'lion': 'Leo the lion says roar',
        'together': 'Everyone sings together',
    }
    chapters, seen = [], set()
    for ev in tl['events']:
        if ev['scene'] in seen:
            continue
        seen.add(ev['scene'])
        mm, ss = divmod(int(round(ev['start'])), 60)
        chapters.append(f"{mm}:{ss:02d} {titles.get(ev['scene'], ev['scene'])}")

    names = ', '.join(c['name'] for c in tl['cast'].values())
    with open(os.path.join(out_dir, 'description.txt'), 'w', encoding='utf-8') as f:
        f.write(
            f"{script['meta']['title']} - {script['meta']['episode']}\n\n"
            "Milo the mouse hears a mystery sound in the meadow, so he and Ellie "
            "the elephant set off to find out who is making it. Along the way they "
            "meet Bella the cow, Pip the duck, Hop the frog and Leo the lion - and "
            "your little one is invited to make every sound along with them.\n\n"
            "Gentle 3D animation, friendly voices, and clear English subtitles on "
            "every line, so children can listen, watch and read along.\n\n"
            "CHAPTERS\n" + "\n".join(chapters) + "\n\n"
            "WHO YOU WILL MEET\n" + f"    {names}\n\n"
            "WHAT YOUR CHILD PRACTISES\n"
            "- Animal names and the sounds they make\n"
            "- Listening, copying and taking turns\n"
            "- Answering a friendly question out loud\n"
            "- Early reading, following the words on screen\n\n"
            "Every part of this video is original: the characters and sets are "
            "built in code, the voices are synthesised, and the music and animal "
            "sounds are generated from scratch.\n")

    print(f'wrote {srt} ({len(cues)} cues)')
    print(f'wrote {os.path.join(out_dir, "transcript.txt")}')
    print(f'wrote {os.path.join(out_dir, "description.txt")} ({len(chapters)} chapters)')


if __name__ == '__main__':
    main()
