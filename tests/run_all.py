"""Run every suite in order; exit 1 if any check fails."""
import subprocess, sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ['test_regression', 'test_fixes', 'test_assign', 'test_assign_refresh', 'test_membership', 'test_catalog']
failed = False
for s in SUITES:
    out = subprocess.run([sys.executable, os.path.join(HERE, s + '.py')], capture_output=True, text=True, cwd=HERE).stdout
    fails = [l for l in out.splitlines() if l.startswith('FAIL')]
    total = re.findall(r'(\d+)/(\d+) passed', out)
    print(f'{s}: {total[-1][0]}/{total[-1][1]} passed' if total else f'{s}: did not finish', flush=True)
    for l in fails: print('   ', l)
    failed |= bool(fails) or not total or total[-1][0] != total[-1][1]
sys.exit(1 if failed else 0)
