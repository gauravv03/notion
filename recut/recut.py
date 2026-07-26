#!/usr/bin/env python3
"""
Split-screen recut builder for the Dirty Good LMNOP ad.

Top panel  : Nautical Breeze foam being squeezed into the jar (visual, muted)
Bottom panel: key spoken moments from the LMNOP testimonial (carries the audio)

The edit is driven entirely by an EDL (edit decision list) JSON file, so the
timings can be retuned without touching the render logic.

    python3 recut.py --edl edl.json --out lmnop_split_35s.mp4

See README.md for the workflow.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)


def ffmpeg_bin():
    for cand in ("ffmpeg", "/usr/local/bin/ffmpeg"):
        try:
            subprocess.run([cand, "-version"], capture_output=True, check=True)
            return cand
        except (OSError, subprocess.CalledProcessError):
            continue
    die("ffmpeg not found on PATH")


def probe_duration(ff, path):
    """Duration in seconds, read back off ffmpeg's stderr banner."""
    out = subprocess.run([ff, "-i", path], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            clock = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = clock.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return None


def fill_panel(label_in, label_out, w, h, anchor):
    """Scale-to-fill then crop a source to exactly w*h.

    anchor is the vertical bias of the crop: 0.0 keeps the top of frame,
    0.5 centres, 1.0 keeps the bottom. Talking heads usually want ~0.35 so
    the face survives the crop instead of the torso.
    """
    return (
        "[{i}]scale={w}:{h}:force_original_aspect_ratio=increase,"
        "crop={w}:{h}:(iw-{w})/2:(ih-{h})*{a},"
        "setsar=1,fps={fps}[{o}]".format(
            i=label_in, o=label_out, w=w, h=h, a=anchor, fps=FPS
        )
    )


# --------------------------------------------------------------------------
# captions
# --------------------------------------------------------------------------

def ass_time(t):
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def ass_color(value):
    """'0xF2C14E' / '#F2C14E' / 'white' -> ASS &HBBGGRR& literal.

    ASS orders colour bytes blue-green-red, the reverse of hex RGB.
    """
    named = {"white": "FFFFFF", "black": "000000"}
    s = str(value).strip().lower()
    s = named.get(s, s)
    s = s.replace("0x", "").replace("#", "")
    if len(s) != 6:
        return "&H00FFFFFF&"
    r, g, b = s[0:2], s[2:4], s[4:6]
    return "&H00%s%s%s&" % (b.upper(), g.upper(), r.upper())


def ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_ass(cues, style, path):
    """Write burned-in caption cues to an ASS file.

    Captions are non-negotiable for feed video: the overwhelming majority of
    impressions are watched muted, so her spoken proof has to survive with the
    sound off.
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(
        W=CANVAS_W,
        H=CANVAS_H,
        font=style.get("font", "Liberation Sans"),
        size=style.get("size", 62),
        outline=style.get("outline", 4),
        shadow=style.get("shadow", 2),
        ml=style.get("margin_l", 70),
        mr=style.get("margin_r", 70),
        mv=style.get("margin_bottom", 300),
    )

    lines = []
    for cue in cues:
        text = ass_escape(cue["text"]).replace("\n", "\\N")
        lines.append(
            "Dialogue: %d,%s,%s,Caption,,0,0,0,,%s%s"
            % (
                cue.get("layer", 0),
                ass_time(cue["start"]),
                ass_time(cue["end"]),
                cue.get("override", ""),
                text,
            )
        )

    with open(path, "w") as fh:
        fh.write(header + "\n".join(lines) + "\n")
    return path


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def build(edl, ff, out_path, workdir, preview=False):
    lmnop = edl["sources"]["lmnop"]
    foam = edl["sources"]["foam"]

    for p in (lmnop["path"], foam["path"]):
        if not os.path.exists(p):
            die("source not found: %s\n"
                "       Put the two source files in place (see README.md) and re-run." % p)

    layout = edl.get("layout", {})
    split = float(layout.get("split", 0.5))          # share of height given to the top panel
    top_h = int(round(CANVAS_H * split / 2) * 2)     # keep both panels even-numbered
    bot_h = CANVAS_H - top_h

    seam = layout.get("seam", {})
    seam_h = int(seam.get("height", 6))
    seam_color = seam.get("color", "0xF2C14E")

    lm_segments = edl["lmnop_segments"]
    foam_segments = edl["foam_segments"]
    if not lm_segments:
        die("edl.lmnop_segments is empty")
    if not foam_segments:
        die("edl.foam_segments is empty")

    total = sum(s["end"] - s["start"] for s in lm_segments)

    # ---- validate against the real sources -------------------------------
    lm_dur = probe_duration(ff, lmnop["path"])
    foam_dur = probe_duration(ff, foam["path"])
    if lm_dur:
        for s in lm_segments:
            if s["end"] > lm_dur + 0.05:
                die("lmnop segment %.2f-%.2f runs past the source (%.2fs)"
                    % (s["start"], s["end"], lm_dur))
    if foam_dur:
        for s in foam_segments:
            if s["end"] - s["start"] > foam_dur * 20:
                die("foam segment %.2f-%.2f is implausibly long" % (s["start"], s["end"]))

    parts = []
    lm_v, lm_a = [], []

    # ---- bottom panel: her key moments, carrying the audio ---------------
    for i, seg in enumerate(lm_segments):
        parts.append(
            "[0:v]trim=start=%f:end=%f,setpts=PTS-STARTPTS[lv%d]"
            % (seg["start"], seg["end"], i)
        )
        parts.append(
            "[0:a]atrim=start=%f:end=%f,asetpts=PTS-STARTPTS[la%d]"
            % (seg["start"], seg["end"], i)
        )
        lm_v.append("[lv%d]" % i)
        lm_a.append("[la%d]" % i)

    # concat wants its inputs interleaved per segment -- v0,a0,v1,a1,... --
    # not every video stream followed by every audio stream.
    interleaved = "".join(v + a for v, a in zip(lm_v, lm_a))
    parts.append(
        "%sconcat=n=%d:v=1:a=1[lvcat][acat]" % (interleaved, len(lm_segments))
    )
    parts.append(fill_panel("lvcat", "bottom", CANVAS_W, bot_h,
                            lmnop.get("crop_anchor", 0.35)))

    # ---- top panel: the foam squeeze, muted ------------------------------
    # The foam input is opened with -stream_loop -1, so segments may run past
    # the clip's natural length and it simply wraps.
    foam_v = []
    for j, seg in enumerate(foam_segments):
        parts.append(
            "[1:v]trim=start=%f:end=%f,setpts=PTS-STARTPTS[fv%d]"
            % (seg["start"], seg["end"], j)
        )
        foam_v.append("[fv%d]" % j)

    parts.append("%sconcat=n=%d:v=1:a=0[fvcat]" % ("".join(foam_v), len(foam_segments)))
    # Trim/pad the foam strip to exactly match the spoken track.
    parts.append(
        "[fvcat]trim=start=0:end=%f,setpts=PTS-STARTPTS,"
        "tpad=stop_mode=clone:stop_duration=%f[fvfit]" % (total, total)
    )
    parts.append(fill_panel("fvfit", "top", CANVAS_W, top_h,
                            foam.get("crop_anchor", 0.5)))

    # ---- stack + seam ----------------------------------------------------
    parts.append("[top][bottom]vstack=inputs=2[stacked]")
    parts.append(
        "[stacked]drawbox=x=0:y=%d:w=%d:h=%d:color=%s@1.0:t=fill[seamed]"
        % (top_h - seam_h // 2, CANVAS_W, seam_h, seam_color)
    )

    last = "seamed"

    # ---- end card scrim --------------------------------------------------
    # This build of ffmpeg has no drawtext (it needs harfbuzz in 7.x), so the
    # scrim is drawn with drawbox and the type is rendered through libass
    # alongside the captions -- which keeps the typography consistent anyway.
    end = edl.get("end_card")
    end_cues = []
    if end and end.get("enabled", True):
        e_start = max(0.0, total - float(end.get("duration", 3.5)))
        parts.append(
            "[%s]drawbox=x=0:y=0:w=%d:h=%d:color=black@%s:t=fill:enable='gte(t,%f)'[scrim]"
            % (last, CANVAS_W, CANVAS_H, end.get("scrim_opacity", "0.55"), e_start)
        )
        last = "scrim"
        for k, line in enumerate(end.get("lines", [])):
            end_cues.append({
                "start": e_start,
                "end": total,
                "text": line["text"],
                "layer": 1,
                "override": "{\\an5\\pos(%d,%d)\\fs%d\\c%s\\bord4\\shad2}" % (
                    CANVAS_W // 2,
                    line.get("y", 780 + k * 100),
                    line.get("size", 64),
                    ass_color(line.get("color", "white")),
                ),
            })

    # ---- captions --------------------------------------------------------
    cues = []
    clock = 0.0
    for seg in lm_segments:
        seg_len = seg["end"] - seg["start"]
        if seg.get("captions"):
            for c in seg["captions"]:
                cues.append({
                    "start": clock + c.get("t", 0.0),
                    "end": clock + c.get("t_end", seg_len),
                    "text": c["text"],
                })
        elif seg.get("caption"):
            cues.append({
                "start": clock + 0.05,
                "end": clock + seg_len - 0.05,
                "text": seg["caption"],
            })
        clock += seg_len

    # Don't let a spoken caption run underneath the end card.
    if end_cues:
        card_start = end_cues[0]["start"]
        cues = [c for c in cues if c["start"] < card_start]
        for c in cues:
            c["end"] = min(c["end"], card_start)
        cues.extend(end_cues)

    if cues:
        ass_path = os.path.join(workdir, "captions.ass")
        build_ass(cues, edl.get("caption_style", {}), ass_path)
        parts.append("[%s]ass=%s[vout]" % (last, ass_path.replace("\\", "/")))
        last = "vout"
    else:
        parts.append("[%s]null[vout]" % last)
        last = "vout"

    # ---- audio: her voice only, normalised for feed ----------------------
    parts.append("[acat]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    graph = ";".join(parts)
    graph_path = os.path.join(workdir, "filtergraph.txt")
    with open(graph_path, "w") as fh:
        fh.write(graph)

    cmd = [
        ff, "-y",
        "-i", lmnop["path"],
        "-stream_loop", "-1", "-i", foam["path"],
        "-filter_complex_script", graph_path,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "veryfast" if preview else "slow",
        "-crf", "30" if preview else "19",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-t", "%f" % total,
        out_path,
    ]
    return cmd, total, top_h, bot_h


def main():
    ap = argparse.ArgumentParser(description="Build the LMNOP split-screen recut.")
    ap.add_argument("--edl", default=os.path.join(os.path.dirname(__file__), "edl.json"))
    ap.add_argument("--out", default="lmnop_split.mp4")
    ap.add_argument("--preview", action="store_true",
                    help="fast low-quality render for checking timing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the ffmpeg command without running it")
    args = ap.parse_args()

    ff = ffmpeg_bin()
    with open(args.edl) as fh:
        edl = json.load(fh)

    workdir = os.path.join(os.path.dirname(os.path.abspath(args.out)) or ".", ".recut_work")
    os.makedirs(workdir, exist_ok=True)

    cmd, total, top_h, bot_h = build(edl, ff, args.out, workdir, preview=args.preview)

    print("canvas   : %dx%d @ %dfps" % (CANVAS_W, CANVAS_H, FPS))
    print("panels   : top %dpx (foam) / bottom %dpx (LMNOP)" % (top_h, bot_h))
    print("duration : %.2fs" % total)

    if args.dry_run:
        print("\n" + " ".join(shlex.quote(c) for c in cmd))
        return

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:] + "\n")
        die("ffmpeg failed")

    size = os.path.getsize(args.out)
    print("wrote    : %s (%.1f MB)" % (args.out, size / 1e6))


if __name__ == "__main__":
    main()
