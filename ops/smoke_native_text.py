"""Local real HyperFrames smoke; requires existing CLI and GSAP (no downloads).

python3 ops/smoke_native_text.py --cli /path/to/hyperframes/dist/cli.js \
  --gsap /path/to/gsap.min.js --output /path/to/qa
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from semasa import motion_assets  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--gsap", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=Path, help="Optional actual browser motionRow payloads keyed by effect ID")
    args = parser.parse_args()
    rows = json.loads(args.rows.read_text()) if args.rows else {}
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    texts = {"H01": "Keep food safe", "H03": "Why read labels?", "V01": "Read the label", "V03": "Read labels"}
    for code, text in texts.items():
        folder = args.output / code
        folder.mkdir(exist_ok=True)
        shutil.copyfile(args.gsap, folder / "gsap.min.js")
        row = rows.get(code, {"options": {"effect_mode": "manual", "effects": [code]}})
        assert row["options"]["effects"] == [code] and row["options"]["effect_mode"] == "manual"
        report = motion_assets.prepare(row, folder)
        (folder / "input-row.json").write_text(json.dumps(row, indent=2))
        document = '''<!doctype html><html><head><meta charset="utf-8"><script src="gsap.min.js"></script>
<style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#e5f6ed}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#e5f6ed}
h1{position:absolute;top:18%;left:12%;width:76%;text-align:center;font:700 68px/1.2 system-ui;color:#143e35}
p{position:absolute;top:68%;left:12%;width:76%;text-align:center;font:36px system-ui;color:#143e35}</style></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="2" data-width="1080" data-height="1920">
<h1>TEXT</h1><p id="captions">Native text adaptation · local QA<br>Captions remain unchanged</p></div>
<script>window.__timelines={};const tl=gsap.timeline({paused:true});tl.to({}, {duration:2});window.__timelines.main=tl;</script></body></html>'''.replace("TEXT", text)
        out = motion_assets.inject(document, report, [{"id": "s1", "heading": text, "start": 0, "duration": 2}], 2)
        (folder / "index.html").write_text(out)
        (folder / "asset-plan.json").write_text(json.dumps(report, indent=2))
        assert report["effects"][0]["readiness"] == "ready"
        video = args.output / f"{code}.mp4"
        cmd = ["node", args.cli, "render", str(folder), "-o", str(video), "--fps", "12", "--workers", "1", "--low-memory-mode", "--no-best-effort", "--strict"]
        run = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (args.output / f"{code}-render.log").write_text(run.stdout)
        if run.returncode:
            raise RuntimeError(run.stdout)
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]))
        stream = probe["streams"][0]
        assert (stream["width"], stream["height"], stream["nb_frames"]) == (1080, 1920, "24")
        assert abs(float(probe["format"]["duration"]) - 2) < .01
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
        for timestamp in [.12, .6, 1.4]:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", str(args.output / f"{code}-{timestamp}.png")], check=True)
        results.append({"id": code, "video": str(video), "width": 1080, "height": 1920, "frames": 24, "fps": "12/1", "duration": 2, "decode": "passed", "effect": report["effects"][0]})
        (args.output / "render-results.json").write_text(json.dumps(results, indent=2))
    from PIL import Image, ImageDraw
    sheet = Image.new("RGB", (900, 4 * 575), "white")
    draw = ImageDraw.Draw(sheet)
    for row, code in enumerate(texts):
        for column, timestamp in enumerate([.12, .6, 1.4]):
            with Image.open(args.output / f"{code}-{timestamp}.png") as image:
                image.thumbnail((300, 535))
                sheet.paste(image, (column * 300, row * 575 + 30))
            draw.text((column * 300 + 10, row * 575 + 5), f"{code} @ {timestamp}s", fill="black")
    sheet.save(args.output / "contact-sheet.jpg")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
