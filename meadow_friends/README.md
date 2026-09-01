# Meadow Friends — a 3D kids' episode, rendered from code

A 2:27 animated episode for toddlers. Six characters talk to each other in a
3D meadow: Milo the mouse hears a mystery sound, and he and Ellie the elephant
go and find out who is making it. Every line is spoken aloud, and English
subtitles are burned into the picture and supplied separately as an `.srt`.

    ./render/build.sh              # → out/meadow-friends.mp4 (+ subtitles, thumbnail)
    ./render/build.sh --quick      # 540p draft, for checking staging and timing

Open `web/index.html` through a local server to scrub the episode with a
transport bar and per-scene jump buttons (it needs a server, not `file://` —
Three.js ships ES modules and Chromium blocks those over `file://`).

## How it is made

Nothing here is stock. The characters and the set are built from primitives in
Three.js, the voices are synthesised with Piper, and the music, ambience and
animal noises are generated with numpy.

    script.json ──→ make_audio.py ──→ out/audio.wav
                                 └──→ out/timeline.json ──┬──→ web/ (the render)
                                                          └──→ make_subs.py

`script.json` is the source of truth: the cast, the dialogue, the staging and
the camera shot for every beat. `make_audio.py` speaks it, and writes a
timeline that carries the exact start time of every line plus the lip-sync
curves measured off the audio. The animation, the subtitles and the chapter
timestamps all read that one file, so they cannot drift apart.

| Path | What it does |
|---|---|
| `script.json` | Cast, dialogue, staging, camera shots |
| `render/make_audio.py` | Piper speech, pitch-shaped per character, music, mix, timeline |
| `render/voices.py` | The animal noises and birdsong, synthesised |
| `render/audition.py` | Picks the cast out of the 904-speaker LibriTTS model |
| `render/make_subs.py` | `.srt`, transcript, description with chapters |
| `web/rig.js` | Shared character machinery: eyes, blinks, mouths, materials |
| `web/species.js` | The six characters |
| `web/world.js` | Ground, hills, trees, pond, fence, sky and lighting presets |
| `web/director.js` | Camera, staging and per-frame animation state |
| `web/overlay.js` | Subtitles, title card, thumbnail treatment |
| `render/render_video.mjs` | Frames → ffmpeg → MP4 |

### Voices

The six characters come from one model — `en-us-libritts-high`, which carries
904 speakers. `audition.py` synthesises the same sentence across a sample of
them and measures median pitch, pitch stability, loudness and spectral
flatness, then picks the steadiest voice in each pitch band. That is how a
107 Hz lion and a 256 Hz mouse end up in the same episode. Each is then
pitch-shifted a little further apart to give it a cartoon register.

### Lip sync

Piper's alignment output is empty for this model, so the mouths are driven from
the audio itself. Every line yields two curves at frame rate: `open`, from
short-window loudness with a fast attack and slow release, and `wide`, from
spectral centroid — a bright "ee" spreads the mouth, a dark "oo" rounds it. The
renderer reads those curves, so the mouth cannot drift out of sync with what is
being said.

### Why it renders slowly

WebGL here runs on SwiftShader, in software. The surprise is that the cost is
not the rasteriser: reading each finished frame back out of the GL context
costs roughly a second regardless of resolution, triangle count, shadows or
material type — all of which were measured and none of which moved the number
much. Sharding across parallel browsers does not help either, because four
cores are already saturated. A 1080p24 render of this episode therefore takes
a couple of hours, and `--quick` exists for iterating.

## Requirements

    pip install piper-tts numpy imageio-ffmpeg
    npm install -g playwright     # plus a Chromium build

`build.sh` finds ffmpeg through `imageio-ffmpeg`. The voice models are fetched
by `render/fetch_voices.sh` and are not committed — they are about 200 MB.

## Licence and reuse

The code, characters, music and animation are original. Three.js is MIT
(`web/lib/three-LICENSE.txt`); the Piper voice models are MIT releases of the
Piper project; the two fonts are SIL Open Font License 1.1. All are free for
commercial use, including monetised video, and nothing in the render can pick
up a Content ID claim.

`youtube/UPLOAD.md` covers the upload settings and the platform rules that
apply to children's content.
