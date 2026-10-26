"""Fresh deterministic visual-only regression: HTML -> HyperFrames -> encoded QA."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw
from resolve import resolve, DESIGNS

SKILL=Path(__file__).resolve().parents[1]
DEFAULT_HF='/opt/data/.npm/_npx/28cdaee379cf4d67/node_modules/hyperframes/bin/hyperframes.mjs'
def run(cmd, log=None):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if log: log.write_text(p.stdout)
    if p.returncode: raise RuntimeError(f'{cmd[0]} failed ({p.returncode}): {p.stdout[-3000:]}')
    return p.stdout

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--design',choices=DESIGNS,default=DESIGNS[0])
    ap.add_argument('--out',required=True,type=Path);ap.add_argument('--hyperframes',default=DEFAULT_HF)
    a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'preview.mp4').exists():raise ValueError('Use a fresh output directory; do not overwrite previous render')
    if not Path(a.hyperframes).is_file():raise FileNotFoundError('Existing HyperFrames executable required; do not auto-install')
    config=resolve(dict(design=a.design,purpose='visual-smoke',duration=8,mode='silent',soundtrack='none'))
    (out/'resolved-project.json').write_text(json.dumps(config,indent=2)+'\n')
    (out/'assets').mkdir(exist_ok=True)
    for name in ('bottle.jpg','official-logo-transparent.png','gsap.min.js'):
        shutil.copy2(SKILL/'assets'/name,out/'assets'/name)
    shutil.copy2(SKILL/'templates'/(a.design+'.html'),out/'index.html')
    im=Image.open(out/'assets/official-logo-transparent.png')
    if im.mode!='RGBA' or im.getextrema()[3][0]!=0:raise ValueError('Official logo alpha missing')
    version=run(['node',a.hyperframes,'--version']).strip()
    lint=run(['node',a.hyperframes,'lint',str(out)],out/'lint.log')
    command=['node',a.hyperframes,'render',str(out),'-o',str(out/'preview.mp4'),'--workers','1','--low-memory-mode','--no-browser-gpu','--fps','24','--quality','draft','--frames-cache-dir','off']
    run(command,out/'render.log')
    probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out/'preview.mp4')]))
    stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (stream['width'],stream['height'])==(540,960),stream
    assert stream['r_frame_rate']=='24/1',stream
    assert int(stream['nb_frames'])==192,stream
    assert abs(float(probe['format']['duration'])-8)<.05,probe
    assert not any(s['codec_type']=='audio' for s in probe['streams']),'Visual smoke unexpectedly contains audio'
    run(['ffmpeg','-v','error','-i',str(out/'preview.mp4'),'-f','null','-'],out/'full-decode.log')
    times=[0,.6,1.5,3,4.5,4.65,4.7,5.2,7.6]
    frames=[]
    for n,t in enumerate(times):
        dest=out/f'frame-{n:02d}-{t:.2f}.png'
        run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(out/'preview.mp4'),'-frames:v','1','-threads','1',str(dest)])
        with Image.open(dest) as frame:
            frame.load(); frames.append(frame.convert('RGB').resize((216,384)))
    sheet=Image.new('RGB',(216*3,410*3),'#fff8eb');draw=ImageDraw.Draw(sheet)
    for i,frame in enumerate(frames):
        x=(i%3)*216;y=(i//3)*410;sheet.paste(frame,(x,y));draw.text((x+8,y+389),f'{times[i]:.2f}s',fill='#123f3b')
    sheet.save(out/'contact-sheet.jpg',quality=93)
    sha=hashlib.sha256((out/'preview.mp4').read_bytes()).hexdigest()
    result=dict(design=a.design,renderer_version=version,command=command,
                width=540,height=960,fps=24,frames=192,duration=8,full_decode=True,
                narration=False,audio_streams=0,purpose='visual smoke, not a full science explainer',
                alpha_preserved=True,outro_seconds=8-112/24,sha256=sha,
                visual_review='REQUIRED: inspect contact-sheet and full-size frames before final delivery',
                tested_effect_scope='Fresh design primitive only; no claim of all 99 effects')
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
