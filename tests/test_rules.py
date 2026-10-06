import os, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'backend'))
from models import Design, Canvas, BatchRequest, LearnProposalRequest, ProjectSave
from engine.rules import parse_text, normalize
from engine.intent import infer_any
import service

FORMATS = [(1080, 1920), (1080, 1080), (1200, 628), (1584, 396), (320, 480), (728, 90)]


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old = os.environ.get('CHAMELEON_DB')
        os.environ['CHAMELEON_DB'] = str(Path(self.tmp.name) / 'r.sqlite3')
        self.design = Design.model_validate_json((ROOT / 'examples/coffee_ad.json').read_text())

    def tearDown(self):
        if self.old is None: os.environ.pop('CHAMELEON_DB', None)
        else: os.environ['CHAMELEON_DB'] = self.old
        self.tmp.cleanup()

    def batch(self, campaign='c'):
        req = BatchRequest(campaign=campaign, design=self.design, targets=[{'width': w, 'height': h} for w, h in FORMATS])
        return service.transform_batch(req)

    def test_parser_understands_common_phrasings(self):
        roles = ['logo', 'headline', 'offer', 'cta', 'hero']
        r = parse_text('Logo always top-left, never shrink the price; hide the offer on small banners and CTA below the offer', roles)
        types = [x['type'] for x in r['rules']]
        self.assertEqual(types, ['pin', 'emphasis', 'hide_small', 'order'])
        self.assertEqual(r['rules'][0]['params'], {'role': 'logo', 'corner': 'top-left'})
        self.assertEqual(r['rules'][2]['params'], {'role': 'offer', 'below': 200})
        self.assertEqual(r['rules'][3]['params'], {'source_role': 'cta', 'target_role': 'offer', 'relation': 'BELOW'})
        self.assertEqual(parse_text('center the headline', roles)['rules'][0]['params'], {'role': 'headline', 'align': 'center'})
        self.assertEqual(parse_text('make it pop', roles)['rules'], [])

    def test_pin_align_emphasis_hide_apply_in_every_format(self):
        service.add_rule('c', 'pin', {'role': 'logo', 'corner': 'top-right'})
        service.add_rule('c', 'align', {'role': 'cta', 'align': 'right'})
        service.add_rule('c', 'hide_small', {'role': 'offer', 'below': 400})
        service.add_rule('c', 'emphasis', {'role': 'cta', 'weight': 1.6})
        out = self.batch()
        for f in out['formats']:
            best = f['candidates'][0]
            w, h = f['target']['width'], f['target']['height']
            els = {e['id']: e for e in best['design']['elements']}
            for r in best['rule_results']:
                self.assertTrue(r['satisfied'], (w, h, r))
            self.assertEqual(els['offer']['hidden'], min(w, h) < 400)
            self.assertEqual(els['logo']['pinned'], 'top-right')
            self.assertGreater(els['logo']['x'] + els['logo']['width'], w * .85)
            self.assertFalse([v for v in best['violations'] if v['type'] in ('OUT_OF_BOUNDS', 'OVERLAP', 'MISSING_REQUIRED')], (w, h))

    def test_rule_crud_toggle_and_replace(self):
        a = service.add_rule('c', 'pin', {'role': 'logo', 'corner': 'top-left'})
        service.add_rule('c', 'pin', {'role': 'logo', 'corner': 'bottom-right'})
        rules = service.get_rules('c')
        self.assertEqual(len(rules), 1); self.assertEqual(rules[0]['params']['corner'], 'bottom-right')
        rid = rules[0]['id']
        self.assertFalse(service.set_enabled('c', rid, False)['enabled'])
        best = self.batch()['formats'][0]['candidates'][0]
        self.assertFalse(any(e['pinned'] for e in best['design']['elements']))
        service.delete_rule('c', rid); self.assertEqual(service.get_rules('c'), [])
        with self.assertRaises(ValueError): service.delete_rule('c', a['id'])
        with self.assertRaises(ValueError): normalize('pin', {'role': 'logo', 'corner': 'middle'})

    def test_learning_from_resize_hide_and_corner_drag(self):
        _, cs, _, _ = service.compile_design(self.design, Canvas(width=1080, height=1080), [])
        before = cs[0]['design']
        # resize the CTA
        after = before.model_copy(deep=True); cta = next(e for e in after.elements if e.id == 'cta')
        cta.width *= 1.5; cta.height *= 1.5
        p = infer_any(before, after, 'cta', 'resize')
        self.assertEqual(p[0]['type'], 'emphasis'); self.assertGreater(p[0]['params']['weight'], 1.3)
        saved = service.learn_proposal(LearnProposalRequest(before=before, after=after, moved_id='cta', kind='resize',
                                                            campaign='c', rule_type='emphasis', params=p[0]['params']))
        self.assertEqual(saved['learned']['type'], 'emphasis')
        # a client cannot save a rule the edit did not show
        with self.assertRaises(ValueError):
            service.learn_proposal(LearnProposalRequest(before=before, after=after, moved_id='cta', kind='resize',
                                                        campaign='c', rule_type='emphasis', params={'role': 'cta', 'weight': .5}))
        # hide the offer in this format
        after = before.model_copy(deep=True); off = next(e for e in after.elements if e.id == 'offer')
        off.hidden = True; off.width = off.height = 0
        p = infer_any(before, after, 'offer', 'hide')
        self.assertEqual(p[0]['params'], {'role': 'offer', 'below': 1081})
        # drag the logo into the bottom-right corner
        after = before.model_copy(deep=True); logo = next(e for e in after.elements if e.id == 'logo')
        logo.x = 1080 - logo.width - 20; logo.y = 1080 - logo.height - 20
        p = infer_any(before, after, 'logo', 'move')
        self.assertIn({'role': 'logo', 'corner': 'bottom-right'}, [x['params'] for x in p if x['type'] == 'pin'])

    def test_emphasis_is_actually_verified(self):
        from engine.rules import bind, check
        from engine.genome import enrich_design
        src = enrich_design(self.design.model_copy(deep=True))
        rule = {'id': 'x', 'type': 'emphasis', 'params': {'role': 'cta', 'weight': 1.6}, 'enabled': True}
        ctx, _ = bind(src, [rule])
        _, with_rule, _, _ = service.compile_design(self.design, Canvas(width=1080, height=1080), [rule])
        self.assertTrue(all(r['satisfied'] for r in with_rule[0]['rule_results']))
        _, without, _, _ = service.compile_design(self.design, Canvas(width=1080, height=1080), [])
        self.assertFalse(check(without[0]['design'], ctx)[0]['satisfied'])   # a layout that ignored the rule fails the check

    def test_all_templates_all_presets_are_clean(self):
        presets = [(1080, 1920), (1080, 1080), (1080, 1350), (1200, 628), (1600, 900), (1000, 1500), (1280, 720), (1584, 396),
                   (728, 90), (300, 250), (160, 600), (970, 250), (320, 480)]
        for name in ['coffee_ad', 'sneaker_drop', 'saas_webinar']:
            d = Design.model_validate_json((ROOT / 'examples' / f'{name}.json').read_text())
            for w, h in presets:
                _, cs, _, _ = service.compile_design(d, Canvas(width=w, height=h), [])
                bad = [v for v in cs[0]['violations'] if v['type'] in ('OVERLAP', 'OUT_OF_BOUNDS', 'MISSING_REQUIRED')]
                self.assertFalse(bad, (name, w, h, bad))

    def test_wide_banner_puts_cta_beside_text(self):
        _, cs, _, _ = service.compile_design(self.design, Canvas(width=1584, height=396), [])
        best = cs[0]; els = {e.id: e for e in best['design'].elements}
        self.assertEqual(best['strategy'], 'banner')
        self.assertGreater(els['cta'].x, els['headline'].x + els['headline'].width * .5)

    def test_projects_round_trip(self):
        service.save_project('proj', ProjectSave(name='Spring', design=self.design, formats=[{'width': 1080, 'height': 1080, 'name': 'Square'}]))
        p = service.get_project('proj'); self.assertEqual(p['name'], 'Spring'); self.assertEqual(p['formats'][0]['name'], 'Square')
        self.assertEqual(service.list_projects()[0]['campaign'], 'proj')
        service.delete_project('proj')
        with self.assertRaises(LookupError): service.get_project('proj')


if __name__ == '__main__':
    unittest.main()
