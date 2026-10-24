"""Install this project's master skill without overwriting an existing skill."""
from pathlib import Path
import hashlib
import json
import os
import shutil

root = Path(__file__).resolve().parents[1]
source = root / 'skills/wechat-editorial-pipeline'
codex_dir = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
destination = codex_dir / 'skills/wechat-editorial-pipeline'
if destination.exists():
    raise SystemExit('目标技能已存在；未覆盖。先核对差异与用户更新范围。')
shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__'))
files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in destination.rglob('*') if p.is_file()}
receipt = {'installed_to': str(destination), 'source': str(source), 'files': files,
           'note': '八个题材技能和三个外部技能位于本项目.agents/skills；主技能在个人技能目录可发现。'}
(root / 'skill-install-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'installed_to': str(destination), 'file_count': len(files)}, ensure_ascii=False))
