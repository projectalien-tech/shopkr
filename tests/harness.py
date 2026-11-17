"""Shared test harness: mock Apps Script server, browser, helpers."""
import json, subprocess, time, urllib.request, os
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                        # repository root: index.html, apps-script/Code.gs
APP = 'http://localhost:8766/index.html'            # a real origin, as on GitHub Pages
SRV = 'http://localhost:8765'
CHROME = os.environ.get('CHROME_PATH') or None      # unset = Playwright's own Chromium
results = []

def check(name, ok, info=''):
    results.append(bool(ok)); print(('PASS' if ok else 'FAIL'), name, ('' if info is None else info), flush=True)
    return ok

def srv(path):
    return json.loads(urllib.request.urlopen(SRV + path).read() or b'{}')

def srv_post(payload):
    req = urllib.request.Request(SRV + '/__post', data=json.dumps(payload).encode(), method='POST')
    return json.loads(urllib.request.urlopen(req).read())

def dump():
    return srv('/__dump')

def events_for(sid):
    ev = dump()['sheets'].get('events', [])
    return [r for r in ev[1:] if len(r) > 2 and r[2] == sid]

def session_row(sid):
    d = dump()['sheets'].get('sessions', [])
    if not d: return None
    head = d[0]
    for r in d[1:]:
        if r and r[0] == sid: return dict(zip(head, r))
    return None

def wait_until(fn, timeout=12, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        time.sleep(step)
    return False

@contextmanager
def environment(with_endpoint=True):
    proc = subprocess.Popen(['node', os.path.join(HERE, 'mock_server.js'), '8765', os.path.join(ROOT, 'apps-script', 'Code.gs')], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    web = subprocess.Popen(['python3', '-m', 'http.server', '8766', '--bind', '127.0.0.1', '--directory', ROOT], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    time.sleep(1.2)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            ctx = b.new_context(viewport={'width': 390, 'height': 844}, accept_downloads=True)
            if with_endpoint:
                ctx.add_init_script("try{ if(!localStorage.getItem('shopkr.device.endpoint')) localStorage.setItem('shopkr.device.endpoint', 'http://localhost:8765/exec'); }catch(e){}")
            pg = ctx.new_page()
            pg.errs, pg.ext, pg.answers = [], [], []
            pg.on('pageerror', lambda e: pg.errs.append(str(e)))
            pg.on('console', lambda m: pg.errs.append(m.text) if m.type == 'error' and 'net::' not in m.text and 'Failed to fetch' not in m.text else None)
            pg.on('request', lambda r: pg.ext.append(r.url) if not r.url.startswith(('file:', 'data:', 'blob:', 'http://localhost:8765', 'http://localhost:8766')) else None)
            def on_dialog(d):
                if d.type == 'confirm': d.accept()
                elif d.type == 'prompt': d.accept(pg.answers.pop(0) if pg.answers else '')
                else: d.dismiss()
            pg.on('dialog', on_dialog)
            yield pg
            b.close()
    finally:
        proc.terminate(); web.terminate()

DESIGN_2X2 = 'search-x-drip-v1'
def consent(pg, pid, cond, start=True, design=DESIGN_2X2):
    pg.goto(f'{APP}?pid={pid}' + (f'&cond={cond}' if cond else '') + (f'&design={design}' if design else '')); pg.wait_for_timeout(300)
    pg.check('#c-age'); pg.check('#c-agree'); pg.click('#c-accept'); pg.wait_for_timeout(150)
    if start:
        pg.click('.btn-primary >> text=Start shopping'); pg.wait_for_timeout(150)
    return pg.evaluate('state.session.sessionId')

def only(pg, *keys):
    pg.evaluate("keys => { state.flags = flagsForPreset('control'); keys.forEach(k => state.flags[k] = true); applyFlagDefaults(); render(); }", list(keys))

def nav(pg, screen, params=None):
    pg.evaluate("([s,p]) => App.navigate(s, p||{})", [screen, params]); pg.wait_for_timeout(120)

def summary():
    print(f'\n{sum(results)}/{len(results)} passed', flush=True)
