"""Independent project-setting axes, with fail-closed style/rights checks."""
import argparse
import json
from pathlib import Path

DESIGNS = ('BrightPhotoDiagramEditorial', 'ContinuousLine')

def resolve(settings):
    c = dict(design=DESIGNS[0], recipe=None, effects=[], language='en', channel='ws',
             mode='silent', duration=30, width=540, height=960, fps=24,
             purpose='production', voice_gender=None, soundtrack='cleared-piano',
             rights_status='cleared', preview_only=False, placeholder_assets=False,
             slide_only=False, diagram_kind='qualitative', evidence=[], outro_seconds=3.3)
    c.update(settings)
    if c['design'] not in DESIGNS: raise ValueError('Unknown approved design')
    if c['language'] not in ('en', 'ms-MY'): raise ValueError('Use English or Malaysian Malay')
    if c['channel'] not in ('ws','linkedin'): raise ValueError('Unknown channel')
    if c['mode'] not in ('voice','silent','gimmick'): raise ValueError('Unknown narration mode')
    if c['purpose'] == 'visual-smoke':
        if c['duration'] != 8 or c['mode'] != 'silent': raise ValueError('Visual smoke is exactly 8s, no narration')
    elif c['purpose'] != 'production': raise ValueError('Unknown purpose')
    elif c['mode'] == 'gimmick':
        if c['duration'] != 10: raise ValueError('Explicit gimmick must be 10s')
        if c.get('compositions',1) != 1: raise ValueError('Gimmick is one persistent composition')
    elif c['duration'] not in (30,60): raise ValueError('Explainers must be 30s or 60s; 10s is gimmick only')
    if (c['width'],c['height']) not in ((540,960),(1080,1920)): raise ValueError('Expected native vertical preview/master')
    if c['placeholder_assets'] or c['slide_only']: raise ValueError('Rejected generic/slide-only draft')
    if c['diagram_kind'] == 'quantitative' and not c['evidence']: raise ValueError('Numeric marks require verified evidence')
    if c['soundtrack'] == 'supplied-reel' and not (c['preview_only'] and c['rights_status']=='unverified'):
        raise ValueError('Unverified reel audio is private-preview-only')
    if c['rights_status'] != 'cleared' and not c['preview_only']: raise ValueError('No uncleared public export')
    if c['mode'] == 'gimmick':
        c.update(cta='Stay tuned. Follow us for more',outro_seconds=0)
    elif c['channel'] == 'linkedin':
        c.update(cta='Follow me for more',identity='Ts. ChM. Muhammad',logo=None)
    else:
        c['cta'] = 'Follow us for more' if c['language']=='en' else 'Jangan lupa follow kami untuk tips seterusnya.'
        c['logo'] = 'official-logo-transparent.png'
    if c['mode'] != 'gimmick' and c['outro_seconds'] < 3.3: raise ValueError('Long outro needs >=3.3s')
    if c['mode'] == 'voice' and c['voice_gender'] not in ('male','female'):
        raise ValueError('Resolve voice gender/provider before synthesizing')
    return c

if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--design',choices=DESIGNS,default=DESIGNS[0]);ap.add_argument('--language',default='en')
    ap.add_argument('--mode',choices=('voice','silent','gimmick'),default='silent')
    ap.add_argument('--duration',type=int,default=30);ap.add_argument('--voice-gender',choices=('male','female'))
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();settings=vars(args).copy();out=settings.pop('output')
    resolved=resolve(settings);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(resolved,indent=2)+'\n');print(json.dumps(resolved,indent=2))
