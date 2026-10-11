import sys,json,threading,unittest,tempfile,os
from pathlib import Path
from urllib.request import Request,urlopen,build_opener,ProxyHandler
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from local_server import ThreadingHTTPServer,Handler
class HTTPTests(unittest.TestCase):
    def test_full_demo_over_http(self):
        with tempfile.TemporaryDirectory() as temp:
            prev=os.environ.get('CHAMELEON_DB');os.environ['CHAMELEON_DB']=str(Path(temp)/'db.sqlite3')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}';opener=build_opener(ProxyHandler({}))
            def api(path,method='GET',data=None):
                request=Request(base+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
                with opener.open(request,timeout=10) as response:return json.load(response)
            try:
                self.assertEqual(api('/health')['status'],'ok')
                for path in ['/','/assets/core.js','/assets/canvas.js','/assets/panels.js','/assets/dnd.js','/assets/tour.js','/assets/home.js','/assets/icons.js','/assets/app.css','/assets/tour.css','/assets/fonts.css','/assets/silk.js','/assets/zip.js','/assets/graph-render.js','/assets/studio-graph.js','/templates','/example?name=summer_sale']:
                    with opener.open(base+path) as response:self.assertEqual(response.status,200)
                with self.assertRaises(HTTPError):api('/adapt','POST',{'design':{},'targets':[{'width':0,'height':0}]})
                d=json.loads((ROOT/'examples'/'coffee_ad.json').read_text())
                # the Studio's path: a template (graph with a real photo) laid out by the engine, and a saved project
                tpls=api('/templates');self.assertGreaterEqual(len(tpls),3)
                g=api('/example?name='+tpls[0]['id']);self.assertIn('nodes',g)
                res=api('/adapt','POST',{'design':g,'targets':[{'width':1080,'height':1920,'name':'ig-story'},{'width':300,'height':250,'name':'mrec'}]})
                self.assertEqual([r['name'] for r in res['results']],['ig-story','mrec']);self.assertIn('roles',res)
                self.assertTrue(all(r['checks']['ok'] for r in res['results']))
                conv=api('/convert','POST',{'design':d})['design'];self.assertEqual(conv['format'],'chameleon-graph/1')
                api('/project?campaign=studio-test','PUT',{'name':'Snow','design':g,'state':{'overrides':{}}})
                self.assertEqual(api('/project?campaign=studio-test')['design']['nodes'][0]['id'],g['nodes'][0]['id'])
                with self.assertRaises(HTTPError):api('/project?campaign=studio-test','PUT',{'name':'Bad','design':{'nodes':'x'}})
                self.assertEqual(api('/projects')[0]['campaign'],'studio-test')
                api('/project?campaign=studio-test','DELETE');self.assertEqual(api('/projects'),[])
                for gone in ['/transform','/rules','/benchmark']:
                    with self.assertRaises(HTTPError):api(gone,'POST',{'design':g})
            finally:
                server.shutdown();server.server_close();thread.join()
                if prev is None:os.environ.pop('CHAMELEON_DB',None)
                else:os.environ['CHAMELEON_DB']=prev
if __name__=='__main__':unittest.main()
