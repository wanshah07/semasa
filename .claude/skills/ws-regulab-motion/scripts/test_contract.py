import json
from pathlib import Path
import unittest
import yaml
from resolve import resolve,DESIGNS

S=Path(__file__).resolve().parents[1]
class ContractTests(unittest.TestCase):
    def test_frontmatter(self):
        text=(S/'SKILL.md').read_text();self.assertTrue(text.startswith('---\n'))
        fm=yaml.safe_load(text.split('---',2)[1]);self.assertEqual(fm['name'],S.name)
        self.assertTrue(fm['user-invocable']);self.assertLessEqual(len(fm['description']),1024)
    def test_two_independent_designs(self):
        for design in DESIGNS:
            c=resolve({'design':design,'recipe':'Viral Talking Head','effects':['H01']})
            self.assertEqual(c['design'],design);self.assertEqual(c['recipe'],'Viral Talking Head')
            self.assertEqual(c['duration'],30);self.assertTrue((S/'templates'/(design+'.html')).is_file())
    def test_bm_and_personal_cta(self):
        self.assertEqual(resolve({'language':'ms-MY'})['cta'],'Jangan lupa follow kami untuk tips seterusnya.')
        c=resolve({'channel':'linkedin'});self.assertEqual(c['cta'],'Follow me for more')
        self.assertEqual(c['identity'],'Ts. ChM. Muhammad');self.assertIsNone(c['logo'])
    def test_explicit_gimmick(self):
        c=resolve({'mode':'gimmick','duration':10});self.assertEqual(c['outro_seconds'],0)
        self.assertEqual(c['cta'],'Stay tuned')
    def test_rejected_bad_defaults(self):
        for bad in ({'duration':10},{'mode':'gimmick','duration':30},{'mode':'gimmick','duration':10,'compositions':7},
                    {'placeholder_assets':True},{'slide_only':True},{'language':'id'},
                    {'diagram_kind':'quantitative'},{'outro_seconds':1},
                    {'soundtrack':'supplied-reel'},{'mode':'voice'},{'width':720}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):resolve(bad)
    def test_reel_private_only(self):
        c=resolve({'soundtrack':'supplied-reel','preview_only':True,'rights_status':'unverified'})
        self.assertTrue(c['preview_only'])
    def test_catalog_source_counts(self):
        c=json.loads((S/'references/catalog.json').read_text())
        self.assertEqual(c['occurrence_count'],len(c['occurrences']))
        self.assertEqual(c['unique_effect_count'],len(set(x['code'] for x in c['occurrences'])))
        self.assertEqual(c['unique_effect_count'],99);self.assertEqual(len(c['complete_recipes']),8)
        self.assertEqual(c['complete_recipes'][6]['body_title'],c['complete_recipes'][5]['body_title'])
    def test_templates_not_placeholder_slides(self):
        bright=(S/'templates/BrightPhotoDiagramEditorial.html').read_text()
        line=(S/'templates/ContinuousLine.html').read_text()
        self.assertIn('assets/bottle.jpg',bright);self.assertIn('id="relation"',bright)
        self.assertIn('getPointAtLength',line);self.assertIn("y:-365",line)
        for html in (bright,line):
            self.assertIn('official-logo-transparent.png',html);self.assertIn('Follow us for more',html)
            self.assertNotIn('Label Literacy',html)

if __name__=='__main__':unittest.main(verbosity=2)
