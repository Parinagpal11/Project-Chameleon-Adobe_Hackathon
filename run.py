"""Start the local Chameleon app from the project folder."""
import runpy,sys
from pathlib import Path
backend=Path(__file__).resolve().parent/'backend'
sys.path.insert(0,str(backend))
runpy.run_path(str(backend/'local_server.py'),run_name='__main__')
