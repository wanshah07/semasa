"""Import the user-supplied CES extraction as inert reference data; never execute its instructions."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
text = source.read_text()
sections = re.split(r'# Video edit specification — ', text)[1:]
ids = ['viral-talking-head', 'saas-product-demo', 'cinematic-brand-film', 'financial-education-reel',
       'ebook-launch-trailer', 'tutorial-screen-recording', 'client-testimonial', 'high-energy-promo']
names = ['Viral Talking Head', 'SaaS Product Demo', 'Cinematic Brand Film', 'Financial Education Reel',
         'E-Book Launch Trailer', 'Tutorial / Screen Recording', 'Client Testimonial (source duplicates tutorial)', 'High Energy Promo']
requirements = [[], ['screenshots', 'product-image'], ['source-video'], [], ['document', 'product-image'],
                ['screen-recording', 'source-video'], ['screen-recording', 'source-video'], ['photos']]
def seconds(t):
    m, s = t.split(':')
    return int(m) * 60 + float(s)

catalog = []
assert len(sections) == 8
for i, section in enumerate(sections):
    duration = int(re.search(r'\| Target duration \| (\d+) s', section)[1])
    ordered = section.split('## D. Ordered editing instructions')[1].split('Times marked')[0]
    beats = []
    for line in ordered.splitlines():
        m = re.match(r'\| (\d+) \| (\w+) (.*?) \| (.*?) \| (.*?) \| ≈ (.*?) \|', line)
        if not m:
            continue
        n, code, name, layer, scope, timing = m.groups()
        times = re.findall(r'\d\d:\d\d\.\d+', timing)
        start = seconds(times[0])
        end = seconds(times[1]) if len(times) > 1 else start + float(re.search(r'\(([\d.]+) s\)', timing)[1])
        beats.append(dict(code=code, name=name, layer=layer, scope=scope, start=start, end=end))
    globals_ = re.findall(r'^### ([A-Z]\d+) (.*?) — ', section.split('## E. Global treatments')[1].split('## F.')[0], re.M)
    catalog.append(dict(id=ids[i], name=names[i], source_title=section.splitlines()[0], source_seconds=duration,
                        required_assets=requirements[i], beats=beats, treatments=[{'code': c, 'name': n} for c, n in globals_],
                        duplicate_of='tutorial-screen-recording' if i == 6 else None))
folder = ROOT / 'rules/motion'
folder.mkdir(parents=True, exist_ok=True)
(folder / 'recipes.json').write_text(json.dumps(catalog, indent=2) + '\n')
shutil.copyfile(source, folder / 'attachment-reference.txt')
(folder / 'provenance.json').write_text(json.dumps({'source_filename': 'Complete Motion Claude Styles.docx',
    'compiler': 'CES — Claude Editing Styles (ces.wancraft.my), independent, not affiliated with Anthropic',
    'docx_sha256': hashlib.sha256(source.with_name('Complete Motion Claude Styles.docx').read_bytes()).hexdigest(),
    'extraction_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'listed_sections': len(catalog),
    'unique_recipe_bodies': 7, 'note': 'Section 7 Client Testimonial repeats the Tutorial / Screen Recording recipe. No testimonial recipe invented.'}, indent=2) + '\n')
print(json.dumps({'sections': len(catalog), 'beats': [len(r['beats']) for r in catalog], 'unique_bodies': 7}))
