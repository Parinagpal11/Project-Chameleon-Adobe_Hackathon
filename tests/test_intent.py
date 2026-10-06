import json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from models import Design,Canvas,LearnEditRequest,TransformRequest
from engine.intent import infer_edit
from service import compile_design,learn_edit,get_rules,transform,clear_rules,database,add_rule
from benchmark import run_benchmark

class IntentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=os.environ.get('CHAMELEON_DB');os.environ['CHAMELEON_DB']=str(Path(self.tmp.name)/'rules.sqlite3')
        self.design=Design.model_validate_json((ROOT/'examples/coffee_ad.json').read_text())
        _,cs,_,_=compile_design(self.design,Canvas(width=1080,height=1920),[])
        self.before=cs[0]['design'];self.after=self.before.model_copy(deep=True)
        els={e.id:e for e in self.after.elements};els['offer'].y=els['cta'].y-els['offer'].height-10
        self.req=LearnEditRequest(before=self.before,after=self.after,moved_id='offer',campaign='alpha',source_role='offer',target_role='cta',relation='ABOVE')
    def tearDown(self):
        if self.old is None:os.environ.pop('CHAMELEON_DB',None)
        else:os.environ['CHAMELEON_DB']=self.old
        self.tmp.cleanup()
    def test_actual_edit_infers_semantic_rule(self):
        p=infer_edit(self.before,self.after,'offer')
        self.assertTrue(any(r['source_role']=='offer' and r['target_role']=='cta' and r['relation']=='ABOVE' for r in p))
    def test_no_edit_does_not_invent_rule(self):
        self.assertEqual(infer_edit(self.before,self.before,'offer'),[])
        with self.assertRaises(ValueError):learn_edit(self.req.model_copy(update={'after':self.before}))
    def test_reject_multi_element_and_size_edits(self):
        altered=self.after.model_copy(deep=True);altered.elements[0].x+=20
        with self.assertRaises(ValueError):infer_edit(self.before,altered,'offer')
        altered=self.after.model_copy(deep=True);next(e for e in altered.elements if e.id=='offer').width+=20
        with self.assertRaises(ValueError):infer_edit(self.before,altered,'offer')
    def test_persist_and_transfer_across_formats_and_ids(self):
        learn_edit(self.req)
        self.assertEqual(len(get_rules('alpha')),1)
        renamed=self.design.model_copy(deep=True)
        for e in renamed.elements:e.id='new_'+e.id
        for w,h in [(1584,396),(320,480),(1200,628)]:
            r=transform(TransformRequest(design=renamed,target=Canvas(width=w,height=h),campaign='alpha'))
            for c in r['candidates']:
                self.assertTrue(c['relationship_results'][0]['satisfied'])
                self.assertEqual(c['metrics']['required_preserved'],c['metrics']['required_total'])
    def test_campaign_isolation_and_clear(self):
        learn_edit(self.req);self.assertEqual(get_rules('beta'),[])
        clear_rules('beta');self.assertEqual(len(get_rules('alpha')),1)
        clear_rules('alpha');self.assertEqual(get_rules('alpha'),[])
    def test_missing_role_is_explicitly_skipped(self):
        learn_edit(self.req);d=self.design.model_copy(deep=True);d.elements=[e for e in d.elements if e.id!='offer']
        r=transform(TransformRequest(design=d,target=Canvas(width=1200,height=628),campaign='alpha'))
        self.assertEqual(len(r['skipped_rules']),1)
    def test_cycle_rolls_back(self):
        # Preexisting CTA > headline > offer; adding offer > CTA must roll back.
        # Preexisting cta ABOVE headline ABOVE offer; offer ABOVE cta closes a loop.
        for s,t in [('cta','headline'),('headline','offer')]:
            add_rule('alpha','order',{'source_role':s,'target_role':t,'relation':'ABOVE'})
        with self.assertRaises(ValueError):learn_edit(self.req)
        self.assertEqual(len(get_rules('alpha')),2)
    def test_benchmark_has_held_out_transfer_and_shared_denominators(self):
        b=run_benchmark();self.assertEqual(b['cases'],96)
        totals=b['totals'];m=totals['chameleon_memory']
        self.assertEqual(m['relationships_preserved'],96)
        self.assertLess(totals['chameleon_no_memory']['relationships_preserved'],96)
        self.assertEqual(len({v['required_total'] for v in totals.values()}),1)
        self.assertEqual(len({v['relationships_total'] for v in totals.values()}),1)
if __name__=='__main__':unittest.main()
