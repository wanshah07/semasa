"""Recover original section labels/order, including duplicated featured entries, from DOCX."""
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def parse(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    groups = []
    titles = {'Hooks', 'Captions', 'Signature Effects', 'Motion Pace', 'Sound', 'Colour & Finish'}
    occurrence = 0
    for para in root.findall('.//w:body/w:p', ns):
        text = ''.join(t.text or '' for t in para.findall('.//w:t', ns)).strip()
        # Source headings are plain paragraphs, sometimes joined to numbered entry one.
        joined = re.match(r'^([A-Za-z &-]+?)1\. ', text)
        if joined:
            groups.append({'title': joined[1], 'ids': [], 'occurrences': []})
        elif text in titles:
            groups.append({'title': text, 'ids': [], 'occurrences': []})
        m = re.search(r'# CES style instruction — ([A-Z]\d{2})\b', text)
        if m:
            occurrence += 1
            groups[-1]['ids'].append(m[1])
            groups[-1]['occurrences'].append(occurrence)
    return groups


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    path = root / 'docs/motion/Styles.docx'
    groups = parse(path)
    out = {'source': 'docs/motion/Styles.docx', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'groups': groups}
    (root / 'rules/motion/effect-sections.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({g['title']: len(g['ids']) for g in groups}))
