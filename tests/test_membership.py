"""v6.3.0: membership study (default design) — paid ShopKR+, Fresh, nagging with 7-day escape."""
from harness import *

def first_product_offer(pg, pid_):
    """Open a product; return True if the ShopKR+ offer pop-up is showing."""
    nav(pg, 'product', {'id': pid_}); pg.wait_for_timeout(100)
    return pg.locator('.modal-card:has-text("ShopKR+")').count() == 1
def choose(pg, text):
    if text == 'escape': pg.click('.modal-link'); return
    pg.click(f'.modal-actions .btn >> text="{text}"'); pg.wait_for_timeout(100)

with environment() as pg:
    E = pg.evaluate
    # ---------- default link opens the membership study ----------
    pg.goto(f'{APP}?pid=M0'); pg.wait_for_timeout(300)
    check('plain link → membership design; cells A0/A1', E("CONFIG.DESIGN.id") == 'membership-nag-v1' and E("CONFIG.ASSIGNABLE_CONDITIONS") == ['A0', 'A1'])
    check('A1 = #23 only; A0 = nothing', E("CONFIG.PRESETS.A1") == ['membershipNagging'] and E("CONFIG.PRESETS.A0") == [])
    check('#23 registered as regulated nagging', E("(p => p.n === 23 && p.regulated && p.grayType.includes('Nagging'))(PATTERNS.find(p => p.key === 'membershipNagging'))"))

    # ---------- server assigns A0/A1 ----------
    sid = consent(pg, 'M1', '', start=False, design=None)
    check('server assigns a membership cell', wait_until(lambda: E("state.screen") == 'task', 10) and E("state.session.condAssigned") in ('A0', 'A1') and E("state.session.assignedBy") == 'server')

    # ---------- control A0: one offer, never repeats ----------
    consent(pg, 'C0', 'A0', design=None)
    check('A0: offer at first product view', first_product_offer(pg, 3))
    check('A0: first offer has no escape button', pg.locator('.modal-link').count() == 0)
    choose(pg, 'Not now')
    repeats = sum(first_product_offer(pg, i) for i in [4, 5, 11, 12, 13, 21])
    nav(pg, 'cart'); repeats += pg.locator('.modal-card').count()
    check('A0: after "Not now" the offer never returns (6 products + cart)', repeats == 0, repeats)
    check('A0: logs one offer and one decline', E("state.nag.shows") == 1 and E("state.nag.declines") == 1)

    # ---------- treatment A1: repeats with escape ----------
    consent(pg, 'N1', 'A1', design=None)
    check('A1: same first offer, no escape', first_product_offer(pg, 3) and pg.locator('.modal-link').count() == 0)
    choose(pg, 'Not now')
    check('A1: no repeat on the very next product', not first_product_offer(pg, 4))
    check('A1: repeat after 2 product views', first_product_offer(pg, 5))
    check('A1: repeat offers "Don\'t show again for 7 days"', pg.locator('.modal-link:has-text("7 days")').count() == 1)
    choose(pg, 'Not now')
    nav(pg, 'product', {'id': 11}); 
    nav(pg, 'cart'); pg.wait_for_timeout(100)
    check('A1: repeat when the cart opens', pg.locator('.modal-card:has-text("ShopKR+")').count() == 1)
    choose(pg, 'escape'); pg.wait_for_timeout(100)
    more = sum(first_product_offer(pg, i) for i in [12, 13, 14, 15, 21, 22])
    nav(pg, 'cart'); more += pg.locator('.modal-card').count()
    check('A1: escape stops all further offers', more == 0 and E("state.nag.escapes") == 1, more)
    pg.reload(); pg.wait_for_timeout(300)
    check('A1: escape survives a refresh', not first_product_offer(pg, 23) and not first_product_offer(pg, 24) and not first_product_offer(pg, 25))
    imp = E("state.logs.filter(e => e.type === 'dark_pattern_impression' && e.detail.pattern === 'membershipNagging').length")
    check('A1: only repeats count as #23 impressions', imp == 2, imp)

    # ---------- cap at MAX_SHOWS ----------
    consent(pg, 'N2', 'A1', design=None)
    shows = 0
    for i in range(1, 30):
        if first_product_offer(pg, (i % 40) + 1):
            shows += 1; choose(pg, 'Not now')
    check('A1: never more than 6 offers in all', shows == 6 and E("state.nag.shows") == 6, shows)

    # ---------- joining: paid, charged once, no more offers ----------
    consent(pg, 'J1', 'A1', design=None)
    first_product_offer(pg, 3); choose(pg, 'Not now'); first_product_offer(pg, 4); first_product_offer(pg, 5)
    choose(pg, 'Join for ₩4,990'); pg.wait_for_timeout(200)
    check('join from a repeat: member, ₩4,990 charged, via offer_2', E("state.membership.active") and E("state.memberFees") == 4990 and E("state.nag.joinedVia") == 'offer_2')
    check('no offers once a member', not first_product_offer(pg, 6) and not first_product_offer(pg, 7) and not first_product_offer(pg, 8))

    # ---------- Fresh: visible, gated, same in both conditions ----------
    for cell in ['A0', 'A1']:
        consent(pg, 'F' + cell, cell, design=None)
        E("state.nag.shows = 1; state.nag.declines = 1; state.nag.escapedUntil = Date.now() + 864e5; saveShop()")   # get the first offer out of the way
        E("state.category='fresh'; state.query=''; App.navigate('search')"); pg.wait_for_timeout(200)
        n_fresh = pg.locator('#search-results .card').count()
        badge = pg.locator('#search-results .badge.members').count()
        nav(pg, 'product', {'id': 41})
        pg.click('.action-bar .btn-outline'); pg.wait_for_timeout(150)
        gate = pg.locator('.modal-card:has-text("ShopKR Fresh is for members")').count()
        choose(pg, 'Not now')
        check(f'{cell}: Fresh visible with "ShopKR+ only"; non-member gets the members-only prompt, cart unchanged', n_fresh == 8 and badge == 8 and gate == 1 and E("state.cart.length") == 0)
    pg.click('.action-bar .btn-outline'); pg.wait_for_timeout(150); choose(pg, 'Join for ₩4,990'); pg.wait_for_timeout(200)
    check('joining from the prompt adds the item it was for', E("state.membership.active") and E("state.cart.map(i=>i.id)") == [41] and E("state.nag.joinedVia") == 'fresh_gate')
    E("state.cart.push({id:7, qty:1}); saveShop()"); nav(pg, 'cart'); pg.click('#bottomnav .btn'); pg.wait_for_timeout(1700); pg.click('#pay-btn'); pg.wait_for_timeout(300)
    o = E("state.orders[0]")
    check('member order: free shipping, Fresh pork saving counted', o['totals']['shipping'] == 0 and o['memberSavings']['fresh'] == 2000, o['memberSavings'])
    pg.click('.done .btn-primary'); pg.wait_for_timeout(300)
    s = E("sessionSummary()")
    check('summary: fee + order in totalSpent; benefit; against-interest flag', s['membershipFees'] == 4990 and s['totalSpent'] == 4990 + o['totals']['total'] and s['memberBenefit'] == 2000 and s['joinedAgainstInterest'] is True, {k: s[k] for k in ['membershipFees', 'totalSpent', 'memberBenefit', 'joinedAgainstInterest', 'joinedVia', 'gatePrompts']})
    items = E("[...document.querySelectorAll('.db-item b')].map(b=>b.textContent)")
    check('A1 debrief lists #23 with the 7-day sentence', items == ['Membership offer repeats after "Not now"'] and '7 days' in pg.inner_text('.study'))

    # ---------- the task can be finished without joining ----------
    consent(pg, 'T0', 'A1', design=None)
    first_product_offer(pg, 9); choose(pg, 'Not now')
    E("state.cart = [{id:9,qty:1},{id:1,qty:1},{id:7,qty:1}]; saveShop()")   # eggs, ramen, gochujang
    nav(pg, 'cart'); pg.wait_for_timeout(100)
    if pg.locator('.modal-card').count(): choose(pg, 'Not now')
    pg.click('#bottomnav .btn'); pg.wait_for_timeout(1700); pg.click('#pay-btn'); pg.wait_for_timeout(300)
    check('protein + staple + seasoning without joining, within ₩30,000', E("state.screen") == 'orderDone' and not E("state.membership.active") and E("totalSpent()") <= 30000, E("totalSpent()"))
    pg.click('.done .btn-primary'); pg.wait_for_timeout(200)
    check('non-joiner: joinedAgainstInterest empty; cart did not re-prompt without a product view in between', E("sessionSummary().joinedAgainstInterest") is None and E("sessionSummary().nagShown") == 1 and E("sessionSummary().nagDeclines") == 1)

    # ---------- control debrief + truthful membership page ----------
    consent(pg, 'D0', 'A0', design=None)
    E("App.endTask('researcher_ended')"); pg.wait_for_timeout(200)
    check('A0 debrief: comparison group + #23', 'comparison group' in pg.inner_text('.study') and E("[...document.querySelectorAll('.db-item b')].map(b=>b.textContent)") == ['Membership offer repeats after "Not now"'])
    consent(pg, 'MP', 'A0', design=None); nav(pg, 'membership', {'from': 'my'})
    txt = pg.inner_text('#content')
    check('membership page: paid price, Fresh benefit, no "members-only prices"', '₩4,990/month' in txt and 'ShopKR Fresh' in txt and 'Members-only prices' not in txt)
    E("state.checkout=null; state.cart=[{id:1,qty:1}]; saveShop()"); nav(pg, 'checkout')
    check('no ShopKR+ offer at checkout in the membership study', pg.locator('.offer').count() == 0)

    # ---------- the 2×2 design is unchanged ----------
    consent(pg, 'X1', 'A0B0')
    check('2×2 link: no Fresh, no offer pop-up, trial membership', E("CONFIG.DESIGN.id") == 'search-x-drip-v1' and E("visibleProducts().some(p=>p.members)") is False and not first_product_offer(pg, 3) and not first_product_offer(pg, 4))
    nav(pg, 'membership', {'from': 'my'})
    check('2×2 membership page: free trial, no Fresh, no false price claim', 'Free for 30 days' in pg.inner_text('#content') and 'Fresh' not in pg.inner_text('#content') and 'Members-only prices' not in pg.inner_text('#content'))

    # ---------- server columns ----------
    check('sessions row carries the membership measures', wait_until(lambda: (session_row(sid) or {}).get('nagShown') is not None and 'joinedAgainstInterest' in session_row(sid), 10))
    check('no JS errors', not pg.errs, pg.errs[:3])
    check('no requests except the logging server', not pg.ext, pg.ext[:3])
summary()
