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
                d=api('/example');result=api('/transform','POST',{'design':d,'target':{'width':1080,'height':1920},'campaign':'demo'})
                before=result['best']['design'];after=json.loads(json.dumps(before));els={e['id']:e for e in after['elements']}
                els['offer']['y']=els['cta']['y']-els['offer']['height']-10
                edit={'before':before,'after':after,'moved_id':'offer'}
                self.assertTrue(api('/infer-edit','POST',edit)['proposals'])
                api('/learn-edit','POST',{**edit,'campaign':'demo','source_role':'offer','target_role':'cta','relation':'ABOVE'})
                result=api('/transform','POST',{'design':d,'target':{'width':1584,'height':396},'campaign':'demo'})
                self.assertTrue(result['best']['relationship_results'][0]['satisfied'])
                self.assertFalse(result['baseline']['relationship_results'][0]['satisfied'])
                self.assertEqual(len(api('/rules?campaign=demo')),1)
                self.assertEqual(api('/rules?campaign=other'),[])
                self.assertEqual(api('/benchmark')['cases'],96)
                for path in ['/','/assets/core.js','/assets/canvas.js','/assets/panels.js','/assets/dnd.js','/assets/tour.js','/assets/home.js','/assets/icons.js','/assets/app.css','/assets/tour.css','/assets/render.js','/assets/zip.js','/templates','/example?name=sneaker_drop']:
                    with opener.open(base+path) as response:self.assertEqual(response.status,200)
                with self.assertRaises(HTTPError):api('/transform','POST',{'design':{},'target':{'width':0,'height':0}})
                api('/rules?campaign=demo','DELETE');self.assertEqual(api('/rules?campaign=demo'),[])
            finally:
                server.shutdown();server.server_close();thread.join()
                if prev is None:os.environ.pop('CHAMELEON_DB',None)
                else:os.environ['CHAMELEON_DB']=prev
if __name__=='__main__':unittest.main()
