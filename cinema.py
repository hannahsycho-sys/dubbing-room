#!/usr/bin/env python3
"""
cinema.py — '극장 안에서 영화를 보는' 오프닝과 엔딩.

도형으로만 이루어져 있어 코드로 정확히 그릴 수 있다.
  · 어두운 객석, 붉은 좌석이 원근으로 줄지어 있고
  · 가운데 스크린에 불이 들어오면서 제목이 뜬다
  · 마지막엔 스크린이 하얗게 밝아지며 본편으로 넘어간다

엔딩은 같은 극장에서 스크린 위로 크레딧이 올라가고 'The END' 로 닫는다.

미리보기:
    ~/.dubtools/bin/python cinema.py
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_credits as MC

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1280, 720, 30

# 스크린 위치
SX0, SY0, SX1, SY1 = 232, 44, 1048, 476

ROOM     = (26, 26, 28)
FRAME    = (14, 14, 16)
SCREEN   = (219, 217, 212)
SEAT     = (138, 28, 32)
SEAT_DK  = (74, 14, 18)
INK      = (28, 26, 26)

SERIF   = "/System/Library/Fonts/Supplemental/Didot.ttc"
MYUNGJO = "/System/Library/Fonts/AppleMyungjo.ttf"


def f_serif(size, bold=False):
    for idx in ((1, 2, 0) if bold else (0, 1)):
        try: return ImageFont.truetype(SERIF, size, index=idx)
        except Exception: continue
    return MC.font(size, bold)

def f_kor(size):
    try: return ImageFont.truetype(MYUNGJO, size)
    except Exception: return MC.font(size, True)


def ease_out(x):    return 1 - (1 - x) ** 3
def ease_in_out(x): return 3*x*x - 2*x*x*x
def clamp01(x):     return max(0.0, min(1.0, x))
def seg(t, a, b):
    if b <= a: return 1.0 if t >= b else 0.0
    return clamp01((t - a) / (b - a))


# ───────────────────────────────────────── 객석
def vgrad(size, top, bot):
    w, h = size
    g = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    a = np.array(top, np.float32)[None, None, :] * (1 - g) + np.array(bot, np.float32)[None, None, :] * g
    return Image.fromarray(np.repeat(a, w, 1).astype(np.uint8))


def seat_rows():
    """먼 줄부터 가까운 줄까지 — 가까울수록 크고 아래에 있다"""
    rows = []
    for i, (y, h, w, gap, off, lit) in enumerate([
        (472,  74, 118, 10,   0, 1.00),
        (532,  88, 140, 12,  70, 0.86),
        (604, 106, 168, 14,   0, 0.70),
        (690, 128, 202, 16,  96, 0.55),
    ]):
        rows.append(dict(y=y, h=h, w=w, gap=gap, off=off, lit=lit))
    return rows


def draw_room(light):
    """light 0~1 : 스크린 불빛의 세기. 좌석이 그만큼 밝아진다."""
    img = Image.new("RGB", (W, H), ROOM)
    d = ImageDraw.Draw(img)

    # 벽 — 위가 조금 더 어둡다
    img.paste(vgrad((W, H), (18, 18, 20), (34, 33, 35)), (0, 0))

    # 스크린에서 번지는 빛
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rectangle([SX0 - 30, SY0 - 20, SX1 + 30, SY1 + 30], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    gl = np.asarray(glow, np.float32)[..., None] / 255.0 * light
    base = np.asarray(img, np.float32)
    base += gl * np.array([120, 116, 108], np.float32)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    # 스크린 테두리
    d.rectangle([SX0 - 18, SY0 - 14, SX1 + 18, SY1 + 14], fill=FRAME)
    return img


def paste_screen(img, screen_img, light):
    """스크린 내용(밝기 반영)을 붙인다"""
    sw, sh = SX1 - SX0, SY1 - SY0
    s = np.asarray(screen_img.resize((sw, sh), Image.LANCZOS), np.float32)
    s *= 0.06 + 0.94 * light                       # 영사기가 꺼져 있으면 거의 검다
    img.paste(Image.fromarray(np.clip(s, 0, 255).astype(np.uint8)), (SX0, SY0))
    return img


def draw_seats(img, light):
    d = ImageDraw.Draw(img, "RGBA")
    for r in seat_rows():
        y, h, w, gap, off, lit = r["y"], r["h"], r["w"], r["gap"], r["off"], r["lit"]
        k = 0.30 + 0.70 * lit * (0.35 + 0.65 * light)
        top = tuple(int(SEAT[i] * k + 26 * lit * light) for i in range(3))
        bot = tuple(int(SEAT_DK[i] * k) for i in range(3))
        x = -w + (off % (w + gap))
        while x < W + w:
            box = [x, y, x + w, y + h + 60]
            # 등받이 — 위가 둥글다
            mask = Image.new("L", (w + 1, h + 61), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h + 60], radius=int(h * 0.42), fill=255)
            grad = vgrad((w + 1, h + 61), top, bot)
            img.paste(grad, (int(x), int(y)), mask)
            # 스크린 빛이 닿는 윗선
            d.rounded_rectangle([x + 6, y + 3, x + w - 6, y + 16],
                                radius=7, fill=(255, 200, 170, int(44 * lit * light)))
            x += w + gap
    return img


def vignette(img, amount=0.55):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W/2) / (W*0.76))**2 + ((yy - H/2) / (H*0.80))**2)
    m = np.clip(1.04 - amount * r**2.2, 0.18, 1.0)[..., None]
    return Image.fromarray(np.clip(np.asarray(img, np.float32) * m, 0, 255).astype(np.uint8))


# ───────────────────────────────────────── 스크린에 들어갈 내용
def blank_screen(sw, sh):
    img = Image.new("RGB", (sw, sh), SCREEN)
    a = np.asarray(img, np.float32)
    rng = np.random.default_rng(4)
    a += rng.normal(0, 2.4, (sh, sw, 1))            # 스크린 표면의 아주 옅은 결
    yy = np.linspace(0, 1, sh, dtype=np.float32)[:, None, None]
    a *= 1.03 - 0.10 * yy                           # 아래가 살짝 어둡다
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def centered(d, y, text, f, fill, spacing=0, sw=None):
    sw = sw or (SX1 - SX0)
    if spacing:
        total = sum(d.textlength(c, font=f) + spacing for c in text) - spacing
        x = (sw - total) / 2
        for c in text:
            d.text((x, y), c, font=f, fill=fill); x += d.textlength(c, font=f) + spacing
    else:
        d.text(((sw - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def title_screen(P, t):
    """스크린 위에 제목이 하나씩 떠오른다"""
    sw, sh = SX1 - SX0, SY1 - SY0
    img = blank_screen(sw, sh)
    lay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)

    full  = P["title"]
    main  = full.split("—")[0].strip() or full
    sub   = full.split("—")[1].strip() if "—" in full else ""

    def fade(y, text, f, a, spacing=0, col=INK):
        if a <= 0.004 or not text: return
        tmp = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        centered(ImageDraw.Draw(tmp), y, text, f, col + (int(255 * a),), spacing, sw)
        lay.alpha_composite(tmp)

    fade(96,  "S O R I T U N E   D U B B I N G", f_serif(23), ease_out(seg(t, 1.55, 2.35)), 3)
    fade(150, main, f_serif(74, True), ease_out(seg(t, 2.15, 3.35)))
    if sub:
        fade(262, sub, f_serif(28), ease_out(seg(t, 3.25, 4.15)))
    a = ease_out(seg(t, 4.05, 4.90))
    if a > 0.004:
        d.line([(sw/2 - 90, 318), (sw/2 + 90, 318)], fill=INK + (int(110 * a),), width=1)
        fade(336, "플로라 팀", f_kor(26), a, col=(150, 24, 28))

    img = img.convert("RGBA"); img.alpha_composite(lay)
    return img.convert("RGB")


# ───────────────────────────────────────── 프레임
def zoom_crop(img, z):
    if z <= 1.0001: return img
    nw, nh = int(W * z), int(H * z)
    big = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - W) // 2, int((nh - H) * 0.40)
    return big.crop((x, y, x + W, y + H))


def title_frames(P, secs):
    n = int(round(secs * FPS))
    for i in range(n):
        t = i / FPS
        light = ease_in_out(seg(t, 0.55, 1.65))
        flash = ease_in_out(seg(t, secs - 0.95, secs - 0.15))   # 끝에 스크린이 하얗게

        img = draw_room(light)
        img = paste_screen(img, title_screen(P, t), light)
        img = draw_seats(img, light)
        img = vignette(img)
        img = zoom_crop(img, 1.0 + 0.055 * ease_in_out(seg(t, 0.4, secs)))

        a = np.asarray(img, np.float32)
        if flash > 0.002:                       # 스크린이 번지며 화면을 덮는다 → 본편으로
            m = np.zeros((H, W, 1), np.float32)
            m[SY0:SY1, SX0:SX1] = 1.0
            m = np.asarray(Image.fromarray((m[..., 0] * 255).astype(np.uint8))
                           .filter(ImageFilter.GaussianBlur(70)), np.float32)[..., None] / 255.0
            a = a * (1 - m * flash) + 255.0 * (m * flash)
            a = a * (1 - flash * 0.55) + 255.0 * (flash * 0.55)
        a *= ease_in_out(seg(t, 0.0, 0.55))
        yield np.clip(a, 0, 255).astype(np.uint8)


# ───────────────────────────────────────── 엔딩 크레딧 (같은 극장)
SILENT_SLOT, GAP, LEAD, TAIL = 2.6, 0.45, 1.2, 4.2

def credits_plan(P, notes):
    """누가 언제 소감을 말하는지, 이름이 언제 화면 가운데에 올지 정한다.
       팀은 녹음 구간을 나눈 것일 뿐이라 크레딧에서는 한 팀으로 올린다."""
    entries = []
    for tk in P["teams"]:
        for c in [x for x in P["cast"] if x["team"] == tk]:
            n = notes.get(c["person"])
            entries.append(dict(person=c["person"], chars=c["chars"],
                                dur=(n["dur"] if n else 0.0), has=bool(n)))
    if not entries:
        raise SystemExit("배역이 없습니다.")

    t = LEAD
    for e in entries:
        e["slot"] = e["dur"] if e["dur"] > 0.3 else SILENT_SLOT
        e["t0"], e["t1"] = t, t + e["slot"]
        t += e["slot"] + GAP
    total = t + TAIL

    sh = SY1 - SY0
    avg = sum(e["slot"] for e in entries) / len(entries)
    speed = max(16.0, min(110.0, 336.0 / avg))     # 소감이 길수록 천천히 흐른다
    for e in entries:
        e["y"] = int(speed * ((e["t0"] + e["t1"]) / 2) + sh / 2)
    return dict(entries=entries, total=round(total, 2), speed=round(speed, 2))


def credits_tall(P, plan):
    """스크린 폭에 맞춘 세로로 긴 크레딧 판"""
    sw, sh = SX1 - SX0, SY1 - SY0
    ent, speed = plan["entries"], plan["speed"]
    th = int(speed * plan["total"] + sh) + 200
    img = Image.new("RGB", (sw, th), SCREEN)
    a = np.asarray(img, np.float32)
    rng = np.random.default_rng(4)
    a += rng.normal(0, 2.2, (th, sw, 1))
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    f_hd, f_ch, f_nm, f_no = f_serif(34, True), f_kor(21), f_serif(26), f_serif(15)
    hd_y = ent[0]["y"] - 150
    centered(d, hd_y, "C A S T", f_serif(22), (120, 112, 108), 6, sw)

    mid = sw / 2
    for e in ent:
        y = e["y"]
        ch = " · ".join(e["chars"])
        cw = d.textlength(ch, font=f_ch)
        d.text((mid - 26 - cw, y + 3), ch, font=f_ch, fill=(150, 30, 34))
        d.text((mid + 26, y), e["person"], font=f_nm, fill=INK)
        for k in range(4):                                  # 가운데 점선
            cx = mid - 18 + k * 9
            d.ellipse([cx, y + 15, cx + 2, y + 17], fill=(150, 144, 138))
        if e["has"]:
            d.text((mid + 26, y + 34), "a word", font=f_no, fill=(150, 30, 34))
    return img


def credits_screen(P, plan, tall, t):
    """스크린 한 장 — 크레딧이 흐르고, 말하는 사람 줄에 빛이 머문다"""
    sw, sh = SX1 - SX0, SY1 - SY0
    speed, total = plan["speed"], plan["total"]
    maxy = max(0, tall.size[1] - sh)
    y = int(round(min(speed * t, maxy)))
    img = tall.crop((0, y, sw, y + sh)).copy()

    arr = np.asarray(img, np.float32)
    for e in plan["entries"]:
        if not e["has"]: continue
        t0, t1 = e["t0"], e["t0"] + max(e["dur"], 0.4)
        if not (t0 - 0.45 <= t <= t1 + 0.55): continue
        amt = min(seg(t, t0 - 0.45, t0 + 0.2), 1 - seg(t, t1, t1 + 0.55))
        sy = e["y"] - y
        if sy < -70 or sy > sh + 70: continue
        rows = np.arange(sh, dtype=np.float32)[:, None, None]
        band = np.exp(-((rows - (sy + 16)) / 34.0) ** 2) * amt
        arr -= band * np.array([6, 26, 34], np.float32)     # 따뜻한 쪽으로 물들인다
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # 마지막 인사
    a = ease_out(seg(t, total - 3.4, total - 2.0))
    if a > 0.004:
        lay = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        fi, fc = f_serif(50), f_serif(50, True)
        w1 = dd.textlength("The ", font=fi); w2 = dd.textlength("END", font=fc)
        x = (sw - (w1 + w2)) / 2
        col = INK + (int(255 * a),)
        dd.text((x, sh/2 - 40), "The ", font=fi, fill=col)
        dd.text((x + w1, sh/2 - 40), "END", font=fc, fill=col)
        img = img.convert("RGBA"); img.alpha_composite(lay); img = img.convert("RGB")
    return img


def credits_frames(P, plan):
    secs = plan["total"]
    tall = credits_tall(P, plan)
    n = int(round(secs * FPS))
    for i in range(n):
        t = i / FPS
        img = draw_room(1.0)
        img = paste_screen(img, credits_screen(P, plan, tall, t), 1.0)
        img = draw_seats(img, 1.0)
        img = vignette(img)
        img = zoom_crop(img, 1.0 + 0.030 * ease_in_out(seg(t, 0.0, secs)))
        a = np.asarray(img, np.float32)
        a *= ease_in_out(seg(t, 0.0, 1.1))
        a *= 1 - ease_in_out(seg(t, secs - 1.8, secs))
        yield np.clip(a, 0, 255).astype(np.uint8)


def main():
    import imageio_ffmpeg, motion as M, music as MU
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(MC.OUT, exist_ok=True)
    P = MC.read_project()
    import sys
    secs = 6.4
    if "--credits" not in sys.argv:
        wav = M.write_wav(MU.render("warm", secs, 0.85, fade_in=0.6, fade_out=0.9),
                          os.path.join(MC.OUT, "cin.wav"))
        M.encode(title_frames(P, secs), secs, wav, os.path.join(HERE, "오프닝_극장.mp4"), ff)
        print("  오프닝_극장.mp4")
    if "--title" not in sys.argv:
        notes = MC.fetch_notes(P["key"]) if "--fetch" in sys.argv else {}
        plan = credits_plan(P, notes)
        cw = M.write_wav(MU.render("warm", plan["total"], 0.42, fade_in=2.0, fade_out=2.6),
                         os.path.join(MC.OUT, "cin_cred.wav"))
        M.encode(credits_frames(P, plan), plan["total"], cw,
                 os.path.join(HERE, "크레딧_극장.mp4"), ff)
        print(f"  크레딧_극장.mp4  ({plan['total']:.1f}초)")

if __name__ == "__main__":
    main()
