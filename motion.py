#!/usr/bin/env python3
"""
motion.py — 오프닝(막이 오르는 장면)과 엔딩 크레딧을 '한 장 한 장 그려서' 영상으로 만든다.

예전에는 PNG 한 장에 페이드만 걸었다. 이제는 30fps 로 프레임을 직접 그리고
ffmpeg 에 그대로 흘려 넣는다(임시 PNG 를 만들지 않는다).

음악도 여기서 직접 합성한다 — 남의 곡을 쓰지 않고 사인파를 쌓아 만든 것이라
저작권 걱정 없이 마음대로 길이를 맞출 수 있다.

혼자 미리 보고 싶을 때:
    ~/.dubtools/bin/python motion.py --preview          # 소감 없이
    ~/.dubtools/bin/python motion.py --preview --fetch  # 서버 소감까지 받아서
"""
import json, math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import make_credits as MC          # 대본 읽기 · 소감 시간표 계산은 그대로 쓴다

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1280, 720, 30
SR = 44100

AMBER = (240, 165, 0)
INK   = (240, 236, 226)
DIM   = (147, 141, 126)
BG    = (10, 10, 8)

VELVET = (104, 20, 26)         # 막 색 (짙은 다홍)
GOLD   = (198, 150, 62)

font = MC.font                 # AppleSDGothicNeo


# ════════════════════════════════════════════════ 거들어 주는 것들
def ease_out(x):      return 1 - (1 - x) ** 3
def ease_in_out(x):   return 3*x*x - 2*x*x*x
def clamp01(x):       return max(0.0, min(1.0, x))

def seg(t, t0, t1):
    """t0~t1 구간을 0~1 로 바꾼다 (밖이면 0 또는 1)"""
    if t1 <= t0: return 1.0 if t >= t1 else 0.0
    return clamp01((t - t0) / (t1 - t0))

def to_rgba(img):
    return img if img.mode == "RGBA" else img.convert("RGBA")

def over(base, layer, alpha=1.0):
    """numpy float 배경 위에 RGBA PIL 이미지를 알파 합성"""
    if alpha <= 0.001: return base
    a = np.asarray(layer, dtype=np.float32)
    rgb, al = a[..., :3], a[..., 3:4] / 255.0 * alpha
    return base * (1 - al) + rgb * al


# ════════════════════════════════════════════════ 무대 · 막
def stage_bg():
    """막 뒤의 무대 — 가운데가 은은하게 밝은 어두운 공간"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H * 0.52
    r = np.sqrt(((xx - cx) / (W * 0.62)) ** 2 + ((yy - cy) / (H * 0.78)) ** 2)
    glow = np.exp(-(r ** 2) * 2.1)
    bg = np.zeros((H, W, 3), np.float32)
    bg[..., 0] = BG[0] + glow * 72
    bg[..., 1] = BG[1] + glow * 46
    bg[..., 2] = BG[2] + glow * 18
    # 바닥 쪽 풋라이트
    foot = np.exp(-((yy - H * 0.98) / 90.0) ** 2) * np.exp(-((xx - cx) / (W * 0.5)) ** 2)
    bg[..., 0] += foot * 46; bg[..., 1] += foot * 30; bg[..., 2] += foot * 10
    return bg


def velvet_panel(w):
    """주름이 잡힌 벨벳 한 쪽 (w 픽셀 폭). 오른쪽 끝이 무대 안쪽."""
    xx = np.arange(w, dtype=np.float32)
    folds = 0.60 + 0.40 * (0.5 + 0.5 * np.cos(xx / 26.0))        # 촘촘한 주름
    folds *= 0.80 + 0.20 * (0.5 + 0.5 * np.cos(xx / 123.0 + 1.1))  # 큰 덩어리 음영
    folds = folds[None, :]
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    vert = 1.08 - 0.42 * yy ** 1.5                                 # 아래로 갈수록 어둡게
    shade = folds * vert
    p = np.empty((H, w, 3), np.float32)
    for i, c in enumerate(VELVET):
        p[..., i] = c * shade
    p[..., 0] += folds[0][None, :] * 16                            # 주름 끝 붉은 반사
    # 안쪽(무대 쪽) 모서리에 빛이 걸린다
    edge = np.exp(-((xx - (w - 1)) / 30.0) ** 2)[None, :]
    for i, c in enumerate((255, 214, 150)):
        p[..., i] += edge * c * 0.20
    return p


def valance():
    """천장에 걸린 주름 천 (항상 보인다)"""
    vh = 96
    xx = np.arange(W, dtype=np.float32)
    folds = 0.58 + 0.42 * (0.5 + 0.5 * np.cos(xx / 30.0))
    yy = np.linspace(0, 1, vh, dtype=np.float32)[:, None]
    shade = folds[None, :] * (1.12 - 0.55 * yy ** 1.3)
    v = np.empty((vh, W, 4), np.float32)
    for i, c in enumerate(VELVET):
        v[..., i] = c * shade
    v[..., 0] += folds[None, :] * 14
    # 아래쪽을 물결 모양으로 잘라낸다
    scall = (np.cos(xx / 30.0) * 0.5 + 0.5) * 16 + vh - 26
    rows = np.arange(vh, dtype=np.float32)[:, None]
    a = np.clip(scall[None, :] - rows, 0, 1) * 255
    v[..., 3] = a
    # 끝단 금색 선
    band = np.clip(1.6 - np.abs(scall[None, :] - rows - 1.0), 0, 1)
    for i, c in enumerate(GOLD):
        v[..., i] = v[..., i] * (1 - band) + c * band
    return Image.fromarray(np.clip(v, 0, 255).astype(np.uint8))


def draw_curtain(frame, open_amt, panel, val_img):
    """open_amt 0=닫힘 1=활짝. 두 폭이 양옆으로 갈라진다."""
    half = W // 2
    cw = int(round(half * (1.0 - open_amt)))
    if cw > 0:
        src = panel[:, half - cw:half]                      # 안쪽 모서리를 유지한 채 바깥으로 빠진다
        frame[:, 0:cw] = src
        frame[:, W - cw:W] = src[:, ::-1]
        # 막이 무대에 드리우는 그림자
        sh = min(70, max(0, W - 2 * cw))
        if sh > 2:
            g = np.linspace(0.42, 1.0, sh, dtype=np.float32)[None, :, None]
            frame[:, cw:cw + sh] *= g
            frame[:, W - cw - sh:W - cw] *= g[:, ::-1]
    vh = val_img.size[1]
    frame[:vh] = over(frame[:vh], val_img)
    return frame


# ════════════════════════════════════════════════ 글자 레이어
def title_layers(P):
    """타이틀 글자들을 미리 한 장씩 그려 둔다 (매 프레임 다시 안 그리게)"""
    def blank(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))
    def center(d, y, text, f, fill, spacing=0):
        if spacing:
            total = sum(d.textlength(c, font=f) + spacing for c in text) - spacing
            x = (W - total) / 2
            for c in text:
                d.text((x, y), c, font=f, fill=fill); x += d.textlength(c, font=f) + spacing
        else:
            d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

    full  = P["title"]
    title = full.split("—")[0].strip() or full
    sub   = full.split("—")[1].strip() if "—" in full else ""

    L = {}
    im = blank(); d = ImageDraw.Draw(im)
    center(d, 236, "S O R I T U N E   D U B B I N G", font(23, True), AMBER, spacing=3)
    L["kick"] = im

    im = blank(); d = ImageDraw.Draw(im)
    center(d, 292, title, font(66, True), INK)
    L["title"] = im
    L["glow"]  = im.filter(ImageFilter.GaussianBlur(14))

    im = blank(); d = ImageDraw.Draw(im)
    if sub: center(d, 382, sub, font(30), DIM)
    d.line([(W // 2 - 150, 452), (W // 2 + 150, 452)], fill=(78, 70, 52), width=1)
    center(d, 480, "플로라 팀", font(25), AMBER)
    L["sub"] = im
    return L


def light_sweep(prog):
    """글자 위를 한 번 지나가는 빛 — 알파 마스크로 쓴다"""
    x = np.arange(W, dtype=np.float32)
    c = -260 + prog * (W + 520)
    return np.exp(-((x - c) / 120.0) ** 2)[None, :, None]


# ════════════════════════════════════════════════ 오프닝 프레임
def title_frames(P, secs):
    """막이 오르고 제목이 드러나는 장면"""
    bg    = stage_bg()
    panel = velvet_panel(W // 2)
    val   = valance()
    L     = title_layers(P)

    OPEN0, OPEN1 = 0.70, 3.00          # 막이 갈라지는 구간
    n = int(round(secs * FPS))
    for i in range(n):
        t = i / FPS
        f = bg.copy()

        # 조명이 서서히 올라온다
        f *= 0.18 + 0.82 * ease_in_out(seg(t, 0.0, 1.5))

        # 제목 (막이 반쯤 열릴 때부터)
        ta = ease_out(seg(t, 1.55, 2.85))
        if ta > 0.002:
            rise = int(round((1 - ta) * 16))
            lay = L["title"] if rise == 0 else L["title"].transform(
                (W, H), Image.AFFINE, (1, 0, 0, 0, 1, -rise), resample=Image.BILINEAR)
            f = over(f, L["glow"], ta * 0.45)
            f = over(f, lay, ta)
            sw = seg(t, 2.1, 3.4)
            if 0.001 < sw < 0.999:                      # 빛이 한 번 스친다
                m = np.asarray(lay, np.float32)[..., 3:4] / 255.0
                f += m * light_sweep(sw) * np.array([255, 232, 186], np.float32) * 0.55

        f = over(f, L["kick"], ease_out(seg(t, 2.35, 3.25)))
        f = over(f, L["sub"],  ease_out(seg(t, 2.95, 3.95)))

        # 막
        f = draw_curtain(f, 0.88 * ease_in_out(seg(t, OPEN0, OPEN1)), panel, val)

        # 앞뒤 암전
        f *= ease_in_out(seg(t, 0.0, 0.45))
        f *= 1 - ease_in_out(seg(t, secs - 0.85, secs))

        yield np.clip(f, 0, 255).astype(np.uint8)


# ════════════════════════════════════════════════ 엔딩 크레딧 프레임
def credits_tall(P, sched):
    """세로로 긴 크레딧 판 한 장 (스크롤해서 보여 준다)"""
    MC.make_credits(P, {n["person"]: {"dur": n["dur"], "url": ""}
                        for n in sched["notes"] if n["has"]})
    return Image.open(os.path.join(MC.OUT, "credits.png")).convert("RGB")


def vignette_mask():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W/2) / (W*0.72))**2 + ((yy - H/2) / (H*0.76))**2)
    return np.clip(1.08 - 0.52 * r**2.1, 0.25, 1.0)[..., None]


def credits_frames(P, sched, secs):
    tall  = np.asarray(credits_tall(P, sched), np.float32)
    speed = sched["speed"]
    vign  = vignette_mask()
    maxy  = max(0, tall.shape[0] - H)
    rng   = np.random.default_rng(7)
    grain = rng.normal(0, 1, (H, W, 1)).astype(np.float32)

    # 바닥에서 올라오는 은은한 무대 빛
    yy = np.arange(H, dtype=np.float32)[:, None, None]
    xx = np.arange(W, dtype=np.float32)[None, :, None]
    floor_glow = (np.exp(-((yy - H*1.02) / 230.0) ** 2)
                  * np.exp(-((xx - W/2) / (W*0.46)) ** 2)
                  * np.array([30, 19, 7], np.float32))

    bar = 42                                   # 시네마스코프 느낌의 위아래 검은 띠
    n = int(round(secs * FPS))
    for i in range(n):
        t = i / FPS
        y = int(round(min(speed * t, maxy)))
        f = tall[y:y + H].copy()
        if f.shape[0] < H:                     # 끝에서 모자라면 검게 채운다
            f = np.vstack([f, np.zeros((H - f.shape[0], W, 3), np.float32)])

        # 지금 소감이 나오는 사람 줄에 따뜻한 빛을 얹는다
        for e in sched["notes"]:
            if not e["has"]: continue
            t0, t1 = e["t0"], e["t0"] + max(e["dur"], 0.4)
            if not (t0 - 0.45 <= t <= t1 + 0.55): continue
            a = min(seg(t, t0 - 0.45, t0 + 0.2), 1 - seg(t, t1, t1 + 0.55))
            sy = e["y"] - y
            if sy < -90 or sy > H + 90: continue
            rows = np.arange(H, dtype=np.float32)[:, None, None]
            band = np.exp(-((rows - (sy + 22)) / 44.0) ** 2) * a
            f += band * np.array([150, 104, 24], np.float32)

        f *= vign
        f += floor_glow
        f += grain * 3.2                       # 아주 옅은 필름 그레인
        f[:bar] = 0; f[H - bar:] = 0

        f *= ease_in_out(seg(t, 0.0, 1.1))
        f *= 1 - ease_in_out(seg(t, secs - 2.4, secs))
        yield np.clip(f, 0, 255).astype(np.uint8)


# ════════════════════════════════════════════════ 음악 (직접 합성)
def _note(f, t, amp, attack, decay):
    env = np.minimum(t / max(attack, 1e-3), 1.0) * np.exp(-t / decay)
    env[t < 0] = 0
    w = (np.sin(2*np.pi*f*t) + 0.34*np.sin(4*np.pi*f*t) + 0.14*np.sin(6*np.pi*f*t))
    return w * env * amp

def _mid(n): return 440.0 * 2 ** ((n - 69) / 12.0)

def _reverb(x, mix=0.34):
    y = x.copy()
    for d, g in ((0.029, .50), (0.053, .38), (0.081, .29), (0.127, .21), (0.193, .15), (0.281, .10)):
        k = int(d * SR)
        y[k:] += x[:-k] * g * mix
    # 한 극 저역 통과 — 울림을 부드럽게
    a = 0.30
    out = np.empty_like(y); acc = 0.0
    for i in range(0, len(y), 4096):             # 블록으로 나눠 빠르게
        blk = y[i:i+4096]
        f = np.empty_like(blk)
        for j, v in enumerate(blk):
            acc = acc + a * (v - acc); f[j] = acc
        out[i:i+4096] = f
    return out

def _chords(prog, secs):
    """prog = [(시작초, [미디번호...]), ...] 를 깔린 패드로"""
    t = np.arange(int(secs * SR)) / SR
    out = np.zeros_like(t)
    for k, (t0, notes) in enumerate(prog):
        t1 = prog[k+1][0] if k+1 < len(prog) else secs
        rel = t - t0
        for j, n in enumerate(notes):
            out += _note(_mid(n), rel, 0.085 / (1 + j*0.35), 0.55, (t1 - t0) * 1.9)
    return out

def music_title(secs):
    prog = [(0.0, [57, 60, 64]), (2.1, [53, 57, 60]), (4.0, [48, 55, 60, 64])]
    x  = _chords(prog, secs)
    t  = np.arange(int(secs * SR)) / SR
    x += _note(_mid(36), t, 0.10, 0.9, 7.0)                      # 저음 드론
    x += _note(_mid(81), t - 1.6, 0.075, 0.004, 2.6)             # 제목 드러날 때 종소리
    x += _note(_mid(88), t - 2.9, 0.045, 0.004, 2.0)
    x = _reverb(x, 0.40)
    x *= np.minimum(t / 0.6, 1.0)
    x *= np.clip((secs - t) / 0.9, 0, 1)
    return x

def music_credits(secs):
    bar, prog, t0 = 3.6, [], 0.0
    cycle = [[57, 60, 64], [53, 57, 60], [55, 59, 62], [48, 55, 60]]
    i = 0
    while t0 < secs:
        prog.append((t0, cycle[i % len(cycle)])); t0 += bar; i += 1
    x = _chords(prog, secs) * 0.9
    t = np.arange(int(secs * SR)) / SR
    x += _note(_mid(36), t, 0.07, 1.2, secs)
    for k in range(int(secs // 7.2) + 1):                        # 가끔 울리는 종
        x += _note(_mid(84 if k % 2 else 79), t - (3.0 + k*7.2), 0.034, 0.004, 2.4)
    x = _reverb(x, 0.42)
    x *= np.minimum(t / 2.0, 1.0)
    x *= np.clip((secs - t) / 2.6, 0, 1)
    return x

def write_wav(x, path, vol=1.0):
    x = np.asarray(x, np.float32) * vol
    pk = float(np.max(np.abs(x))) or 1.0
    if pk > 0.97: x = x / pk * 0.97
    s = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.repeat(s[:, None], 2, 1).tobytes())
    return path


# ════════════════════════════════════════════════ 프레임 → mp4
def encode(frames, secs, wav, out, ff, extra_in=None, extra_filter=None, loglevel="error"):
    """frames 제너레이터를 ffmpeg 표준입력으로 흘려 넣는다 (임시 PNG 없음)"""
    cmd = [ff, "-hide_banner", "-loglevel", loglevel, "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav]
    if extra_in: cmd += extra_in
    if extra_filter:
        cmd += ["-filter_complex", extra_filter, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
            "-t", f"{secs:.2f}", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fr in frames:
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg 인코딩 실패")
    return out


# ════════════════════════════════════════════════ 미리보기
def main():
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(MC.OUT, exist_ok=True)
    P = MC.read_project()
    notes = MC.fetch_notes(P["key"]) if "--fetch" in sys.argv else {}
    sched = MC.make_credits(P, notes)

    tsec = 6.6
    print(f"오프닝 {tsec}초 그리는 중…")
    write_wav(music_title(tsec), os.path.join(MC.OUT, "title.wav"))
    encode(title_frames(P, tsec), tsec, os.path.join(MC.OUT, "title.wav"),
           os.path.join(HERE, "미리보기_오프닝.mp4"), ff)

    csec = sched["total"]
    print(f"크레딧 {csec:.1f}초 그리는 중…")
    write_wav(music_credits(csec), os.path.join(MC.OUT, "credits.wav"))
    encode(credits_frames(P, sched, csec), csec, os.path.join(MC.OUT, "credits.wav"),
           os.path.join(HERE, "미리보기_크레딧.mp4"), ff)
    print("  미리보기_오프닝.mp4 / 미리보기_크레딧.mp4")

if __name__ == "__main__":
    main()
