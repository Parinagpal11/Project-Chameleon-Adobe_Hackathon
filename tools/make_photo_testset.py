"""Write 24 more test designs (on top of the 12 hand-laid seeds): real photos, more formats, harder cases.

Each design is a chameleon-graph/1 file in examples/testset with its photo embedded (resized to at most
900 px, JPEG quality 80). Photos come from tests/fixtures/photos; the `new/` ones are Pexels photos
(see tests/fixtures/photos/new/CREDITS.json). Brands and copy are made up.

They cover what the seeds don't: real subjects found by detection, sources that are themselves banners
(728x90, 300x250, 160x600, 1584x396), two photos, a round photo, text-only, long copy with legal, dark
text on a light photo, group photos, tiny subjects. The team can add or swap in Adobe Express designs.

Run:  python tools/make_photo_testset.py   (rewrites examples/testset/index.json with seeds + these)
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from make_seed_testset import T, R, E, BTN, design, D as SEEDS   # noqa: E402

OUT = ROOT / 'examples' / 'testset'
PHOTOS = ROOT / 'tests' / 'fixtures' / 'photos'


def photo(name):
    im = Image.open(PHOTOS / name).convert('RGB')
    im.thumbnail((900, 900))
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=80, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


def P(id, x, y, w, h, name, role=None, radius=0):
    """A real photo filling its box (cover); the engine finds the subject itself."""
    n = {'id': id, 'type': 'image', 'box': [x, y, w, h], 'src': photo(name), 'style': {'radius': radius},
         'meta': {'label': name.split('/')[-1].rsplit('.', 1)[0]}}
    if role:
        n['role'] = role
    return n


X = {}

X['fitness-story'] = design('Running club, full-bleed story', 1080, 1920, '#101820', [
    P('photo', 0, 0, 1080, 1920, 'runner-sunrise.jpg'),
    R('scrim', 0, 1240, 1080, 680, '#101820', opacity=.7),
    T('logo', 80, 90, 360, 40, 'PACE CLUB', weight=800, color='#FFFFFF', ls=4),
    T('eyebrow', 80, 1320, 700, 34, 'SATURDAYS · 6 AM', weight=700, color='#FDBA74', ls=3),
    T('headline', 80, 1380, 920, 110, 'Run into the sunrise', lines=2, weight=800, color='#FFFFFF', lh=1.02),
    *BTN('cta', 80, 1680, 380, 104, 'Join free', fill='#F97316'),
], ['overlay', 'photo', 'story', 'tiny-subject'], 'hard')

X['outdoor-split'] = design('Outdoor gear, photo right', 1200, 628, '#F1F5F0', [
    P('photo', 620, 0, 580, 628, 'user-hiker-lake.jpg'),
    T('logo', 60, 50, 260, 30, 'NORTHTRAIL', weight=800, color='#1F3D2B', ls=3),
    T('headline', 60, 170, 520, 64, 'Pack light, go further', lines=2, weight=800, color='#1F3D2B', lh=1.05),
    T('body', 60, 330, 500, 24, 'Ultralight tents and packs, tested on the trail.', lines=2, weight=400, color='#3F5245', lh=1.35),
    *BTN('cta', 60, 440, 230, 66, 'Shop gear', fill='#1F3D2B'),
], ['split', 'photo', 'person'], 'simple')

X['meal-card'] = design('Meal kit, card over flat-lay', 1080, 1080, '#1C1917', [
    P('photo', 0, 0, 1080, 1080, 'new/flatlay-meal-prep.jpg'),
    R('card', 180, 330, 720, 420, '#FFFBEB', radius=28, role='panel'),
    T('eyebrow', 230, 390, 620, 28, 'WEEKLY MEAL KIT', weight=700, color='#B45309', align='center', ls=3),
    T('headline', 230, 440, 620, 72, 'Dinner, sorted', weight=800, color='#1C1917', align='center', font='DM Serif Display'),
    T('body', 230, 540, 620, 28, 'Five fresh meals delivered on Sunday.', weight=500, color='#44403C', align='center'),
    *BTN('cta', 400, 620, 280, 76, 'Get 50% off', fill='#B45309'),
], ['card', 'photo', 'flat-lay', 'centred'], 'medium')

X['sneaker-drop'] = design('Sneaker drop, product on white', 1080, 1350, '#F3F4F6', [
    P('photo', 0, 0, 1080, 880, 'new/product-sneakers-white.jpg'),
    T('headline', 70, 930, 940, 84, 'Air, reimagined', weight=800, color='#111827'),
    T('price', 70, 1040, 400, 54, '$129', weight=800, color='#DC2626', font='Space Grotesk'),
    *BTN('cta', 70, 1150, 320, 92, 'Shop the drop', fill='#111827'),
    T('logo', 710, 1176, 300, 34, 'STRIDE', weight=800, color='#111827', align='right', ls=4),
], ['product', 'photo', 'price'], 'simple')

X['street-style'] = design('Street style, copy right', 1080, 1350, '#2B1B12', [
    P('photo', 0, 0, 1080, 1350, 'fashion-street.jpg'),
    R('panel', 620, 0, 460, 1350, '#2B1B12', opacity=.82),
    T('logo', 660, 80, 360, 36, 'MAISON OAK', weight=800, color='#F5E6D3', ls=3),
    T('headline', 660, 520, 380, 96, 'The camel coat edit', lines=3, weight=800, color='#F5E6D3', font='Playfair Display', lh=1.05),
    *BTN('cta', 660, 900, 300, 84, 'Shop the edit', fill='#F5E6D3', color='#2B1B12'),
], ['overlay', 'photo', 'face', 'panel'], 'hard')

X['cafe-friends'] = design('Café, two friends, landscape', 1600, 900, '#FFF7ED', [
    P('photo', 800, 0, 800, 900, 'two-people-cafe.jpg'),
    T('logo', 90, 80, 300, 40, 'CORNER CUP', weight=800, color='#7C2D12', ls=3),
    T('headline', 90, 260, 660, 84, 'Bring a friend, coffee’s on us', lines=3, weight=800, color='#431407', lh=1.05),
    T('body', 90, 580, 620, 30, 'Two drinks for the price of one, every Friday.', weight=400, color='#7C2D12'),
    *BTN('cta', 90, 660, 300, 84, 'Find a café', fill='#C2410C'),
], ['split', 'photo', 'faces', 'two-people'], 'medium')

X['concert-banner'] = design('Concert tickets, wide banner', 1584, 396, '#1E0B33', [
    P('photo', 0, 0, 1584, 396, 'new/crowd-concert.jpg'),
    R('fade', 0, 0, 820, 396, '#1E0B33', opacity=.75),
    T('eyebrow', 60, 70, 600, 26, 'LIVE · NOV 14 · RIVER ARENA', weight=700, color='#F0ABFC', ls=2),
    T('headline', 60, 110, 700, 84, 'Lights Out Tour', weight=800, color='#FFFFFF', font='Space Grotesk'),
    *BTN('cta', 60, 250, 260, 76, 'Get tickets', fill='#D946EF'),
    T('logo', 1330, 320, 200, 28, 'TIXLY', weight=800, color='#FFFFFF', align='right', ls=3),
], ['banner-source', 'overlay', 'crowd'], 'hard')

X['earbuds-leaderboard'] = design('Earbuds, leaderboard source', 728, 90, '#FDF2F8', [
    P('photo', 0, 0, 120, 90, 'earbuds-gradient.jpg'),
    T('headline', 140, 18, 380, 26, 'Silence, on demand', weight=800, color='#3B0764'),
    T('body', 140, 50, 380, 16, 'Noise-cancelling earbuds, 30-hour battery.', weight=400, color='#6B21A8'),
    *BTN('cta', 560, 24, 140, 42, 'Shop now', fill='#7E22CE'),
], ['banner-source', 'small-source', 'product'], 'hard')

X['dog-mrec'] = design('Dog food, medium rectangle source', 300, 250, '#FEF3C7', [
    P('photo', 150, 0, 150, 250, 'dog-studio.jpg'),
    T('logo', 14, 14, 120, 14, 'GOOD BOY', weight=800, color='#78350F', ls=2),
    T('headline', 14, 64, 128, 24, 'Real food for real dogs', lines=3, weight=800, color='#451A03', lh=1.05),
    *BTN('cta', 14, 190, 120, 36, 'Try it', fill='#B45309'),
], ['banner-source', 'small-source', 'animal'], 'medium')

X['paris-skyscraper'] = design('Paris trip, skyscraper source', 160, 600, '#0C4A6E', [
    P('photo', 0, 0, 160, 330, 'new/tall-eiffel-aerial.jpg'),
    T('headline', 14, 352, 132, 24, 'Paris for two from $499', lines=4, weight=800, color='#FFFFFF', lh=1.08),
    *BTN('cta', 14, 490, 132, 40, 'Book now', fill='#FACC15', color='#0C4A6E'),
    T('logo', 14, 560, 132, 14, 'SKYWAY', weight=800, color='#BAE6FD', ls=2),
], ['banner-source', 'tall-source', 'landmark'], 'hard')

X['team-group'] = design('Team photo, two buttons', 1080, 1080, '#FFFFFF', [
    P('photo', 0, 0, 1080, 600, 'new/group-row.jpg'),
    T('headline', 80, 650, 920, 72, 'We’re hiring designers', weight=800, color='#0F172A'),
    T('body', 80, 750, 900, 30, 'Remote-friendly, four-day weeks, real ownership.', weight=400, color='#475569'),
    *BTN('cta', 80, 840, 300, 84, 'See roles', fill='#2563EB'),
    *BTN('cta2', 410, 840, 300, 84, 'Meet the team', fill='#E2E8F0', color='#0F172A'),
    T('logo', 80, 990, 300, 30, 'FIELDWORK', weight=800, color='#0F172A', ls=3),
], ['stacked', 'photo', 'group', 'two-buttons'], 'medium')

X['tokyo-night'] = design('Tokyo after dark, story', 1080, 1920, '#0A0A0A', [
    P('photo', 0, 0, 1080, 1920, 'new/signage-japanese-shopfront.jpg'),
    R('scrim', 0, 0, 1080, 520, '#0A0A0A', opacity=.6),
    T('eyebrow', 80, 120, 700, 34, 'FOOD TOURS', weight=700, color='#FCA5A5', ls=4),
    T('headline', 80, 180, 920, 110, 'Tokyo after dark', weight=800, color='#FFFFFF'),
    *BTN('cta', 80, 1700, 380, 104, 'Book a tour', fill='#EF4444'),
    T('logo', 700, 1735, 300, 36, 'NOMAD EATS', weight=800, color='#FFFFFF', align='right', ls=2),
], ['overlay', 'photo', 'text-in-photo', 'night'], 'hard')

X['skincare-portrait'] = design('Skincare, face right', 1080, 1350, '#FAF5EF', [
    P('photo', 460, 0, 620, 1350, 'portrait-woman.jpg'),
    T('logo', 70, 70, 340, 32, 'DEW & CO', weight=800, color='#3F2A1E', ls=3),
    T('headline', 70, 420, 360, 84, 'Glow, gently', lines=2, weight=800, color='#3F2A1E', font='Playfair Display', lh=1.05),
    T('body', 70, 640, 340, 28, 'A serum for sensitive skin.', lines=2, weight=400, color='#6B4F3F', lh=1.35),
    *BTN('cta', 70, 780, 280, 80, 'Discover', fill='#3F2A1E'),
], ['split', 'photo', 'face'], 'medium')

X['pet-new'] = design('Pet treats, new badge', 1200, 628, '#ECFEFF', [
    P('photo', 640, 0, 560, 628, 'new/animal-pug.jpg'),
    *[n for n in [R('badge-bg', 60, 60, 120, 48, '#0E7490', radius=24),
                  T('badge', 72, 72, 96, 22, 'NEW', weight=800, color='#FFFFFF', align='center'),
                  {'id': 'badge-chip', 'type': 'group', 'children': ['badge-bg', 'badge']}]],
    T('headline', 60, 180, 540, 64, 'Treats he’ll sit for', lines=2, weight=800, color='#164E63', lh=1.05),
    T('body', 60, 340, 520, 24, 'Single-ingredient, grain free, vet approved.', lines=2, weight=400, color='#155E75', lh=1.35),
    *BTN('cta', 60, 450, 230, 66, 'Order now', fill='#0E7490'),
    T('logo', 60, 570, 260, 22, 'PAWSOME', weight=800, color='#164E63', ls=3),
], ['split', 'photo', 'animal', 'badge'], 'simple')

X['two-photo-stay'] = design('Holiday stay, two photos', 1080, 1080, '#F8FAFC', [
    P('photo1', 60, 60, 470, 560, 'landscape-tent.jpg', radius=20),
    P('photo2', 550, 60, 470, 560, 'new/snow-hikers-white.jpg', radius=20),
    T('headline', 60, 680, 960, 72, 'Summer or snow?', weight=800, color='#0F172A', align='center'),
    T('body', 60, 780, 960, 30, 'Mountain cabins open all year.', weight=400, color='#475569', align='center'),
    *BTN('cta', 390, 860, 300, 84, 'Pick your dates', fill='#0F172A'),
    T('logo', 390, 1000, 300, 26, 'ALTITUDE', weight=800, color='#0F172A', align='center', ls=3),
], ['two-photos', 'centred', 'cards'], 'hard')

X['coast-panorama'] = design('Coast trip, panorama band', 1600, 900, '#FFFFFF', [
    P('photo', 0, 0, 1600, 520, 'boat-panorama.jpg'),
    T('headline', 90, 580, 900, 80, 'Sail the hidden coves', weight=800, color='#0C4A6E'),
    T('body', 90, 690, 900, 30, 'Seven days, five islands, one small boat.', weight=400, color='#0369A1'),
    *BTN('cta', 1210, 600, 300, 84, 'Plan the trip', fill='#0284C7'),
    T('logo', 1210, 760, 300, 30, 'BLUE COVE', weight=800, color='#0C4A6E', align='right', ls=3),
], ['stacked', 'panorama', 'tiny-subject'], 'medium')

X['latte-square'] = design('Iced latte, copy left', 1080, 1080, '#F5E9DA', [
    P('photo', 0, 0, 1080, 1080, 'latte-overhead.jpg'),
    T('logo', 80, 80, 300, 34, 'BEAN THERE', weight=800, color='#3B2416', ls=3),
    T('headline', 80, 380, 520, 96, 'Iced, not rushed', lines=2, weight=800, color='#3B2416', font='DM Serif Display', lh=1.05),
    T('body', 80, 620, 460, 30, 'Cold brew, oat milk, a little vanilla.', lines=2, weight=400, color='#5C3D2E', lh=1.35),
    *BTN('cta', 80, 760, 280, 82, 'Order ahead', fill='#3B2416'),
], ['overlay', 'photo', 'light-photo'], 'simple')

X['text-only-launch'] = design('Product launch, text only', 1200, 628, '#0F172A', [
    E('glow', 760, -200, 640, 640, '#1E3A8A', role='decoration'),
    T('eyebrow', 80, 120, 600, 26, 'INTRODUCING', weight=700, color='#93C5FD', ls=4),
    T('headline', 80, 165, 900, 96, 'Version 3 is here', weight=800, color='#FFFFFF', font='Space Grotesk'),
    T('body', 80, 300, 760, 30, 'Faster sync, offline mode and a brand new editor.', weight=400, color='#CBD5E1'),
    *BTN('cta', 80, 400, 260, 76, 'See what’s new', fill='#3B82F6'),
    T('logo', 900, 540, 240, 30, 'TASKFLOW', weight=800, color='#FFFFFF', align='right', ls=3),
], ['text-only', 'decoration', 'dark'], 'simple')

X['serum-long-copy'] = design('Serum, long copy and legal', 1080, 1350, '#FFFFFF', [
    P('photo', 620, 80, 400, 520, 'bottle-terrazzo.jpg', radius=24),
    T('logo', 70, 80, 300, 30, 'LUMEN LABS', weight=800, color='#111827', ls=3),
    T('headline', 70, 200, 520, 72, 'Vitamin C, done right', lines=3, weight=800, color='#111827', lh=1.05),
    T('b1', 70, 470, 520, 30, '15% stable vitamin C', weight=500, color='#374151'),
    T('b2', 70, 520, 520, 30, 'Fragrance free, vegan', weight=500, color='#374151'),
    T('b3', 70, 570, 520, 30, 'Results in four weeks', weight=500, color='#374151'),
    T('body', 70, 680, 940, 30, 'Brighter, more even skin with a serum that stays fresh to the last drop.', lines=2, weight=400, color='#4B5563', lh=1.35),
    *BTN('cta', 70, 820, 300, 84, 'Shop serum', fill='#EA580C'),
    T('legal', 70, 1240, 940, 18, 'Results based on a 4-week study of 60 participants. Individual results vary. Patch test before use.', lines=2, weight=400, color='#6B7280', lh=1.3),
], ['long-copy', 'legal', 'product', 'list'], 'hard')

X['snow-charity'] = design('Winter charity, dark text on light photo', 1080, 1080, '#F8FAFC', [
    P('photo', 0, 0, 1080, 1080, 'new/snow-hikers-white.jpg'),
    T('headline', 80, 100, 920, 88, 'Nobody walks alone', weight=800, color='#0F172A', align='center'),
    T('body', 140, 220, 800, 30, 'Donate a warm coat this winter.', weight=500, color='#334155', align='center'),
    *BTN('cta', 390, 900, 300, 84, 'Donate now', fill='#DC2626'),
], ['overlay', 'light-photo', 'centred', 'small-subjects'], 'medium')

X['podcast-circle'] = design('Podcast episode, round photo', 1080, 1080, '#18181B', [
    P('avatar', 340, 120, 400, 400, 'bw-portrait.jpg', radius=200),
    T('eyebrow', 140, 580, 800, 28, 'EPISODE 42', weight=700, color='#A1A1AA', align='center', ls=4),
    T('headline', 140, 630, 800, 64, 'Designing for every screen', lines=2, weight=800, color='#FAFAFA', align='center', lh=1.08),
    T('guest', 140, 800, 800, 30, 'with Ruth Alvarez', weight=500, color='#D4D4D8', align='center'),
    *BTN('cta', 390, 880, 300, 80, 'Listen now', fill='#FAFAFA', color='#18181B'),
    T('logo', 140, 1000, 800, 26, 'THE GRID SHOW', weight=800, color='#A1A1AA', align='center', ls=3),
], ['round-photo', 'centred', 'face'], 'medium')

X['sandal-countdown'] = design('Sandal sale, big number story', 1080, 1920, '#FFE4E6', [
    E('blob', 600, -200, 700, 700, '#FECDD3', role='decoration'),
    T('eyebrow', 80, 140, 700, 36, 'ENDS SUNDAY', weight=700, color='#9F1239', ls=4),
    T('offer', 80, 200, 920, 300, '40%', weight=800, color='#E11D48', font='Montserrat', lh=1.0),
    T('headline', 80, 520, 920, 80, 'off every sandal', weight=800, color='#4C0519'),
    P('product', 140, 760, 800, 700, 'user-coral-sandal.jpg', radius=32),
    *BTN('cta', 80, 1620, 400, 104, 'Shop sandals', fill='#E11D48'),
    T('logo', 600, 1660, 400, 36, 'SOLE & CO', weight=800, color='#4C0519', align='right', ls=3),
], ['big-number', 'product', 'story'], 'medium')

X['retreat-fog'] = design('Wellness retreat, centred story', 1080, 1920, '#E5E7EB', [
    P('photo', 0, 0, 1080, 1920, 'new/fog-rock.jpg'),
    T('headline', 120, 260, 840, 100, 'Breathe out', weight=800, color='#1F2937', align='center', font='Playfair Display'),
    T('body', 160, 400, 760, 34, 'Three quiet days in the mountains.', weight=500, color='#374151', align='center'),
    *BTN('cta', 340, 1640, 400, 100, 'Reserve a room', fill='#1F2937'),
    T('logo', 340, 1800, 400, 30, 'STILLWATER', weight=800, color='#1F2937', align='center', ls=4),
], ['overlay', 'light-photo', 'centred', 'fog'], 'hard')

X['careers-banner'] = design('Careers, wide banner with friends', 1584, 396, '#EEF2FF', [
    P('photo', 1000, 0, 584, 396, 'three-friends.jpg'),
    T('logo', 60, 40, 300, 28, 'BRIGHTPATH', weight=800, color='#312E81', ls=3),
    T('headline', 60, 110, 860, 64, 'Grow with people you like', weight=800, color='#1E1B4B'),
    T('body', 60, 200, 800, 24, 'Mentors, learning budget and a team that has your back.', weight=400, color='#4338CA'),
    *BTN('cta', 60, 270, 240, 70, 'Apply today', fill='#4F46E5'),
], ['banner-source', 'split', 'faces'], 'medium')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = [{'id': k, 'name': d['name'], 'width': d['page']['width'], 'height': d['page']['height'],
              'level': d['meta']['level'], 'tags': d['meta']['tags']} for k, d in SEEDS.items()]
    for key, d in X.items():
        d['meta']['source'] = 'hand-laid with a real photo (tools/make_photo_testset.py)'
        (OUT / f'{key}.json').write_text(json.dumps(d, ensure_ascii=False) + '\n')
        index.append({'id': key, 'name': d['name'], 'width': d['page']['width'], 'height': d['page']['height'],
                      'level': d['meta']['level'], 'tags': d['meta']['tags']})
    (OUT / 'index.json').write_text(json.dumps(index, indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {len(X)} photo designs; index now has {len(index)}')


if __name__ == '__main__':
    main()
