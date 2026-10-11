import os, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'backend'))
from models import Design, ProjectSave
import service


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old = os.environ.get('CHAMELEON_DB')
        os.environ['CHAMELEON_DB'] = str(Path(self.tmp.name) / 'r.sqlite3')
        self.design = Design.model_validate_json((ROOT / 'examples/coffee_ad.json').read_text())

    def tearDown(self):
        if self.old is None: os.environ.pop('CHAMELEON_DB', None)
        else: os.environ['CHAMELEON_DB'] = self.old
        self.tmp.cleanup()

    def test_projects_round_trip(self):
        """A campaign saved in the older studio format still saves, lists, reopens and deletes."""
        service.save_project('proj', ProjectSave(name='Spring', design=self.design.model_dump(), formats=[{'width': 1080, 'height': 1080, 'name': 'Square'}]))
        p = service.get_project('proj'); self.assertEqual(p['name'], 'Spring'); self.assertEqual(p['formats'][0]['name'], 'Square')
        self.assertEqual(service.list_projects()[0]['campaign'], 'proj')
        service.delete_project('proj')
        with self.assertRaises(LookupError): service.get_project('proj')

    def test_same_request_answers_from_memory(self):
        """Repeat /adapt requests come from the result memory and match a fresh run."""
        import json
        d = json.loads((service.TEMPLATE_DIR / 'snow_cabins.json').read_text())
        req = {'design': d, 'targets': [{'width': 300, 'height': 250}]}
        a = service.adapt_request(req); b = service.adapt_request(json.loads(json.dumps(req)))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        b['results'][0]['name'] = 'changed'          # a caller changing its copy doesn't touch the memory
        self.assertNotEqual(service.adapt_request(req)['results'][0]['name'], 'changed')


if __name__ == '__main__':
    unittest.main()
