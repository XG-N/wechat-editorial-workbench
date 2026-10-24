"""Package Git-tracked source files; excludes local untracked state."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
target = args.output.resolve()
if target.exists():
    raise SystemExit('ZIP already exists; not overwritten')
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
files = [name for name in tracked if name and (root / name).is_file()]
if not files:
    raise SystemExit('No tracked files. Inspect and git add the intended public files first.')
if any((root / name).resolve() == target for name in files):
    raise SystemExit('Output ZIP cannot also be an input')
manifest = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name in files:
        archive.write(root / name, name)
    archive.writestr('package-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert all(hashlib.sha256(archive.read(name)).hexdigest() == sha for name, sha in manifest.items())
print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'members': len(files)+1,
    'zip_crc': 'all_passed', 'member_sha256': 'all_passed'}, ensure_ascii=False, indent=2))
