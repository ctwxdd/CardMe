"""Fresh end-to-end rescue; reference hashes are read only after the engine exits."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--expected', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit('Benchmark requires a fresh output folder.')
args.output.mkdir(parents=True)
identity = lambda s: [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]
before = identity(args.image.stat())
root = Path(__file__).resolve().parents[1]
started = time.monotonic()
with (args.output / 'run.log').open('w') as log:
    process = subprocess.run([sys.executable, '-B', str(root / 'engine/carve-photos.py'),
                              '--image', str(args.image), '--output', str(args.output / 'photos')],
                             stdout=log, stderr=subprocess.STDOUT)
seconds = time.monotonic() - started
expected = json.loads(args.expected.read_text())
report_path = args.output / 'photos/pipeline-report.json'
report = json.loads(report_path.read_text()) if report_path.exists() else {}
actual = {str(row['offset']): row for row in report.get('photos', [])}
results = {}
for group, rows in expected.items():
    if not isinstance(rows, dict):
        continue
    matched, missing, different = [], [], []
    for offset, digest in rows.items():
        row = actual.get(str(offset))
        if row is None:
            missing.append(offset)
        elif hashlib.sha256(Path(row['output']).read_bytes()).hexdigest() == digest:
            matched.append(offset)
        else:
            different.append(offset)
    results[group] = {'expected': len(rows), 'matched': len(matched),
                      'missing': missing, 'different': different}
unchanged = identity(args.image.stat()) == before
passed = (process.returncode in (0, 2) and report.get('complete') and unchanged
          and all(not row['missing'] and not row['different'] for row in results.values()))
summary = {'benchmark_version': 1, 'seconds': seconds, 'engine_exit': process.returncode,
           'source_identity': before, 'source_unchanged': unchanged,
           'quality_counts': report.get('quality_counts'), 'results': results, 'passed': bool(passed)}
(args.output / 'benchmark.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
raise SystemExit(0 if passed else 1)
