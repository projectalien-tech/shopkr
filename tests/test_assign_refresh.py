from harness import *
with environment() as pg:
    E = pg.evaluate
    srv('/__delay/3000')
    pg.goto(f'{APP}?design=search-x-drip-v1&pid=RR1'); pg.wait_for_timeout(300)
    pg.check('#c-age'); pg.check('#c-agree'); pg.click('#c-accept'); pg.wait_for_timeout(300)
    check('waiting screen shown while the server answers', E("state.screen") == 'assigning')
    sid = E("state.session.sessionId")
    pg.reload(); pg.wait_for_timeout(300)
    check('after refresh still waiting (no condition guessed)', E("state.screen") == 'assigning' and E("state.session.condAssigned") is None)
    srv('/__delay/0')
    check('reaches the task brief', wait_until(lambda: E("state.screen") == 'task', 12))
    rows = [r for r in (dump()['sheets'].get('assignments') or [])[1:] if r[0] == sid]
    check('exactly one assignment for the session; app uses it', len(rows) == 1 and rows[0][2] == E("state.session.condAssigned") and E("state.session.assignedBy") == 'server', rows)
    check('exactly one assignment + session_start event', E("state.logs.filter(e=>e.type==='assignment').length") == 1 and E("state.logs.filter(e=>e.type==='session_start').length") == 1)
    check('no JS errors', not pg.errs, pg.errs[:3])
summary()
