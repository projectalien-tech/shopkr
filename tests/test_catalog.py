"""v6.4.0: deeper Food and Groceries catalogue (ids 49–58)."""
from harness import *

NEW = list(range(49, 59))

with environment() as pg:
    E = pg.evaluate
    def results(query='', category=None, sort='recommended', free=False, fast=False):
        return E("""([q, c, s, f, x]) => { state.query = q; state.category = c; state.sortBy = s;
                     state.filters.free = f; state.filters.fast = x; return searchResults().map(p => p.id); }""",
                 [query, category, sort, free, fast])

    # ---------- counts (2×2 link: no Fresh) ----------
    consent(pg, 'K1', 'A0B0')
    counts = E("Object.fromEntries(visibleCategories().map(c => [c.id, visibleProducts().filter(p => p.cat === c.id).length]))")
    check('Food and Groceries have 10 products; other categories unchanged at 5',
          counts['food'] == 10 and counts['grocery'] == 10 and all(v == 5 for k, v in counts.items() if k not in ('food', 'grocery')), counts)
    check('ids unique; 58 products in all', E("new Set(PRODUCTS.map(p => p.id)).size === PRODUCTS.length && PRODUCTS.length === 58"))
    check('category search lists all 10', len(results(category='food')) == 10 and len(results(category='grocery')) == 10)

    # ---------- English and Korean search reach the new items ----------
    cases = {'tuna': {50}, 'tofu': {56}, 'soy sauce': {55}, 'udon': {52}, 'somen': {49}, 'garlic': {58}, 'bulgogi': {53}, 'chicken': {51, 57}}
    for q, want in cases.items():
        got = set(results(q))
        check(f'search "{q}" → {sorted(want)}', got == want, sorted(got))
    check('"rice" finds instant rice and 4kg rice', {6, 54} <= set(results('rice')))
    check('"noodles" finds ramen, bibim, somen and udon', {1, 3, 49, 52} <= set(results('noodles')))
    check('"seasoning" finds gochujang, bulgogi sauce, soy sauce, garlic', {7, 53, 55, 58} <= set(results('seasoning')))
    check('Korean "닭가슴살" finds both chicken breasts', set(results('닭가슴살')) == {51, 57})
    check('earlier searches unchanged ("ramen", "oil", "egg")', results('ramen') == [1] and results('oil') == [8] and set(results('egg')) == {9})

    # ---------- the search patterns have something to act on ----------
    only(pg)   # all patterns off
    check('pattern off: best-value frozen chicken ranks above the sponsored smoked chicken', results('chicken') == [57, 51])
    only(pg, 'sortPinning')
    check('sortPinning: sponsored smoked chicken pinned first', results('chicken') == [51, 57])
    check('sortPinning: sponsored items lead Food', results(category='food')[:2] == [4, 51] or results(category='food')[:2] == [51, 4], results(category='food')[:3])
    only(pg)
    check('free-shipping filter drops tofu', 56 not in results(category='grocery', free=True))
    check('next-day filter drops somen and garlic', not ({49, 58} & set(results(category='food', fast=True) + results(category='grocery', fast=True))))
    only(pg, 'priceComparisonPrevention')
    check('priceComparisonPrevention has mixed-unit sizes for every new item', E("ids => ids.every(id => sizeText(prod(id)) !== prod(id).size)", NEW))
    only(pg)

    # ---------- every new product page renders ----------
    bad = []
    for i in NEW:
        nav(pg, 'product', {'id': i})
        name = E("id => prod(id).name", i)
        if pg.locator('#content svg[role=img]').count() == 0 or name not in pg.inner_text('#content'):
            bad.append(i)
    check('product pages for 49–58 render with art and name', not bad, bad)
    check('tuna uses the new can art', E("illus(prod(50).art, '', 100).includes('ellipse cx=\"100\" cy=\"84\"')"))

    # ---------- Fresh alternatives ----------
    consent(pg, 'K2', 'A0', design=None)
    sv = E("memberSavings([{id:43,qty:1},{id:44,qty:1}], {memberShipWaived:false})")
    check('Fresh chicken and tofu now count savings (₩2,000 + ₩500)', sv['fresh'] == 2500, sv)

    # ---------- cheapest basket meeting the task, without joining ----------
    E("state.cart = [{id:56,qty:1},{id:3,qty:1},{id:55,qty:1}]; saveShop()")   # tofu, bibim noodles, soy sauce
    nav(pg, 'cart'); pg.wait_for_timeout(100)
    if pg.locator('.modal-card').count(): pg.click('.modal-actions .btn >> text="Not now"')
    pg.click('#bottomnav .btn'); pg.wait_for_timeout(1700); pg.click('#pay-btn'); pg.wait_for_timeout(300)
    check('cheapest valid basket pays ₩17,580 (incl. ₩3,000 shipping + ₩1,500 handling)', E("state.screen") == 'orderDone' and E("totalSpent()") == 17580, E("totalSpent()"))

    check('no JS errors', not pg.errs, pg.errs[:3])
    check('no requests except the logging server', not pg.ext, pg.ext[:3])
summary()
