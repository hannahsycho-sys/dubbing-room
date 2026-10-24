#!/usr/bin/env python3
"""
music.py — 오프닝·크레딧에 깔 음악을 직접 합성한다.

남의 곡을 쓰지 않고 소리를 처음부터 만들기 때문에 길이를 마음대로 맞출 수 있다.
예전 버전은 사인파만 쌓아 '미디' 같은 소리가 났다. 이번에는
  · 펠트 피아노  : 배음마다 감쇠 속도를 다르게 (높은 배음이 먼저 사라진다)
  · 현(스트링)   : 살짝 어긋난 톱니파 여러 겹 + 느린 활 긋기
  · 공간 울림    : 잡음을 지수로 감쇠시킨 임펄스와 FFT 합성곱 (진짜 리버브)
  · 스테레오     : 좌우를 조금 다르게 해 넓게

미리 들어보기:
    ~/.dubtools/bin/python music.py           # 후보 3곡을 wav 로
"""
import numpy as np, os, wave

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))


# ───────────────────────────────────────────── 기본 도구
def mid(n):            return 440.0 * 2 ** ((n - 69) / 12.0)
def t_arr(dur):        return np.arange(int(dur * SR)) / SR
def _rng(seed=11):     return np.random.default_rng(seed)

def lowpass(x, cut, sr=SR):
    """한 극 저역 통과 — 벡터로 한 번에 (루프 없이)"""
    a = np.exp(-2 * np.pi * cut / sr)
    # y[n] = (1-a)x[n] + a y[n-1]  →  지수 가중 누적
    b = 1 - a
    y = np.empty_like(x)
    acc = 0.0
    # 블록 단위로 쪼개 numpy 로 처리하기 어려워, 짧은 구간만 파이썬 루프
    for i in range(len(x)):
        acc = b * x[i] + a * acc
        y[i] = acc
    return y

def lowpass_fast(x, cut, sr=SR):
    """FFT 로 자르는 저역 통과 — 길이가 길 때 훨씬 빠르다"""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    X *= 1.0 / np.sqrt(1.0 + (f / cut) ** 4)          # 완만한 2차 기울기
    return np.fft.irfft(X, n)

def fftconv(x, ir):
    n = len(x) + len(ir) - 1
    N = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[:len(x)]
    return y

def hall(seconds=2.8, decay=1.5, cut=4200, seed=5):
    """홀 울림 임펄스 — 잡음을 지수로 줄이고 고음을 깎는다"""
    t = t_arr(seconds)
    ir = _rng(seed).normal(0, 1, len(t)) * np.exp(-t / decay)
    ir[: int(0.012 * SR)] = 0                          # 프리딜레이
    ir = lowpass_fast(ir, cut)
    return ir / (np.sqrt(np.sum(ir ** 2)) + 1e-9)

def reverb(x, mix=0.34, **kw):
    ir = hall(**kw)
    return x * (1 - mix * 0.45) + fftconv(x, ir) * mix


# ───────────────────────────────────────────── 악기
def felt_piano(freq, dur, amp=0.25, seed=3):
    """해머 소리가 살짝 섞인 부드러운 피아노"""
    t = t_arr(dur)
    out = np.zeros_like(t)
    # 배음마다 세기와 감쇠가 다르다. 높을수록 빨리 사라진다.
    for k, lvl in ((1, 1.0), (2, .36), (3, .17), (4, .085), (5, .045), (6, .022), (8, .010)):
        inharm = 1 + 0.00042 * k * k                   # 줄의 뻣뻣함
        dec = dur / (1.0 + k * 0.85)
        out += lvl * np.sin(2 * np.pi * freq * inharm * k * t) * np.exp(-t / max(dec, 0.08))
    # 해머가 줄을 때리는 아주 짧은 소리
    nl = int(0.016 * SR)
    noise = _rng(seed).normal(0, 1, nl) * np.exp(-np.linspace(0, 7, nl))
    out[:nl] += lowpass_fast(noise, 2600) * 0.16
    atk = np.minimum(t / 0.004, 1.0)
    return out * atk * amp

def strings(freq, dur, amp=0.12, detune=0.0022, seed=9):
    """활로 긋는 현 — 살짝 어긋난 톱니파 세 겹"""
    t = t_arr(dur)
    out = np.zeros_like(t)
    vib = 1 + 0.0022 * np.sin(2 * np.pi * 4.6 * t + _rng(seed).random() * 6)
    for d in (-detune, 0.0, detune):
        f = freq * (1 + d) * vib
        ph = 2 * np.pi * np.cumsum(f) / SR
        saw = 2 * (ph / (2 * np.pi) % 1.0) - 1          # 톱니
        out += saw
    out = lowpass_fast(out / 3, 2000 + freq * 2.2)
    env = np.minimum(t / 0.55, 1.0) * np.clip((dur - t) / 0.7, 0, 1)
    return out * env * amp

def sub(freq, dur, amp=0.1):
    t = t_arr(dur)
    env = np.minimum(t / 0.35, 1.0) * np.clip((dur - t) / 0.8, 0, 1)
    return np.sin(2 * np.pi * freq * t) * env * amp

def swell(dur, amp=0.07, seed=21):
    """낮게 깔리는 바람 같은 소리 — 긴장감을 만든다"""
    t = t_arr(dur)
    n = lowpass_fast(_rng(seed).normal(0, 1, len(t)), 620)
    return n * (t / dur) ** 2 * amp

def timp(dur=2.4, freq=58.0, amp=0.3, seed=17):
    """팀파니 비슷한 울림 — 음이 살짝 떨어진다"""
    t = t_arr(dur)
    f = freq * (1 + 0.22 * np.exp(-t / 0.05))
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.55)
    skin = lowpass_fast(_rng(seed).normal(0, 1, len(t)), 900) * np.exp(-t / 0.07)
    return (body + skin * 0.5) * amp


# ───────────────────────────────────────────── 쌓기 도구
def place(buf, x, at):
    i = int(at * SR)
    j = min(len(buf), i + len(x))
    if i < len(buf):
        buf[i:j] += x[: j - i]

def chord(buf, notes, at, dur, inst, amp):
    for n in notes:
        place(buf, inst(mid(n), dur, amp), at)


# ───────────────────────────────────────────── 후보 1 · 따뜻한 피아노
def cue_warm(secs):
    """잔잔하고 따뜻한 피아노 — 교실 영상에 가장 무난하다"""
    b = np.zeros(int(secs * SR))
    # Ab - Eb/G - Fm - Db  (넓게 벌린 배치)
    prog = [(0.0, 56, [63, 68, 72]), (2.0, 55, [63, 67, 72]),
            (4.0, 53, [60, 65, 68]), (6.0, 49, [56, 61, 65])]
    for k, (t0, bass, up) in enumerate(prog):
        if t0 >= secs: break
        d = min(3.6, secs - t0)
        place(b, sub(mid(bass - 12), d, 0.085), t0)
        chord(b, up, t0, d + 1.2, strings, 0.055)
        # 피아노를 한 음씩 굴려 준다
        for j, n in enumerate(up):
            place(b, felt_piano(mid(n + 12), min(2.6, secs - t0), 0.115 - j * 0.018),
                  t0 + j * 0.17)
        place(b, felt_piano(mid(bass), min(3.0, secs - t0), 0.10), t0)
    return reverb(b, 0.36, seconds=2.6, decay=1.5)


# ───────────────────────────────────────────── 후보 2 · 영화 오프닝
def cue_cinema(secs):
    """막이 오를 때 쓸, 점점 차오르는 오프닝"""
    b = np.zeros(int(secs * SR))
    place(b, swell(min(secs, 4.2), 0.075), 0.0)
    # 낮은 현이 깔리고 위로 쌓인다
    place(b, sub(mid(33), secs, 0.095), 0.0)
    chord(b, [45, 52, 57], 0.3, max(1.0, secs - 0.6), strings, 0.052)
    chord(b, [64, 69, 72], 1.6, max(1.0, secs - 1.9), strings, 0.040)
    place(b, timp(2.6, 58, 0.26), 0.25)
    place(b, timp(2.2, 58, 0.17), 2.05)
    # 제목이 드러나는 순간
    place(b, timp(3.0, 44, 0.30), 2.9)
    chord(b, [69, 76, 81], 2.95, max(1.0, secs - 3.1), strings, 0.046)
    for j, n in enumerate([81, 88]):
        place(b, felt_piano(mid(n), min(3.2, max(0.4, secs - 3.0)), 0.085 - j * 0.03),
              3.0 + j * 0.22)
    return reverb(b, 0.40, seconds=3.2, decay=1.9)


# ───────────────────────────────────────────── 후보 3 · 잔잔한 앰비언트
def cue_calm(secs):
    """거의 음악이 없는 듯한, 아주 조용한 공간"""
    b = np.zeros(int(secs * SR))
    place(b, sub(mid(40), secs, 0.075), 0.0)
    chord(b, [59, 64, 67], 0.0, secs, strings, 0.034)
    notes = [76, 71, 79, 74, 83, 72]
    t = 0.8
    i = 0
    while t < secs - 0.5:
        place(b, felt_piano(mid(notes[i % len(notes)]), min(4.0, secs - t), 0.10), t)
        t += 2.3 if i % 2 == 0 else 1.5
        i += 1
    return reverb(b, 0.46, seconds=3.6, decay=2.4)


CUES = {"warm": cue_warm, "cinema": cue_cinema, "calm": cue_calm}


# ───────────────────────────────────────────── 마무리
def stereo(x, width=0.02):
    """좌우를 아주 조금 어긋내 넓게 들리게"""
    d = int(width * SR)
    l = x.copy()
    r = np.concatenate([np.zeros(d), x[:-d]]) if d else x.copy()
    return np.stack([l, r], 1)

def finish(x, secs, fade_in=0.8, fade_out=1.6, vol=1.0):
    t = t_arr(secs)[: len(x)]
    x = x[: len(t)] * np.minimum(t / max(fade_in, 1e-3), 1.0)
    x *= np.clip((secs - t) / max(fade_out, 1e-3), 0, 1)
    x = np.tanh(x * 1.2) * 0.9                      # 아주 부드러운 포화
    pk = float(np.max(np.abs(x))) or 1.0
    return x / pk * 0.82 * vol

def render(kind, secs, vol=1.0, fade_in=0.8, fade_out=1.6):
    x = CUES[kind](secs)
    return stereo(finish(x, secs, fade_in, fade_out, vol))

def write_wav(st, path):
    s = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(s.tobytes())
    return path


def main():
    out = os.path.join(HERE, "_credits"); os.makedirs(out, exist_ok=True)
    for k, secs in (("warm", 9.0), ("cinema", 9.0), ("calm", 9.0)):
        p = write_wav(render(k, secs), os.path.join(HERE, f"음악후보_{k}.wav"))
        print("  ", os.path.basename(p))

if __name__ == "__main__":
    main()
