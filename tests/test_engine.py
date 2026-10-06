import json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from models import Design
from engine.genome import enrich_design
from engine.generator import generate_candidates, ordered
from engine.repair import repair_candidate
from engine.scorer import score_candidate
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.design=enrich_design(Design.model_validate_json((ROOT/'examples/coffee_ad.json').read_text()))
    def test_presets_stay_in_bounds_without_critical_collisions(self):
        for w,h in [(1080,1920),(1080,1080),(1200,628),(728,90),(64,64)]:
            for candidate in generate_candidates(self.design,w,h):
                c=score_candidate(repair_candidate(candidate))
                self.assertFalse([v for v in c['violations'] if v['type'] in ('OUT_OF_BOUNDS','OVERLAP')],(w,h,c))
    def test_correction_changes_order(self):
        for candidate in generate_candidates(self.design,1080,1920,[{'source':'cta','target':'headline','relation':'ABOVE'}]):
            els={e.id:e for e in candidate['design'].elements}
            self.assertLessEqual(els['cta'].y+els['cta'].height,els['headline'].y)
    def test_cycle_rejected(self):
        with self.assertRaises(ValueError):
            ordered(self.design.elements,[{'source':'cta','target':'headline','relation':'ABOVE'},{'source':'headline','target':'cta','relation':'ABOVE'}])
    def test_invalid_designs_rejected(self):
        data=self.design.model_dump(); data['canvas']['width']=0
        with self.assertRaises(ValueError): Design.model_validate(data)
        data=self.design.model_dump();data['elements'][1]['id']=data['elements'][0]['id']
        with self.assertRaises(ValueError): Design.model_validate(data)
    def test_input_unchanged(self):
        before=self.design.model_dump()
        generate_candidates(self.design,728,90)
        self.assertEqual(before,self.design.model_dump())
if __name__=='__main__': unittest.main()
