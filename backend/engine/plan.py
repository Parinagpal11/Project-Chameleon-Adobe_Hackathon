"""Plan stage: how big is the change from the source canvas to the target?

The tier decides the adaptation strategy:
  1 same family    aspect ratio changes by at most ~1.5x and orientation is kept
  2 new orientation portrait <-> landscape, or a ratio change up to ~4x
  3 extreme        ratio change above ~4x, or a tiny target (short side under 160 px)
"""
from __future__ import annotations

TIER_NAMES = {1: 'Same family', 2: 'New orientation', 3: 'Extreme'}
TIER_STRATEGY = {
    1: 'Scale and keep anchors, margins and alignment; re-wrap text; re-crop photos around the subject.',
    2: 'Keep groups intact and re-flow them along the new main axis; rebalance image and text areas.',
    3: 'Rebuild by importance: keep the essentials in one row or column, drop decoration, protect text size.',
}

# The eight evaluation sizes from docs/STRATEGY.md §8
EVAL_SIZES = [
    {'name': 'Instagram portrait', 'width': 1080, 'height': 1350},
    {'name': 'Story', 'width': 1080, 'height': 1920},
    {'name': 'Facebook link', 'width': 1200, 'height': 628},
    {'name': 'Presentation 16:9', 'width': 1600, 'height': 900},
    {'name': 'LinkedIn banner', 'width': 1584, 'height': 396},
    {'name': 'Medium rectangle', 'width': 300, 'height': 250},
    {'name': 'Leaderboard', 'width': 728, 'height': 90},
    {'name': 'Wide skyscraper', 'width': 160, 'height': 600},
]


def orientation(w: float, h: float) -> str:
    a = w / h
    return 'square' if 0.9 <= a <= 1.1 else ('landscape' if a > 1 else 'portrait')


def plan_tier(src_w: float, src_h: float, dst_w: float, dst_h: float) -> dict:
    a, b = src_w / src_h, dst_w / dst_h
    change = max(a / b, b / a)
    o_src, o_dst = orientation(src_w, src_h), orientation(dst_w, dst_h)
    flips = o_src != o_dst and 'square' not in (o_src, o_dst)
    short = min(dst_w, dst_h)
    if abs(src_w - dst_w) < .5 and abs(src_h - dst_h) < .5:
        tier = 1     # the size it was designed at (even a banner): nothing to adapt
    elif change > 4 or short <= 160:
        tier = 3
    elif flips or change > 1.5:
        tier = 2
    else:
        tier = 1
    scale = min(dst_w / src_w, dst_h / src_h)
    if tier == 1 and scale < .35:
        tier = 2   # same shape but much smaller: text and detail no longer fit at the same proportions
    reasons = [f'aspect ratio changes {change:.2f}x ({o_src} → {o_dst})']
    if short <= 160: reasons.append(f'short side is only {int(short)} px')
    if scale < .35: reasons.append(f'content must shrink to {scale * 100:.0f}% of its size')
    return {'tier': tier, 'tier_name': TIER_NAMES[tier], 'strategy': TIER_STRATEGY[tier],
            'ratio_change': round(change, 3), 'from': o_src, 'to': o_dst,
            'scale': round(scale, 4), 'reasons': reasons}
