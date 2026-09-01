#!/usr/bin/env python3
"""
make_subs.py - English subtitles and description text, straight from script.json.

The .srt is generated from the same caption cues the animation draws, so the
closed captions can never drift out of sync with the words on screen. The
chapter timestamps in the description come from the same place, so they cannot
drift either.

    python3 render/make_subs.py
"""
import json
import os


def ts(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = json.load(open(os.path.join(root, 'script.json')))

    cues, t = [], 0.0
    for scene in script['scenes']:
        for c in scene['captions']:
            cues.append((t + c['t'], t + c['t'] + c['d'], c['text']))
        t += scene['dur']

    # never let one cue run into the next
    for i in range(len(cues) - 1):
        if cues[i][1] > cues[i + 1][0] - 0.05:
            cues[i] = (cues[i][0], cues[i + 1][0] - 0.05, cues[i][2])

    out_dir = os.path.join(root, 'out')
    os.makedirs(out_dir, exist_ok=True)
    srt = os.path.join(out_dir, 'animal-sounds-song.en.srt')
    with open(srt, 'w', encoding='utf-8') as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{text}\n\n')

    lyrics = os.path.join(out_dir, 'lyrics.txt')
    with open(lyrics, 'w', encoding='utf-8') as f:
        f.write(f"{script['meta']['title']} - {script['meta']['subtitle']}\n\n")
        t = 0.0
        for scene in script['scenes']:
            mm, ss = divmod(int(t), 60)
            f.write(f"[{mm}:{ss:02d}] {scene['id'].upper()}\n")
            for c in scene['captions']:
                f.write(f"    {c['text']}\n")
            f.write('\n')
            t += scene['dur']

    # ---- YouTube description, with chapters at the real scene boundaries ----
    titles = {
        'intro': 'Hello, animal friends!', 'chorus': 'Sing along with everyone!',
        'outro': 'Goodbye!',
    }
    lines, t = [], 0.0
    for scene in script['scenes']:
        mm, ss = divmod(int(round(t)), 60)
        if scene['type'] == 'verse':
            label = f"The {scene['name']} says {scene['sound']}!"
        elif scene['type'] == 'guess':
            label = f"Guess who says {scene['sound']}?"
        else:
            label = titles.get(scene['type'], scene['id'])
        lines.append(f'{mm}:{ss:02d} {label}')
        t += scene['dur']

    desc = os.path.join(out_dir, 'description.txt')
    meta = script['meta']
    with open(desc, 'w', encoding='utf-8') as f:
        f.write(
            f"{meta['title']} - {meta['subtitle']}\n\n"
            "Sing along and make the animal sounds! Meet eight friendly animals - "
            "the cow, the duck, the cat, the dog, the frog, the lion, the monkey and "
            "the elephant - and copy each sound out loud. Then play a guessing game "
            "and sing the animal song together at the end.\n\n"
            "Big, colourful animations and clear English subtitles on every line, so "
            "little ones can listen, watch and read along.\n\n"
            "CHAPTERS\n" + "\n".join(lines) + "\n\n"
            "WHAT YOUR CHILD PRACTISES\n"
            "- Animal names and the sounds they make\n"
            "- Listening, copying and taking turns\n"
            "- Early reading, following the words on screen\n"
            "- Simple question-and-answer play (\"Can you say MOO?\")\n\n"
            "All the artwork, animation and music in this video is original and made "
            "for this channel.\n"
        )

    print(f'wrote {srt} ({len(cues)} cues, {t:.0f}s)')
    print(f'wrote {lyrics}')
    print(f'wrote {desc} ({len(lines)} chapters)')


if __name__ == '__main__':
    main()
