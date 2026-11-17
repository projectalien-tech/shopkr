"""One test per code-review finding (v6.1.0)."""
import csv, io, time
from harness import *

with environment() as pg:
    E = pg.evaluate

    # ---------- formula-like pid, kept through a later purge (Code.gs re-applies the guard) ----------
    sidF = consent(pg, '=HYPERLINK("x")', 'control')
    check('setup: formula-like pid session synced', wait_until(lambda: session_row(sidF) is not None))

    # ---------- #1 withdrawal sticks, locally and on the server ----------
    sidW = consent(pg, 'W1', 'control')
    E("App.addToCart(1)"); nav(pg, 'cart'); nav(pg, 'home')
    check('#1 setup: full summary on server before withdrawal', wait_until(lambda: (session_row(sidW) or {}).get('pid') == 'W1'))
    E("App.endTask('researcher_ended')"); pg.wait_for_timeout(200)
    pg.click('.btn-sec >> text=Withdraw my data'); pg.click('.modal-actions .btn-danger'); pg.wait_for_timeout(300)
    wseq = E("state.seq")
    check('#1 in-memory shopping data cleared', E("state.cart.length === 0 && state.orders.length === 0 && Object.keys(state.seenImp).length === 0"))
    E("dispatchEvent(new Event('pagehide'))"); E("App.navigate('home')"); E("dispatchEvent(new Event('pagehide'))"); pg.wait_for_timeout(300)
    check('#1 shop data not rewritten after pagehide', E(f"localStorage.getItem('shopkr.shop.{sidW}') === null"))
    check('#1 local log holds only the withdrawal marker', E(f"JSON.parse(localStorage.getItem('shopkr.log.{sidW}')).map(e=>e.type).join()") == 'withdrawal')
    check('#1 nothing logged after withdrawal', E("state.seq") == wseq and E("state.queue.length") <= 1)
    check('#1 withdrawal reaches server', wait_until(lambda: (session_row(sidW) or {}).get('withdrawn') is True))
    row = session_row(sidW)
    check('#1 sessions row blanked on withdrawal (before purge)', row['pid'] == '' and row['orderCount'] == '' and row['condAssigned'] == '', {k: row[k] for k in ['pid', 'condAssigned', 'orderCount', 'withdrawn']})
    pg.wait_for_timeout(5600)
    check('#1 no events stored after the marker', all(r[6] <= wseq for r in events_for(sidW)), max(r[6] for r in events_for(sidW)))
    srv('/__purge')
    E("dispatchEvent(new Event('pagehide'))"); pg.wait_for_timeout(5600)
    check('#1 after purge + later pagehide: no events return', len(events_for(sidW)) == 0)
    check('#1 after purge + later pagehide: row stays blank', session_row(sidW)['pid'] == '' and session_row(sidW)['withdrawn'] is True)
    # an outdated client (v6.0.0) sending a full summary and new events for the withdrawn session
    out = srv_post({'v': 1, 'withdraw': False, 'session': {'sessionId': sidW, 'pid': 'W1', 'orderCount': 3, 'lastOrderTotal': 9999},
                    'events': [{'eventId': sidW + '-9999', 'sessionId': sidW, 'pid': 'W1', 'seq': 9999, 'type': 'navigate', 'detail': '{}'}]})
    check('#1 server ignores old-client data for a withdrawn session', out.get('ok') and out.get('appended') == 0 and session_row(sidW)['pid'] == '' and len(events_for(sidW)) == 0, out)

    # ---------- #2 purge takes the lock; rewritten rows keep the formula guard ----------
    locks = [l for l in dump()['lockLog'] if l[1] == 'purgeWithdrawn']
    check('#2 purgeWithdrawn acquires and releases the script lock', locks[:1] == [['acquire', 'purgeWithdrawn']] and locks[-1:] == [['release', 'purgeWithdrawn']], locks)
    check('#2 purge rewrite creates no formulas', dump()['formulas'] == [], dump()['formulas'][:2])
    check('#2 formula-like pid still stored as text after purge', any(str(r[3]) == "'=HYPERLINK(\"x\")" for r in events_for(sidF)))

    # ---------- #3a next participant's link opened while offline ----------
    srv('/__offline/on')
    sidO1 = consent(pg, 'O1', 'control')
    nav(pg, 'search'); nav(pg, 'cart'); nav(pg, 'home'); pg.wait_for_timeout(600)
    E("dispatchEvent(new Event('pagehide'))")
    q1 = E(f"JSON.parse(localStorage.getItem('shopkr.queue.{sidO1}')||'[]').map(e=>e.seq)")
    pg.goto(f'{APP}?design=search-x-drip-v1&pid=O2&cond=control'); pg.wait_for_timeout(400)
    check('#3a next participant on consent; O1 queue left on device', E("state.screen") == 'consent' and len(q1) > 3, len(q1))
    srv('/__offline/off')
    if not check('#3a O1 events delivered while O2 is still on consent', wait_until(lambda: {r[6] for r in events_for(sidO1)} >= set(q1), 15)):
        print('   DIAG', E("JSON.stringify({sids: storedQueueSids().map(x=>x.slice(0,8)+':'+(JSON.parse(localStorage.getItem('shopkr.queue.'+x)||'[]').length)), inF: ORPHANS.inFlight})"),
              'server seqs', sorted(r[6] for r in events_for(sidO1)), 'q1', q1, 'row', session_row(sidO1), flush=True)
    check('#3a O1 stored queue removed once delivered', wait_until(lambda: E(f"localStorage.getItem('shopkr.queue.{sidO1}') === null"), 8))
    check('#3a O1 session row uses its stored summary', (session_row(sidO1) or {}).get('pid') == 'O1')
    check('#3a nothing recorded for O2 before consent', E("Object.keys(localStorage).filter(k=>k.includes(state.session.sessionId)).length") == 0)

    # ---------- #3b New session while offline ----------
    sidR1 = consent(pg, 'R1', 'control')
    check('#3b setup synced', wait_until(lambda: len(events_for(sidR1)) >= 2))
    srv('/__offline/on')
    nav(pg, 'search'); nav(pg, 'my')
    pg.answers[:] = ['R2', 'control']
    E("App.resetSession()"); pg.wait_for_timeout(300)
    check('#3b new session on consent', E("state.screen") == 'consent' and E("state.session.pid") == 'R2')
    srv('/__offline/off')
    def r1_done():
        ev = events_for(sidR1); types = [r[11] for r in ev]; seqs = sorted(r[6] for r in ev)
        return 'session_end' in types and seqs == list(range(1, seqs[-1] + 1))
    check('#3b R1 session_end + all events delivered with no gaps', wait_until(r1_done, 15))
    ev = events_for(sidR1)
    se = next(r for r in ev if r[11] == 'session_end'); sx = [r for r in ev if r[11] == 'screen_exit' and '"my"' in str(r[13])]
    check('#3b screen_exit of the last screen saved before session_end', bool(sx) and sx[-1][6] < se[6])

    # ---------- #3c request in flight when the session changes ----------
    sidF1 = consent(pg, 'F1', 'control')
    check('#3c setup synced', wait_until(lambda: len(events_for(sidF1)) >= 2))
    srv('/__delay/2500')
    E("SYNC.inFlight = false; SYNC.nextAt = 0")
    nav(pg, 'search'); nav(pg, 'cart'); nav(pg, 'home')
    E("flushQueue('manual'); 0"); pg.wait_for_timeout(100)   # fire and forget: do not await the request
    check('#3c a request is in flight with F1\'s newest events', E("SYNC.inFlight") is True)
    pg.answers[:] = ['F2', 'control']
    E("App.resetSession()"); pg.wait_for_timeout(200)
    pg.check('#c-age'); pg.check('#c-agree'); pg.click('#c-accept'); pg.wait_for_timeout(150)
    sidF2 = E("state.session.sessionId")
    pg.click('.btn-primary >> text=Start shopping'); pg.wait_for_timeout(2200)
    srv('/__delay/0')
    def f2_complete():
        types = [r[11] for r in events_for(sidF2)]
        return 'consent_given' in types and 'session_start' in types and 'task_start' in types
    check('#3c F2 early events not trimmed by F1\'s late response', wait_until(f2_complete, 15), [r[11] for r in events_for(sidF2)][:5])
    check('#3c F1 events complete', wait_until(lambda: 'session_end' in [r[11] for r in events_for(sidF1)], 15))

    # ---------- #4 forced continuity: members not recorded as trial takers ----------
    sidM = consent(pg, 'M1', 'control')
    only(pg, 'forcedContinuity'); E("App.joinMembership('test')")
    E("App.buyNow(9)"); pg.wait_for_timeout(300)
    check('#4 trial not pre-selected for a member', E("state.checkout.trial") is None)
    E("App.placeOrder()"); pg.wait_for_timeout(200)
    op = E("state.logs.filter(e=>e.type==='order_placed').pop().detail")
    check('#4 member order: trial false, offer not shown', op.get('trial') is False and op.get('trialOfferShown') is False and op.get('trialPreselected') is False and op.get('trialChoice') is None, {k: op.get(k) for k in ['trial', 'trialOfferShown', 'trialPreselected', 'trialChoice']})
    check('#4 sessions trialKept FALSE for member', wait_until(lambda: (session_row(sidM) or {}).get('trialKept') is False))
    sidN = consent(pg, 'N1', 'control')
    only(pg, 'forcedContinuity'); E("App.buyNow(9)"); pg.wait_for_timeout(300); E("App.placeOrder()"); pg.wait_for_timeout(200)
    op = E("state.logs.filter(e=>e.type==='order_placed').pop().detail")
    check('#4 non-member order still records pre-selected trial', op.get('trial') is True and op.get('trialOfferShown') is True and op.get('trialPreselected') is True)

    # ---------- #5 back button from store home ----------
    sidB = consent(pg, 'B1', 'control')
    pg.go_back(); pg.wait_for_timeout(250)
    check('#5 back from store home stays in the store', E("state.screen") == 'home' and E("state.study.phase") == 'shopping')
    nav(pg, 'product', {'id': 3}); pg.go_back(); pg.wait_for_timeout(250); pg.go_back(); pg.wait_for_timeout(250); pg.go_back(); pg.wait_for_timeout(250)
    check('#5 repeated back never reaches the task brief', E("state.screen") == 'home')
    E("App.startTask()")
    check('#5 task_start logged exactly once', E("state.logs.filter(e=>e.type==='task_start').length") == 1)

    # ---------- #6 cart strikethrough under false discount ----------
    consent(pg, 'C1', 'control')
    only(pg, 'falseDiscount'); E("state.cart=[{id:2,qty:2},{id:9,qty:1}]; saveShop()"); nav(pg, 'cart')
    struck = pg.locator('.cart-item .list-price').all_inner_texts()
    exp = E("[fmt(dispList(prod(2))*2), fmt(dispList(prod(9)))]")
    item_total = E("fmt(computeTotals(state.cart,{}).list)")
    check('#6 struck prices use the false-discount reference', struck == exp, f'{struck} vs {exp}')
    check('#6 no price struck through next to itself', '₩10,960' not in struck)
    check('#6 struck prices add up to the cart item total', E("fmt(dispList(prod(2))*2 + dispList(prod(9)))") == item_total, item_total)

    # ---------- #7 CSV keeps negatives numeric ----------
    E("App.updateQty(2, -1)")
    E("App.openPanel(true)"); pg.wait_for_timeout(200)
    with pg.expect_download() as d: pg.click('.rp-btn >> text="Export CSV"')
    txt = open(d.value.path(), encoding='utf-8-sig').read()
    rows = list(csv.DictReader(io.StringIO(txt)))
    deltas = [r.get('detail.delta') for r in rows if r.get('type') == 'cart_qty_change']
    check('#7 negative delta exported as -1, not text', deltas and deltas[-1] == '-1', deltas)
    check('#7 text formula guard still applied', E("csvEscape('=SUM(A1)')") == "'=SUM(A1)" and E("csvEscape('-5 days')") == "'-5 days" and E("csvEscape(-1)") == '-1')
    E("App.openPanel(false)")

    check('no JS errors', not pg.errs, pg.errs[:3])
    check('no requests except the logging server', not pg.ext, pg.ext[:3])
summary()
