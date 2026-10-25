"""Build demo/taskworker-demo.mp4 (1280x720) from the real demo run.

Scenes use the genuine Playwright screenshots from runs/demo plus
PIL-rendered title/terminal cards. Narration via the system TTS (Helio).
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
WORK = DEMO / "work"
SHOTS = ROOT / "runs" / "demo" / "screenshots"
W, H = 1280, 720

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

BG = (13, 17, 23)
FG = (230, 237, 243)
MUTED = (154, 164, 181)
GREEN = (63, 185, 80)
BLUE = (88, 166, 255)
AMBER = (210, 153, 34)


def font(path, size):
    return ImageFont.truetype(path, size)


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("FAILED:", " ".join(cmd), "\n", r.stderr[-2000:])
        sys.exit(1)
    return r


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of",
               "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.stdout.strip())


def tts(text: str, out: Path):
    run(["/opt/hatch/bin/tts", "speak", "--voice", "Helio",
         "--text", text, "--output", str(out)])
    norm = out.with_suffix(".norm.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-af",
         "loudnorm=I=-16:TP=-1.5:LRA=11", str(norm)])
    return norm


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def title_card(title, subtitle, accent=GREEN):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=accent)
    d.text((80, 250), title, font=font(SANS_B, 84), fill=FG)
    for i, line in enumerate(wrap(d, subtitle, font(SANS, 34), W - 160)):
        d.text((80, 370 + i * 48), line, font=font(SANS, 34), fill=MUTED)
    return img


def terminal_card(lines, title=""):
    """lines: list of (text, color)."""
    img = Image.new("RGB", (W, H), (10, 12, 16))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 54], fill=(22, 27, 34))
    d.text((24, 12), title or "terminal", font=font(MONO_B, 22), fill=MUTED)
    y = 90
    for text, color in lines:
        for ln in wrap(d, text, font(MONO, 24), W - 80):
            d.text((40, y), ln, font=font(MONO, 24), fill=color)
            y += 38
        y += 8
    return img


def shot_scene(shot: Path, caption: str, badge: str):
    img = Image.open(shot).convert("RGB").resize((W, H))
    d = ImageDraw.Draw(img)
    # badge as a dark pill top-right (page content is centred, so the
    # corners are empty); never drawn over the page heading.
    bf = font(MONO_B, 20)
    tw = d.textlength(badge, font=bf)
    d.rounded_rectangle([W - tw - 48, 18, W - 20, 52], radius=17,
                        fill=(13, 17, 23))
    d.text((W - tw - 34, 24), badge, font=bf, fill=(255, 255, 255))
    d.rectangle([0, H - 118, W, H], fill=(13, 17, 23))
    d.rectangle([0, H - 118, W, H - 114], fill=GREEN)
    for i, line in enumerate(wrap(d, caption, font(SANS, 27), W - 56)):
        d.text((28, H - 100 + i * 36), line, font=font(SANS, 27), fill=FG)
    return img


SCENES = [
    # (kind, payload, narration)
    ("title", ("TaskWorker", "An autonomous AI worker. One sentence in — a finished job out."),
     "TaskWorker — an autonomous AI worker. Give it a task in plain English, and it does the job on a computer by itself."),
    ("terminal", ([("$ python -m taskworker run \\", MUTED),
                   ('  "Find the latest invoice from Acme Supplies Ltd,', FG),
                   ("   extract the amount and due date, enter it into", FG),
                   ("   our internal system, and tell me once it is done.\"", FG),
                   ("  --brain rule --auto-approve", GREEN)],
                  "the task — one sentence, no steps given"),
     "Here is the task: find the latest invoice from Acme Supplies Limited, extract the amount and due date, enter it into our internal system, and tell me once it is done. One sentence. No steps given."),
    ("shot", (SHOTS / "shot_01.png", "Opens the inbox in a real browser — and ignores the traps: a newer invoice from another vendor, and an older Acme invoice.", "STEPS 1–2 · INBOX"),
     "The agent opens the company inbox in a real browser. Notice the traps: a newer invoice from a different vendor, and an older invoice from the same vendor. It picks the right one — the latest from Acme."),
    ("shot", (SHOTS / "shot_02.png", "Opens the email, downloads the attached invoice PDF, and reads the document itself.", "STEP 3 · THE INVOICE"),
     "It opens the email, downloads the attached invoice PDF, and reads the document itself: invoice INV-2026-1042, four thousand eight hundred fifty dollars, due the nineteenth of November, twenty twenty-six."),
    ("shot", (SHOTS / "shot_03.png", "Opens the internal system and fills in the form — vendor, invoice number, amount, due date — then submits.", "STEPS 4–8 · ENTERING"),
     "Then it opens the internal system and fills in the form — vendor, invoice number, amount, due date — and submits."),
    ("shot", (SHOTS / "shot_04.png", "The record is in the system. The agent re-reads it and checks every field before calling the job done.", "STEP 9 · VERIFICATION"),
     "Here is the proof. The record is in the system. And the agent does not just trust the submit button — it re-reads the system and checks every field before calling the job done."),
    ("terminal", ([("Outcome: SUCCESS", GREEN),
                   ("Summary: Entered invoice INV-2026-1042 from Acme", FG),
                   ("  Supplies Ltd ($4,850.00, due 2026-11-19)", FG),
                   ("Verification: passed=True", GREEN),
                   ("Steps: 11  |  Report: runs/demo", MUTED)],
                  "the run report"),
     "Outcome: success. Eleven steps, verification passed. Every run leaves a full transcript, a summary, and screenshots as evidence."),
    ("title", ("TaskWorker", "A narrow prototype that genuinely works. Offline planner included; LLM brain for tasks nobody scripted."),
     "TaskWorker. A narrow prototype that genuinely works — with a planner that runs offline, and an LLM brain for tasks nobody scripted."),
]


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    frames, audios = [], []
    for i, (kind, payload, narration) in enumerate(SCENES):
        if kind == "title":
            img = title_card(*payload)
        elif kind == "terminal":
            lines, title = payload
            img = terminal_card(lines, title)
        else:
            img = shot_scene(*payload)
        frame = WORK / f"scene_{i:02d}.png"
        img.save(frame)
        frames.append(frame)
        audio = tts(narration, WORK / f"scene_{i:02d}.mp3")
        audios.append(audio)
        print(f"scene {i}: audio {duration(audio):.1f}s")

    # scene durations = audio + padding; 0.5s crossfades between scenes
    durs = [duration(a) + 0.9 for a in audios]
    print("durations:", [round(d, 1) for d in durs], "total ~",
          round(sum(durs) - 0.5 * (len(durs) - 1), 1), "s")

    # build filtergraph: loop each image, xfade chain, concat audio
    inputs = []
    for f, d in zip(frames, durs):
        inputs += ["-loop", "1", "-t", f"{d:.2f}", "-i", str(f)]
    for a in audios:
        inputs += ["-i", str(a)]
    n = len(frames)
    filt = []
    for i in range(n):
        filt.append(f"[{i}:v]format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
    offset = durs[0]
    prev = "v0"
    for i in range(1, n):
        out = f"xf{i}"
        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration=0.5:"
                    f"offset={offset - 0.5:.2f}[{out}]")
        prev = out
        offset += durs[i] - 0.5
    filt.append(f"[{prev}]format=yuv420p[vout]")
    audio_inputs = "".join(f"[{n + i}:a]" for i in range(n))
    filt.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")
    out_mp4 = DEMO / "taskworker-demo.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt),
         "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(out_mp4)])
    print("WROTE", out_mp4, out_mp4.stat().st_size // 1024, "KB,",
          f"{duration(out_mp4):.1f}s")
    print(json.dumps({"scenes": len(frames),
                      "durations": [round(d, 1) for d in durs]}, indent=1))


if __name__ == "__main__":
    main()
