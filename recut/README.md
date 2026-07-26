# LMNOP split-screen recut

Rebuilds the LMNOP testimonial as a 9:16 split-screen ad:

- **Top panel** — Nautical Breeze foam being squeezed into the jar (visual only, muted)
- **Bottom panel** — the key spoken moments from the LMNOP testimonial, carrying the audio

Output is 1080×1920, 30fps, ~30s (the brief asked for 30–40s).

## Status: the edit runs, the timings are not yet confirmed

The render pipeline is built and tested end to end. What is **not** done is the
part that needs eyes on the footage.

This environment's egress policy blocks `video.xx.fbcdn.net` (and the rest of the
Meta/Instagram CDN, plus `drive.google.com`), so the two source videos could not be
downloaded, watched, or transcribed here. The consequence:

- Every `start`/`end` in `edl.json` is a **structural template** carrying a
  `needs_confirm: true` flag — a sensible testimonial arc (hook → problem →
  switch → proof → social proof), not a cut derived from what she actually says.
- The caption and end-card **copy is real**, lifted verbatim from the live
  creative for ad `120242679571800609`.

Before this ships, someone has to open the footage and replace the timings.

## Running it

Put the two sources here:

```
recut/src/lmnop.mp4    # Meta ad C_LMNOP_Testimonial_Jul, video_id 1522988409250178 (35.3s)
recut/src/foam.mp4     # Meta ad DG_NauticalBreeze_FluffFoam_Video, video_id 1545707373629821 (27.2s)
```

Then:

```bash
python3 recut.py --edl edl.json --out lmnop_split_30s.mp4 --preview   # fast, for checking timing
python3 recut.py --edl edl.json --out lmnop_split_30s.mp4             # final quality
python3 recut.py --edl edl.json --dry-run                             # print the ffmpeg command
```

`--preview` uses CRF 30 / veryfast so you can iterate on the cut in seconds, then
drop the flag for the CRF 19 delivery render.

### Requirements

ffmpeg with **libass**, **libx264** and **fontconfig**. Note this build has no
`drawtext` (it needs harfbuzz on ffmpeg 7.x), which is why all on-screen type —
captions *and* end card — goes through libass. If you run it somewhere with a
different ffmpeg, libass is the only hard dependency.

```bash
pip install imageio-ffmpeg   # ships a suitable static build
```

## Tuning the cut

Everything lives in `edl.json`.

| Field | What it does |
|---|---|
| `lmnop_segments[]` | Her beats. `start`/`end` are timestamps **in the source**; they concatenate in order and define the final runtime. |
| `foam_segments[]` | Foam beats for the top panel. The foam input is opened with `-stream_loop -1`, so a segment may run past 27.2s and it simply wraps. |
| `sources.*.crop_anchor` | Vertical bias when cropping to the panel. `0` keeps the top of frame, `0.5` centres, `1` keeps the bottom. **Set this first** — a naive centre crop on a vertical talking head tends to frame her torso instead of her face. Default `0.35`. |
| `layout.split` | Share of the canvas given to the top panel. `0.5` is the even split in the brief. |
| `caption_style.margin_bottom` | Distance from frame bottom, in px. `300` keeps captions clear of the Reels/TikTok UI. |
| `end_card` | Offer card over the final beat. Set `enabled: false` to drop it. |

Captions come from either `caption` (one line for the whole segment) or
`captions[]` (`t` / `t_end` offsets *relative to the segment start*) when a beat
needs more than one card.

## Why it is built this way

- **Her audio is the spine.** The foam panel is muted. It's a testimonial — the
  proof is what she says, and the foam is there to hold the eye while she says it.
- **Captions are burned in, not optional.** Most feed impressions are watched
  muted, so the spoken proof has to survive with the sound off.
- **Audio is normalised to −14 LUFS** (`loudnorm`), the level social platforms
  target, so it doesn't get turned down against other ads in the feed.
- **The seam is a deliberate 6px brand-gold rule.** Without it the join reads as a
  broken crop rather than a designed split.
- **The recut is shorter than the source** (30s from 35.3s). The point of the
  exercise is to cut the slack out of her delivery, not to reformat it at length.

## Checking a render

```bash
ffmpeg -i out.mp4 -vf "select='eq(n\,30)+eq(n\,300)+eq(n\,880)',scale=270:480,tile=3x1" -frames:v 1 sheet.png
```

Confirm: face framed in the bottom panel, the squeeze visible up top, captions
clear of the bottom UI, and the end card legible.
