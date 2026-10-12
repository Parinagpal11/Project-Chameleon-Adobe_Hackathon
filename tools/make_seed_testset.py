"""Write the seed test set: 12 varied designs in chameleon-graph/1 format.

These are hand-laid stand-ins so the engine has something realistic to chew on in week 1.
They get replaced/extended by designs the team builds in Adobe Express (target: 36).
Photos are placeholders: a fill colour plus a `subject` box (image-relative 0..1).

Run:  python tools/make_seed_testset.py
      then python tools/make_photo_testset.py (it adds the 24 photo designs and rewrites index.json with all 36)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'examples' / 'testset'
LH = 1.15


def T(id, x, y, w, size, text, lines=1, weight=600, color='#111111', align='left', font='Inter', role=None, lh=LH, ls=0):
    n = {'id': id, 'type': 'text', 'box': [x, y, w, round(lines * size * lh, 1)], 'text': text,
         'style': {'fontSize': size, 'fontWeight': weight, 'fontFamily': font, 'color': color, 'align': align, 'lineHeight': lh}}
    if ls: n['style']['letterSpacing'] = ls
    if role: n['role'] = role
    return n


def R(id, x, y, w, h, fill, radius=0, role=None, stroke=None, opacity=None):
    n = {'id': id, 'type': 'shape', 'shape': 'rect', 'box': [x, y, w, h], 'style': {'fill': fill, 'radius': radius}}
    if stroke: n['style']['stroke'] = stroke
    if opacity is not None: n['style']['opacity'] = opacity
    if role: n['role'] = role
    return n


def E(id, x, y, w, h, fill, role=None, opacity=None):
    n = {'id': id, 'type': 'shape', 'shape': 'ellipse', 'box': [x, y, w, h], 'style': {'fill': fill}}
    if opacity is not None: n['style']['opacity'] = opacity
    if role: n['role'] = role
    return n


def I(id, x, y, w, h, fill, subject=None, role=None, label=None, radius=0):
    n = {'id': id, 'type': 'image', 'box': [x, y, w, h], 'style': {'fill': fill, 'radius': radius}}
    if subject: n['subject'] = subject
    if role: n['role'] = role
    if label: n['meta'] = {'label': label}
    return n


def BTN(id, x, y, w, h, label, fill='#111111', color='#ffffff', size=None, radius=None, font='Inter'):
    size = size or round(h * .38)
    th = round(size * LH, 1)
    return [R(f'{id}-bg', x, y, w, h, fill, radius if radius is not None else h / 2),
            T(f'{id}-label', x + 12, round(y + (h - th) / 2, 1), w - 24, size, label, weight=700, color=color, align='center', font=font),
            {'id': id, 'type': 'group', 'children': [f'{id}-bg', f'{id}-label']}]


def design(name, w, h, bg, nodes, tags, level):
    return {'format': 'chameleon-graph/1', 'name': name, 'page': {'width': w, 'height': h, 'background': bg},
            'nodes': nodes, 'meta': {'level': level, 'tags': tags, 'source': 'seed (hand-laid stand-in)'}}


D = {}

D['promo-centered'] = design('Spring promo, centred', 1080, 1080, '#F4EFE6', [
    E('blob-a', -120, -140, 420, 420, '#E9C9A8', role='decoration'),
    E('blob-b', 820, 800, 380, 380, '#CFE0C3', role='decoration'),
    T('eyebrow', 340, 250, 400, 28, 'NEW SEASON', weight=700, color='#7A5C3E', align='center', ls=4),
    T('headline', 140, 310, 800, 96, 'Fresh picks for spring', lines=2, weight=800, color='#2B1D14', align='center', font='Playfair Display', lh=1.05),
    T('subhead', 190, 530, 700, 34, 'Seasonal bowls, made the morning you order.', weight=500, color='#4A3A2E', align='center'),
    *BTN('cta', 400, 625, 280, 84, 'Order now', fill='#2B1D14'),
    T('logo', 440, 960, 200, 30, 'GREENLY', weight=800, color='#2B1D14', align='center', ls=3),
], ['centred', 'text-only', 'decoration'], 'simple')

D['split-photo-left'] = design('Coffee launch, photo left', 1200, 628, '#FFFFFF', [
    I('photo', 0, 0, 600, 628, '#B98B5E', subject=[.25, .2, .5, .65], label='coffee cup'),
    I('logo', 1010, 40, 150, 48, '#1E1E1E', role='logo', label='logo'),
    T('headline', 660, 170, 480, 60, 'Brew a little joy', lines=2, weight=800, color='#1E1E1E', lh=1.05),
    T('body', 660, 310, 470, 24, 'Small-batch roasts delivered every two weeks.', lines=2, weight=400, color='#555555', lh=1.35),
    *BTN('cta', 660, 410, 220, 64, 'Start trial', fill='#C8693B'),
], ['split', 'photo', 'left-aligned'], 'simple')

D['overlay-fullbleed'] = design('Travel overlay, full-bleed photo', 1080, 1350, '#0E2233', [
    I('photo', 0, 0, 1080, 1350, '#3E6E8E', subject=[.3, .15, .45, .45], label='mountain lake'),
    R('scrim', 0, 760, 1080, 590, '#0E2233', opacity=.65),
    I('logo', 70, 70, 170, 56, '#FFFFFF', role='logo', label='logo'),
    T('headline', 70, 860, 900, 92, 'Find your quiet place', lines=2, weight=800, color='#FFFFFF', lh=1.05),
    T('subhead', 70, 1075, 760, 34, 'Cabins across the Alps from $89 a night.', weight=500, color='#DCE8F0'),
    *BTN('cta', 70, 1160, 300, 86, 'Book a cabin', fill='#FFFFFF', color='#0E2233'),
], ['overlay', 'photo', 'left-aligned'], 'hard')

D['event-poster'] = design('Design meetup poster', 1080, 1350, '#151515', [
    *[x for x in [R('date-bg', 80, 80, 220, 110, '#FF5A36', radius=12),
                  T('date', 100, 105, 180, 50, 'OCT 24', weight=800, color='#FFFFFF', align='center'),
                  {'id': 'date-badge', 'type': 'group', 'children': ['date-bg', 'date']}]],
    T('eyebrow', 80, 270, 600, 30, 'ISU DESIGN NIGHT', weight=700, color='#FF5A36', ls=3),
    T('headline', 80, 320, 920, 120, 'Make it bend, not break', lines=3, weight=800, color='#FFFFFF', font='Space Grotesk', lh=1.0),
    T('details', 80, 700, 700, 32, '6:30 PM · Student Innovation Center 1118', weight=500, color='#CCCCCC'),
    R('rule', 80, 770, 920, 3, '#333333', role='decoration'),
    I('sp1', 80, 820, 280, 280, '#6B5B95', subject=[.25, .1, .5, .6], label='speaker', radius=140),
    T('sp1-name', 80, 1115, 280, 28, 'Maya Chen', weight=700, color='#FFFFFF', align='center'),
    I('sp2', 400, 820, 280, 280, '#88B04B', subject=[.25, .1, .5, .6], label='speaker', radius=140),
    T('sp2-name', 400, 1115, 280, 28, 'Leo Park', weight=700, color='#FFFFFF', align='center'),
    I('sp3', 720, 820, 280, 280, '#F7CAC9', subject=[.25, .1, .5, .6], label='speaker', radius=140),
    T('sp3-name', 720, 1115, 280, 28, 'Ava Ruiz', weight=700, color='#FFFFFF', align='center'),
    T('legal', 80, 1260, 920, 20, 'Free entry. RSVP required; seats are limited. Terms apply.', weight=400, color='#888888'),
], ['poster', 'many-elements', 'repeated-cards'], 'medium')

D['sale-banner'] = design('Summer sale banner', 1200, 628, '#FFE45C', [
    E('sun', 860, -160, 520, 520, '#FFC93C', role='decoration'),
    T('headline', 70, 80, 560, 44, 'Summer sale', weight=800, color='#1B1B1B'),
    T('offer', 70, 140, 600, 150, '50% OFF', weight=800, color='#1B1B1B', font='Montserrat', lh=1.0),
    T('body', 70, 310, 520, 26, 'On every pair of sandals, this weekend only.', weight=500, color='#333333'),
    *BTN('cta', 70, 390, 240, 70, 'Shop the sale', fill='#1B1B1B'),
    I('product', 700, 110, 440, 420, '#E07A5F', subject=[.15, .2, .7, .6], label='sandal'),
    T('legal', 70, 570, 700, 16, '*Selected styles. Valid until Sunday 11:59 PM. While stocks last.', weight=400, color='#555555'),
], ['offer', 'product', 'legal'], 'medium')

D['quote-card'] = design('Customer quote card', 1080, 1080, '#EEF2FF', [
    T('mark', 100, 90, 200, 260, '“', weight=800, color='#C7D2FE', font='DM Serif Display', lh=1.0, role='decoration'),
    T('quote', 140, 300, 800, 54, 'Chameleon cut our resize work from a day to ten minutes.', lines=4, weight=600, color='#1E1B4B', align='center', font='DM Serif Display', lh=1.2),
    I('avatar', 330, 720, 96, 96, '#A5B4FC', subject=[.2, .1, .6, .7], label='avatar', radius=48),
    T('name', 446, 728, 360, 32, 'Priya Desai', weight=700, color='#1E1B4B'),
    T('title', 446, 770, 360, 24, 'Design lead, Northwind', weight=400, color='#4338CA'),
], ['centred', 'quote', 'lockup'], 'simple')

D['product-grid'] = design('Three products grid', 1080, 1080, '#FAFAF7', [
    T('headline', 80, 80, 920, 64, 'This week’s bestsellers', weight=800, color='#111111', align='center'),
    I('p1', 80, 250, 280, 340, '#D4A373', subject=[.15, .15, .7, .7], label='mug', radius=16),
    T('p1-name', 80, 610, 280, 30, 'Stoneware mug', weight=600, color='#111111', align='center'),
    T('p1-price', 80, 650, 280, 30, '$24', weight=800, color='#BC4749', align='center'),
    I('p2', 400, 250, 280, 340, '#A3B18A', subject=[.15, .15, .7, .7], label='plant pot', radius=16),
    T('p2-name', 400, 610, 280, 30, 'Clay planter', weight=600, color='#111111', align='center'),
    T('p2-price', 400, 650, 280, 30, '$32', weight=800, color='#BC4749', align='center'),
    I('p3', 720, 250, 280, 340, '#8D99AE', subject=[.15, .15, .7, .7], label='lamp', radius=16),
    T('p3-name', 720, 610, 280, 30, 'Desk lamp', weight=600, color='#111111', align='center'),
    T('p3-price', 720, 650, 280, 30, '$58', weight=800, color='#BC4749', align='center'),
    *BTN('cta', 390, 820, 300, 84, 'Shop all', fill='#111111'),
    T('logo', 440, 980, 200, 26, 'HOMEWARE CO', weight=800, color='#111111', align='center', ls=2),
], ['grid', 'repeated-cards', 'centred'], 'hard')

D['webinar-speakers'] = design('Webinar with two speakers', 1600, 900, '#0B1020', [
    I('logo', 90, 70, 180, 54, '#FFFFFF', role='logo', label='logo'),
    T('eyebrow', 90, 230, 500, 28, 'LIVE WEBINAR', weight=700, color='#7DD3FC', ls=3),
    T('headline', 90, 280, 760, 72, 'Scaling design systems without the chaos', lines=3, weight=800, color='#FFFFFF', lh=1.08),
    T('details', 90, 560, 700, 30, 'Thursday, Nov 6 · 11 AM CT · 45 min', weight=500, color='#CBD5E1'),
    *BTN('cta', 90, 640, 300, 80, 'Save my seat', fill='#38BDF8', color='#0B1020'),
    I('sp1', 980, 200, 240, 300, '#334155', subject=[.2, .05, .6, .6], label='speaker', radius=20),
    T('sp1-name', 980, 520, 240, 28, 'Jordan Lee', weight=700, color='#FFFFFF', align='center'),
    T('sp1-role', 980, 556, 240, 22, 'Staff designer', weight=400, color='#94A3B8', align='center'),
    I('sp2', 1260, 200, 240, 300, '#475569', subject=[.2, .05, .6, .6], label='speaker', radius=20),
    T('sp2-name', 1260, 520, 240, 28, 'Sam Ortiz', weight=700, color='#FFFFFF', align='center'),
    T('sp2-role', 1260, 556, 240, 22, 'Eng manager', weight=400, color='#94A3B8', align='center'),
], ['split', 'repeated-cards', 'left-aligned'], 'medium')

D['story-stacked'] = design('Recipe story, stacked', 1080, 1920, '#FFF8F0', [
    I('photo', 0, 0, 1080, 1080, '#E76F51', subject=[.2, .25, .6, .55], label='pasta bowl'),
    T('logo', 70, 60, 300, 36, 'KITCHEN·CO', weight=800, color='#FFFFFF', ls=2),
    T('eyebrow', 90, 1160, 600, 32, '15-MINUTE DINNER', weight=700, color='#E76F51', ls=3),
    T('headline', 90, 1215, 900, 96, 'Lemon garlic pasta', lines=2, weight=800, color='#264653', font='Playfair Display', lh=1.05),
    T('body', 90, 1440, 880, 36, 'Five ingredients, one pan, zero stress. Swipe up for the full recipe.', lines=2, weight=400, color='#3D405B', lh=1.35),
    *BTN('cta', 90, 1620, 360, 100, 'Get the recipe', fill='#264653'),
], ['stacked', 'photo', 'story'], 'simple')

D['dense-menu'] = design('Café menu, dense', 1080, 1350, '#1F2A24', [
    T('headline', 90, 90, 900, 84, 'Today at the café', weight=800, color='#F2E8CF', font='DM Serif Display'),
    R('rule-top', 90, 210, 900, 2, '#F2E8CF', role='decoration'),
    *[n for i, (item, price) in enumerate([('Flat white', '$4.50'), ('Cardamom bun', '$3.75'), ('Avocado toast', '$9.00'),
                                          ('Matcha latte', '$5.25'), ('Granola bowl', '$7.50'), ('Iced tea', '$3.00')])
      for n in (T(f'item{i+1}', 90, 260 + i * 120, 600, 40, item, weight=600, color='#F2E8CF'),
                T(f'price{i+1}', 790, 260 + i * 120, 200, 40, price, weight=700, color='#E9C46A', align='right'))],
    R('rule-bottom', 90, 1010, 900, 2, '#F2E8CF', role='decoration'),
    T('note', 90, 1060, 900, 30, 'Oat milk free on Mondays.', weight=500, color='#CAD2C5'),
    T('logo', 90, 1220, 400, 34, 'MOSS CAFÉ', weight=800, color='#F2E8CF', ls=3),
    T('legal', 590, 1230, 400, 18, 'Prices include tax. Menu may change.', weight=400, color='#8A9A8F', align='right'),
], ['dense', 'list', 'text-heavy'], 'hard')

D['asymmetric-number'] = design('48-hour flash, asymmetric', 1080, 1080, '#111827', [
    R('stripe', 0, 640, 1080, 18, '#F43F5E', role='decoration'),
    I('product', 70, 80, 360, 420, '#9CA3AF', subject=[.1, .1, .8, .8], label='headphones', radius=24),
    T('number', 480, 60, 560, 300, '48h', weight=800, color='#F43F5E', font='Space Grotesk', align='right', lh=1.0),
    T('offer', 520, 400, 520, 52, '30% off all audio', weight=700, color='#FFFFFF', align='right'),
    T('headline', 70, 720, 800, 80, 'Flash sale', weight=800, color='#FFFFFF', font='Space Grotesk'),
    T('body', 70, 830, 760, 30, 'Ends Sunday at midnight. No code needed.', weight=400, color='#D1D5DB'),
    *BTN('cta', 70, 920, 260, 76, 'Shop audio', fill='#F43F5E'),
], ['asymmetric', 'big-type', 'product'], 'medium')

D['app-download'] = design('App download, landscape', 1600, 900, '#F5F3FF', [
    E('halo', 160, 120, 660, 660, '#DDD6FE', role='decoration'),
    I('phone', 330, 90, 330, 720, '#4C1D95', subject=[.05, .05, .9, .9], label='app screenshot', radius=40),
    T('headline', 820, 230, 680, 80, 'Plan trips with friends', lines=2, weight=800, color='#2E1065', lh=1.05),
    T('body', 820, 440, 640, 30, 'Shared itineraries, split costs, one app.', weight=400, color='#4C1D95'),
    *[n for n in [R('ios-bg', 820, 540, 230, 76, '#111111', radius=14),
                  T('ios', 836, 559, 198, 32, 'App Store', weight=700, color='#FFFFFF', align='center'),
                  R('and-bg', 1070, 540, 230, 76, '#111111', radius=14),
                  T('and', 1086, 559, 198, 32, 'Google Play', weight=700, color='#FFFFFF', align='center'),
                  {'id': 'stores', 'type': 'group', 'children': ['ios-bg', 'ios', 'and-bg', 'and']}]],
    T('rating', 820, 650, 500, 26, '4.8 ★ from 12,000 reviews', weight=600, color='#6D28D9'),
], ['split', 'device', 'badges'], 'medium')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for key, d in D.items():
        (OUT / f'{key}.json').write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
        index.append({'id': key, 'name': d['name'], 'width': d['page']['width'], 'height': d['page']['height'],
                      'level': d['meta']['level'], 'tags': d['meta']['tags']})
    (OUT / 'index.json').write_text(json.dumps(index, indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {len(index)} designs to {OUT}')


if __name__ == '__main__':
    main()
