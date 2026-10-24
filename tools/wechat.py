"""Project entry point; the packaged skill is also usable independently."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / 'skills' / 'wechat-editorial-pipeline' / 'scripts' / 'pipeline.py'), run_name='__main__')
