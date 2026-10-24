#!/usr/bin/env python3
"""
hand.py — 손으로 그린 듯한 오프닝.

매끈한 그라데이션과 완벽한 곡선은 '컴퓨터로 만든 티'가 난다.
손그림처럼 보이게 하는 것은 결국 이 네 가지다.

  1) 종이      — 크림색 바탕에 섬유 결과 얼룩
  2) 떨리는 선 — 자로 잰 선이 아니라 미세하게 흔들리는 펜선
  3) 크레용 칠 — 선 밖으로 조금 삐져나가고, 결이 보이는 색칠
  4) 초당 10장 — 30장을 다 그리지 않고 3프레임씩 같은 그림을 쓴다.
                 그림마다 선이 미세하게 달라지며 자글거리는 느낌(보일링)이 난다.

미리보기:
    ~/.dubtools/bin/python hand.py
"""
import numpy as np, os
from PIL import Image, ImageDraw, ImageFilter

import make_credits as MC

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1280, 720, 30
HOLD = 3                     # 한 그림을 몇 프레임 쓰는가 (3 = 초당 10장)

PAPER   = np.array([246, 239, 223], np.float32)
INK     = np.array([ 42,  34,  28], np.float32)
RED     = np.array([188,  58,  52], np.float32)
RED_DK  = np.array([142,  36,  36], np.float32)
GOLD    = np.array([206, 158,  70], np.float32)

font = MC.font


# ───────────────────────────────────────── 도구
def ease_out(x):    return 1 - (1 - x) ** 3
def ease_in_out(x): return 3*x*x - 2*x*x*x
def clamp01(x):     return max(0.0, min(1.0, x))
def seg(t, a, b):
    if b <= a: return 1.0 if t >= b else 0.0
    return clamp01((t - a) / (b - a))

def smooth_noise(h, w, scale, seed):
    """부드럽게 번지는 잡음 (-1~1). 손떨림·종이결의 재료."""
    rng = np.random.default_rng(seed)
    sh, sw = max(2, h // scale), max(2, w // scale)
    n = rng.normal(0, 1, (sh, sw)).astype(np.float32)
    n = (n - n.min()) / (np.ptp(n) + 1e-9)
    im = Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(im, np.float32) / 255.0 * 2 - 1


def paper_bg(seed):
    """크림색 종이 — 섬유 결, 옅은 얼룩, 가장자리 그늘"""
    bg = np.repeat(PAPER[None, None, :], H, 0).repeat(W, 1)
    fiber = smooth_noise(H, W, 2, seed) * 4.0 + smooth_noise(H, W, 9, seed + 1) * 5.0
    stain = smooth_noise(H, W, 90, seed + 2)
    bg += fiber[..., None]
    bg += (stain * 7.0)[..., None] * np.array([1.0, .92, .72], np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W/2) / (W*0.78))**2 + ((yy - H/2) / (H*0.82))**2)
    bg *= np.clip(1.04 - 0.20 * r**2.4, 0.72, 1.0)[..., None]
    return bg


def crayon_tex(seed, angle=0.62):
    """크레용 결 — 손으로 칠하면 방향도 세기도 일정하지 않다"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # 칠하는 방향 자체가 조금씩 흔들린다
    wob = smooth_noise(H, W, 70, seed + 31) * 0.30
    u  = xx * np.cos(angle + wob) + yy * np.sin(angle + wob)
    v  = xx * np.cos(angle - 1.15) + yy * np.sin(angle - 1.15)
    hatch  = 0.90 + 0.10 * np.sin(u / 2.6)          # 주된 결 (약하게)
    hatch *= 0.95 + 0.05 * np.sin(v / 3.7 + 0.8)    # 교차하는 결
    # 세게 칠한 곳과 살짝 스친 곳
    press = (smooth_noise(H, W, 26, seed + 12) * 0.5 + 0.5)
    hatch *= 0.80 + 0.34 * press
    grain = smooth_noise(H, W, 2, seed) * 0.11 + smooth_noise(H, W, 6, seed + 3) * 0.13
    return np.clip(hatch + grain, 0.32, 1.18)


def ink_edge(dist, width, soft=1.1):
    """선까지의 거리 → 펜선 진하기"""
    return np.clip(1.0 - (np.abs(dist) - width) / soft, 0, 1)


# ───────────────────────────────────────── 막 한 폭 그리기
def curtain_panel(cw, seed, mirror=False):
    """
    폭 cw 의 막 한 폭을 그린다.
    반환: (색 레이어 HxWx3, 알파 HxW)  — 알파가 0 이면 종이가 그대로 보인다.
    """
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # 안쪽 모서리 — 곧은 직선이 아니라 흔들린다
    wob = smooth_noise(H, 1, 40, seed)[:, 0] * 9.0 + smooth_noise(H, 1, 150, seed+7)[:, 0] * 5.0
    edge = cw + wob[:, None]

    inside = xx < edge
    a = np.where(inside, 1.0, 0.0).astype(np.float32)
    # 크레용은 선 밖으로 조금 삐져나간다
    spill = np.clip(1.0 - (xx - edge) / 7.0, 0, 1) * (smooth_noise(H, W, 7, seed+3)*.5+.5)
    a = np.maximum(a, np.where((xx >= edge) & (xx < edge + 7), spill, 0))

    # 주름 — 세로로 흔들리는 띠
    fold = np.zeros((H, W), np.float32)
    nf = max(2, int(cw / 86) + 2)
    rng = np.random.default_rng(seed + 11)
    for k in range(nf):
        fx = (k + 0.5) / nf
        base = edge[:, 0] * fx if cw > 0 else 0
        jitter = smooth_noise(H, 1, 55, seed + 20 + k)[:, 0] * 7.0
        cx = (base + jitter)[:, None]
        d = xx - cx
        fold += np.exp(-(d / (7.0 + rng.random() * 5)) ** 2) * (0.5 + rng.random() * 0.5)

    # 주름마다 가느다란 펜선 (끝까지 긋지 않고 중간에 끊긴다)
    foldline = np.zeros((H, W), np.float32)
    for k in range(nf):
        fx = (k + 0.5) / nf
        base = edge[:, 0] * fx if cw > 0 else 0
        cx = (base + smooth_noise(H, 1, 55, seed + 20 + k)[:, 0] * 7.0)[:, None]
        on = np.clip(smooth_noise(H, 1, 30, seed + 60 + k)[:, 0] * 1.4 + 0.45, 0, 1)[:, None]
        foldline = np.maximum(foldline, ink_edge(xx - cx, 0.7, 1.2) * on * 0.5)

    tex = crayon_tex(seed + 5)
    shade = np.clip(0.72 + 0.46 * tex - 0.30 * np.clip(fold, 0, 1.4), 0.30, 1.25)
    # 아래로 갈수록 살짝 어둡게 (칠하다 보면 자연히 그렇게 된다)
    shade *= 1.06 - 0.22 * (yy / H)

    col = RED[None, None, :] * shade[..., None]
    col = col * 0.82 + RED_DK[None, None, :] * 0.18 * np.clip(fold, 0, 1)[..., None]

    col = col * (1 - foldline[..., None] * 0.55) + INK[None, None, :] * (foldline * 0.55)[..., None]

    # 안쪽 모서리 펜선
    line = ink_edge(xx - edge, 1.6, 1.4) * (0.72 + 0.28 * (smooth_noise(H, W, 5, seed+9)*.5+.5))
    col = col * (1 - line[..., None]) + INK[None, None, :] * line[..., None]
    a = np.maximum(a, line)

    if mirror:
        col = col[:, ::-1]; a = a[:, ::-1]
    return col, np.clip(a, 0, 1)


def valance(seed):
    """천장 주름 천 — 물결 모양 아래 끝"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = 92.0
    wave = 18 * np.sin(xx / 46.0) + 7 * np.sin(xx / 17.0 + 1.1)
    wave += smooth_noise(1, W, 60, seed)[0] * 7.0
    bot = base + wave

    a = np.clip(bot - yy, 0, 1)
    tex = crayon_tex(seed + 4, angle=1.35)
    fold = 0.5 + 0.5 * np.sin(xx / 31.0 + smooth_noise(1, W, 40, seed+2)[0] * 1.6)
    shade = np.clip(0.78 + 0.42 * tex - 0.26 * fold, 0.34, 1.22)
    col = RED[None, None, :] * shade[..., None]

    line = ink_edge(yy - bot, 1.7, 1.5)
    gold = ink_edge(yy - bot + 7, 3.4, 2.2) * 0.75
    col = col * (1 - gold[..., None]) + GOLD[None, None, :] * gold[..., None]
    col = col * (1 - line[..., None]) + INK[None, None, :] * line[..., None]
    a = np.maximum(a, line)
    return col, np.clip(a, 0, 1)


# ───────────────────────────────────────── 손글씨 느낌 글자
def text_mask(text, f, y, spacing=0):
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    if spacing:
        total = sum(d.textlength(c, font=f) + spacing for c in text) - spacing
        x = (W - total) / 2
        for c in text:
            d.text((x, y), c, font=f, fill=255); x += d.textlength(c, font=f) + spacing
    else:
        d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=255)
    return np.asarray(im, np.float32) / 255.0


def inkify(mask, seed, rough=0.55, jitter=2.0):
    """(큰 글자일수록 jitter 를 키우면 손으로 쓴 느낌이 강해진다)"""
    """반듯한 글자를 '펜으로 쓴 것처럼' 흔들고 테두리를 거칠게 만든다"""
    dx = (smooth_noise(H, W, 46, seed) * jitter
          + smooth_noise(H, W, 11, seed + 5) * jitter * 0.45).astype(np.int32)
    dy = (smooth_noise(H, W, 46, seed + 1) * jitter
          + smooth_noise(H, W, 11, seed + 6) * jitter * 0.45).astype(np.int32)
    yy, xx = np.mgrid[0:H, 0:W]
    m = mask[np.clip(yy + dy, 0, H-1), np.clip(xx + dx, 0, W-1)]
    # 테두리를 울퉁불퉁하게 — 잉크가 고르게 묻지 않는다
    n = smooth_noise(H, W, 4, seed + 2)
    m = np.clip(m * (1 + rough * n) - 0.12 * np.clip(n, 0, 1), 0, 1)
    # 안쪽 농담
    m *= 0.80 + 0.20 * (smooth_noise(H, W, 7, seed + 3) * .5 + .5)
    return m


# ───────────────────────────────────────── 한 장 그리기
def draw_one(P, t, secs, seed, L):
    bg = paper_bg(seed)

    open_amt = 0.86 * ease_in_out(seg(t, 0.75, 3.05))
    half = W // 2
    cw = int(round(half * (1.0 - open_amt)))

    # 글자 (막이 반쯤 열린 뒤부터)
    def put(mask, alpha, color):
        if alpha <= 0.004: return
        a = (mask * alpha)[..., None]
        bg[:] = bg * (1 - a) + color[None, None, :] * a

    ta = ease_out(seg(t, 1.70, 2.95))
    if ta > 0.004:
        put(inkify(L["title"], seed * 7 + 1, 0.78, 4.2), ta, INK)
    put(inkify(L["kick"],  seed * 7 + 2, 0.60, 1.8), ease_out(seg(t, 2.45, 3.30)), RED_DK)
    put(inkify(L["sub"],   seed * 7 + 3, 0.55, 2.0), ease_out(seg(t, 3.00, 3.95)), INK * 0.82 + PAPER * 0.18)
    put(inkify(L["team"],  seed * 7 + 4, 0.55, 2.0), ease_out(seg(t, 3.35, 4.25)), RED_DK)

    # 막
    if cw > 0:
        col, a = curtain_panel(cw, seed * 13 + 5)
        bg[:] = bg * (1 - a[..., None]) + col * a[..., None]
        col, a = curtain_panel(cw, seed * 13 + 6, mirror=True)
        bg[:] = bg * (1 - a[..., None]) + col * a[..., None]
    col, a = valance(seed * 13 + 7)
    bg[:] = bg * (1 - a[..., None]) + col * a[..., None]

    # 앞뒤 암전 (종이가 어두워지는 느낌)
    bg *= ease_in_out(seg(t, 0.0, 0.5))
    bg *= 1 - ease_in_out(seg(t, secs - 0.9, secs))
    return np.clip(bg, 0, 255).astype(np.uint8)


def layers(P):
    full  = P["title"]
    title = full.split("—")[0].strip() or full
    sub   = full.split("—")[1].strip() if "—" in full else ""
    return {
        "kick":  text_mask("S O R I T U N E   D U B B I N G", font(23, True), 232, spacing=3),
        "title": text_mask(title, font(68, True), 288),
        "sub":   text_mask(sub, font(30), 382) if sub else np.zeros((H, W), np.float32),
        "team":  text_mask("플로라 팀", font(27, True), 468),
    }


def title_frames(P, secs):
    """초당 10장만 그리고 3프레임씩 쓴다 — 손그림 특유의 자글거림"""
    L = layers(P)
    n = int(round(secs * FPS))
    cur, idx = None, -1
    for i in range(n):
        d = i // HOLD
        if d != idx:
            idx = d
            cur = draw_one(P, (d * HOLD) / FPS, secs, d + 1, L)
        yield cur


def main():
    import imageio_ffmpeg, motion as M, music as MU
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(MC.OUT, exist_ok=True)
    P = MC.read_project()
    secs = 6.6
    wav = M.write_wav(MU.render("warm", secs, 0.85, fade_in=0.6, fade_out=0.9),
                      os.path.join(MC.OUT, "hand.wav"))
    M.encode(title_frames(P, secs), secs, wav,
             os.path.join(HERE, "오프닝_손그림.mp4"), ff)
    print("  오프닝_손그림.mp4")

if __name__ == "__main__":
    main()
