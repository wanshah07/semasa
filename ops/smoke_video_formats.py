"""Offline real-render smoke: authored silent 30s and single-composition 10s fixtures, no writer/TTS calls.

Requires existing --cli and --gsap files; never installs/downloads models or media.
This is renderer/preview proof, NOT an end-to-end voiced generation claim.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from semasa import motion, video_format_policy  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', required=True)
    parser.add_argument('--gsap', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for fmt in ['silent-first', 'gimmick']:
        row = video_format_policy.normalize({'voice':'off', 'options':{'format':fmt}})
        seconds = row['seconds']
        folder = args.output / fmt
        folder.mkdir(exist_ok=True)
        shutil.copyfile(args.gsap, folder / 'gsap.min.js')
        if fmt == 'gimmick':
            scenes = [{'id':'s1', 'start':0, 'duration':10,
                       'heading':'What does your packaging actually tell you? Stay tuned. Follow us for more.',
                       'narration':'', 'lines':[]}]
        else:
            texts = ['What does your packaging actually tell you?',
                     'A label gives information about the product.',
                     'That information helps you make a more informed choice.',
                     'Start by reading the packaging before you buy.']
            scenes = [{'id':f's{i+1}', 'heading':text, 'kicker':'', 'lines':[], 'narration':''}
                      for i,text in enumerate(texts)]
            scenes.append({'id':'brand-outro', 'heading':'Follow us for more', 'narration':'', 'lines':[]})
            scenes, _ = motion.fit_scenes(scenes, seconds)
        clips = ''.join(f'<div class="clip" id="{s["id"]}" data-start="{s["start"]}" '
                        f'data-duration="{s["duration"]}" style="position:absolute;left:12%;top:24%;width:76%;'
                        f'font:64px/1.4 system-ui;text-align:center;color:#143e35;">{s["heading"]}</div>'
                        for s in scenes if s['id'] != 'brand-outro')
        document = ('<!doctype html><html><head><script src="gsap.min.js"></script>'
                    '<style>html,body{margin:0;width:1080px;height:1920px;background:#e5f6ed;overflow:hidden}'
                    '#root{position:relative;width:1080px;height:1920px}</style></head><body>'
                    f'<div id="root" data-composition-id="main" data-start="0" data-duration="{seconds}" '
                    f'data-width="1080" data-height="1920">{clips}</div><script>window.__timelines={{}};'
                    f'const tl=gsap.timeline({{paused:true}});tl.to({{}},{{duration:{seconds}}});'
                    'window.__timelines.main=tl;</script></body></html>')
        motion.write_project(folder, motion.inject_layers(document, scenes, seconds, 1080, 1920, False), set())
        (folder / 'input-row.json').write_text(json.dumps(row, indent=2))
        video = folder / 'master.mp4'
        cmd = ['node', args.cli, 'render', str(folder), '-o', str(video), '--fps','12', '--workers','1',
               '--low-memory-mode', '--no-best-effort','--strict']
        run = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (folder / 'render.log').write_text(run.stdout)
        if run.returncode:
            raise RuntimeError(run.stdout[-4000:])
        mixed = motion.mix_music(video, scenes, seconds)
        preview = motion.make_preview(mixed)
        master_meta, preview_meta = motion.probe(mixed), motion.probe(preview)
        assert (master_meta['width'], master_meta['height']) == (1080,1920)
        assert (preview_meta['width'], preview_meta['height']) == (540,960)
        assert abs(master_meta['duration_s'] - seconds) < .1
        for path in [mixed, preview]:
            subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'], check=True)
        result = {'format':fmt, 'master':master_meta, 'preview':preview_meta, 'decode':'passed',
                  'scope':'authored offline renderer fixture; no writer, no narration synthesis'}
        results.append(result)
        (args.output / 'results.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
