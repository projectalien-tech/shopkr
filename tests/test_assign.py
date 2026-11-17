"""v6.2.0: 2x2 design cells and balanced server assignment."""
import json, uuid, time
from collections import Counter
from harness import *

CELLS = ['A0B0', 'A0B1', 'A1B0', 'A1B1']
def assign(sid, cells=CELLS, design='search-x-drip-v1'):
    return srv_post({'v': 1, 'action': 'assign', 'sessionId': sid, 'design': design, 'cells': cells})
def finish(sid, cell):   # what the app sends once the task has ended
    return srv_post({'v': 1, 'session': {'sessionId': sid, 'condAssigned': cell, 'taskEndAt': '2026-11-02T10:00:00Z', 'taskEndReason': 'order'}, 'events': []})
def assignments(design='search-x-drip-v1'):
    a = dump()['sheets'].get('assignments', [])
    return [dict(zip(a[0], r)) for r in a[1:] if r[1] == design] if a else []

with environment() as pg:
    E = pg.evaluate
    # ---------------- app: cells generated from CONFIG.DESIGN ----------------
    pg.goto(f'{APP}?design=search-x-drip-v1&pid=X0'); pg.wait_for_timeout(300)
    cells = E("JSON.stringify(Object.fromEntries(Object.entries(DESIGN_CELLS).map(([k,v])=>[k,v.patterns])))")
    check('cells generated from the design', json.loads(cells) == {'A0B0': [], 'A0B1': ['dripPricing'], 'A1B0': ['disguisedAds', 'sortPinning'], 'A1B1': ['disguisedAds', 'sortPinning', 'dripPricing']}, cells)
    check('cells added to presets; old presets kept', E("['A0B0','A1B1','control','ABC','ALL'].every(c => c in CONFIG.PRESETS)"))
    check('no condition before consent', E("state.session.condAssigned") is None and E("state.session.assignedBy") == 'pending')

    # ---------------- app: server assignment after consent ----------------
    sid = consent(pg, 'X1', '', start=False)
    check('consent → assigned → task brief', wait_until(lambda: E("state.screen") == 'task', 10))
    s = E("state.session")
    check('assigned by server to a design cell', s['assignedBy'] == 'server' and s['condAssigned'] in CELLS, s['condAssigned'])
    check('flags match the cell', set(E("activeKeys()")) == set(E(f"CONFIG.PRESETS['{s['condAssigned']}']")))
    types = E("state.logs.map(e=>e.type)")
    check('events in order: consent_given → assignment → session_start', types.index('consent_given') < types.index('assignment') < types.index('session_start') and types.count('session_start') == 1, types[:6])
    ss = E("state.logs.find(e=>e.type==='session_start').detail")
    check('session_start carries design + factor levels', ss['design'] == 'search-x-drip-v1' and ss['cell'] == s['condAssigned'] and ss['factorA'] in (0, 1) and ss['factorB'] in (0, 1))
    check('sessions row has design, factorA, factorB', wait_until(lambda: (session_row(sid) or {}).get('design') == 'search-x-drip-v1'))
    lv = E(f"cellLevels('{s['condAssigned']}')")
    check('sessions row factor levels match the cell', wait_until(lambda: (lambda r: r['factorA'] == lv['factorA'] and r['factorB'] == lv['factorB'] and r['assignedBy'] == 'server' and r['condAssigned'] == s['condAssigned'])(session_row(sid)), 10), {k: session_row(sid)[k] for k in ['condAssigned', 'factorA', 'factorB', 'assignedBy']})
    pg.reload(); pg.wait_for_timeout(400)
    check('refresh keeps the same cell', E("state.session.condAssigned") == s['condAssigned'] and E("state.screen") == 'task')
    check('server returns the same cell on retry', assign(sid).get('cell') == s['condAssigned'] and assign(sid).get('reused') is True)
    # declining never takes a slot
    n_before = len(assignments())
    pg.goto(f'{APP}?design=search-x-drip-v1&pid=X2'); pg.wait_for_timeout(300); pg.click('.btn-sec >> text=I do not want to take part'); pg.wait_for_timeout(800)
    check('declining creates no assignment', len(assignments()) == n_before)

    # ---------------- app: 11 more participants through the browser stay balanced ----------------
    for i in range(3, 14):
        consent(pg, f'X{i}', '', start=False); wait_until(lambda: E("state.screen") == 'task', 10)
    counts = Counter(a['cell'] for a in assignments())
    check('12 browser participants → 3 per cell', sorted(counts.values()) == [3, 3, 3, 3], dict(counts))

    # ---------------- app: pinned link and fallback ----------------
    consent(pg, 'XP', 'A1B1', start=False)
    check('?cond=A1B1 pins the cell without asking the server', E("state.session.assignedBy") == 'url' and E("activeKeys().join()") == 'disguisedAds,sortPinning,dripPricing' and E("state.screen") == 'task')
    srv('/__offline/on')
    consent(pg, 'XF', '', start=False)
    check('server unreachable → random fallback, still reaches task', wait_until(lambda: E("state.screen") == 'task', 12) and E("state.session.assignedBy") == 'random_fallback' and E("state.session.condAssigned") in CELLS)
    check('fallback recorded with the error', bool(E("state.logs.find(e=>e.type==='assignment').detail.error")))
    sidFB, cellFB = E("state.session.sessionId"), E("state.session.condAssigned")
    srv('/__offline/off')
    check('fallback cell recorded on the server once it is back', wait_until(lambda: any(a['sessionId'] == sidFB and a['cell'] == cellFB and a['assignedBy'] == 'random_fallback' for a in assignments()), 15))
    # the server assigned a cell the app never received (timed out) and the app used another: the tab follows the app
    sx = str(uuid.uuid4()); got = assign(sx)['cell']; other = next(c for c in CELLS if c != got)
    srv_post({'v': 1, 'session': {'sessionId': sx, 'design': 'search-x-drip-v1', 'condAssigned': other, 'assignedBy': 'random_fallback'}, 'events': []})
    check('assignments tab corrected to the cell actually used', [a['cell'] for a in assignments() if a['sessionId'] == sx] == [other])

    # ---------------- app: control-cell debrief ----------------
    consent(pg, 'XC', 'A0B0')
    E("App.endTask('researcher_ended')"); pg.wait_for_timeout(200)
    txt = pg.inner_text('.study'); items = E("[...document.querySelectorAll('.db-item b')].map(b=>b.textContent)")
    check('A0B0 debrief: comparison group + the design\'s 3 patterns', 'comparison group' in txt and len(items) == 3, items)

    # ---------------- server: balance under many simultaneous sign-ups ----------------
    D = 'stress-v1'
    for _ in range(40): assign(str(uuid.uuid4()), design=D)
    counts = Counter(a['cell'] for a in assignments(D))
    check('40 assignments → exactly 10 per cell', sorted(counts.values()) == [10, 10, 10, 10], dict(counts))
    first8 = [a['cell'] for a in assignments(D)][:8]
    check('every block of 4 contains each cell once', sorted(first8[:4]) == CELLS and sorted(first8[4:]) == CELLS, first8)
    check('order within blocks is random (not always the same)', len({tuple(first8[:4]), tuple(first8[4:8])}) >= 1)

    # ---------------- server: dropouts reopen their slot; withdrawals free it ----------------
    D2 = 'dropout-v1'
    srv('/__prop?k=assign_reservation_min&v=0.02')   # 1.2 s, for the test
    sids = [str(uuid.uuid4()) for _ in range(4)]
    got = {s_: assign(s_, design=D2)['cell'] for s_ in sids}
    dropout = sids[0]
    for s_ in sids[1:]: finish(s_, got[s_])
    time.sleep(1.5)
    nxt = assign(str(uuid.uuid4()), design=D2)['cell']
    check('an expired, unfinished slot goes to the next participant', nxt == got[dropout], f'dropout cell {got[dropout]}, next {nxt}')
    st = {a['sessionId']: a['status'] for a in assignments(D2)}
    check('finished participants marked complete', all(st[s_] == 'complete' for s_ in sids[1:]))
    srv('/__prop?k=assign_reservation_min&v=60')
    D3 = 'withdraw-v1'
    w = [str(uuid.uuid4()) for _ in range(4)]; gw = {s_: assign(s_, design=D3)['cell'] for s_ in w}
    srv_post({'v': 1, 'withdraw': True, 'session': {'sessionId': w[2], 'withdrawn': True}, 'events': []})
    check('a withdrawal frees its slot at once', assign(str(uuid.uuid4()), design=D3)['cell'] == gw[w[2]])
    check('changing the design id restarts balancing', Counter(a['cell'] for a in assignments('new-design')) == Counter() and assign(str(uuid.uuid4()), design='new-design')['ok'])
    check('invalid cell lists are refused', assign(str(uuid.uuid4()), cells=['only-one'])['ok'] is False)

    check('no JS errors', not pg.errs, pg.errs[:3])
    check('no requests except the logging server', not pg.ext, pg.ext[:3])

# ---------------- server: upgrading a v6.1 Sheet adds the new columns ----------------
with environment() as pg:
    srv('/__seed_old_sessions')
    sid = str(uuid.uuid4())
    srv_post({'v': 1, 'session': {'sessionId': sid, 'pid': 'NEW1', 'design': 'search-x-drip-v1', 'factorA': 1, 'factorB': 0}, 'events': []})
    head = dump()['sheets']['sessions'][0]
    check('old sessions header gains the new columns at the end, old ones in place', head[25:31] == ['lastSeq', 'firstSeen', 'lastUpdate', 'design', 'factorA', 'factorB'] and head[-1] == 'joinedAgainstInterest' and len(head) == 40, head[-4:])
    row = session_row(sid); old = session_row('00000000-0000-4000-8000-000000000000')
    check('new row filled; old row untouched', row['factorA'] == 1 and row['design'] == 'search-x-drip-v1' and old['pid'] == 'OLD1')
summary()
