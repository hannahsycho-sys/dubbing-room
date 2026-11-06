#!/usr/bin/env python3
"""
build_final.py — 10명이 올린 녹음을 모아서 최종 더빙 영상 한 파일로 만듭니다.

    python3 build_final.py

하는 일
  1. Supabase 에서 제출된 녹음 목록을 읽습니다
  2. 녹음 파일을 전부 내려받습니다
  3. 배경음악 트랙 위에 각 대사를 타임코드대로 얹습니다
  4. 영상과 합쳐 final_dub.mp4 로 저장합니다

옵션
  --orig    배경음악 대신 원본 소리를 깔기 (분리 전 음원으로 확인하고 싶을 때)
  --only white|black   한 팀 구간만 만들기
  --keep    중간 파일을 지우지 않기
"""
import json, math, os, re, subprocess, sys, tempfile, urllib.request, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- ffmpeg 찾기 ----------
def find_ffmpeg():
    for c in (shutil.which("ffmpeg"),
              os.path.expanduser("~/.dubtools/lib/python3.9/site-packages/"
                                 "imageio_ffmpeg/binaries/ffmpeg-macos-x86_64-v7.1")):
        if c and os.path.exists(c):
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg 을 찾지 못했습니다.  ~/.dubtools/bin/python -m pip install imageio-ffmpeg")
FF = find_ffmpeg()

# ---------- config.js / segments.js 읽기 ----------
def jsval(src, key):
    m = re.search(rf'{key}\s*:\s*"([^"]*)"', src)
    return m.group(1) if m else ""

cfg = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
URL    = jsval(cfg, "SUPABASE_URL")
KEY    = jsval(cfg, "SUPABASE_ANON_KEY")
BUCKET = jsval(cfg, "BUCKET") or "takes"

seg = open(os.path.join(HERE, "segments.js"), encoding="utf-8").read()
PKEY  = jsval(seg, "key")
VIDEO = jsval(seg, "video")
BGM   = jsval(seg, "videoBgm")
DUB_END = float(re.search(r'dubEnd:\s*([\d.]+)', seg).group(1))

def mixval(key, default):
    m = re.search(rf'{key}:\s*([\d.]+)', seg)
    return float(m.group(1)) if m else default
BGM_VOL   = mixval("bgmVolume",   0.9)

def bgm_ranges():
    """구간별 배경음악 크기 —  bgmRanges: [[0,11,20], [46,68,12]]
    관리 페이지의 '구간별 음악' 과 같은 값을 쓰면 들어본 대로 나온다."""
    m = re.search(r'bgmRanges:\s*\[(.*?)\]\s*,?\s*$', seg, re.M | re.S)
    if not m:
        return []
    out = []
    for a, b, v in re.findall(r'\[\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\]', m.group(1)):
        a, b, v = float(a), float(b), float(v)
        if b > a:
            out.append((a, b, v))
    return out

BGM_RANGES = bgm_ranges()

def bgm_filter():
    """구간마다 배경음악 크기를 바꾼다.

    크기 차이가 클수록 천천히 넘어간다 — 짧게 끊으면 '울컥' 하고 티가 난다.
    방향에 따라 넘어가는 자리도 다르다.
      줄일 때 : 경계까지는 그대로 두고 경계부터 내린다 (앞의 꼬리를 안 자른다)
      키울 때 : 경계 전에 미리 올려 둔다 (구간이 시작될 때 이미 제 크기)
    브라우저 쪽 bgmFade() / teScheduleBed() 와 같은 규칙이다.
    """
    if not BGM_RANGES:
        return f"volume={BGM_VOL}"

    def level(t):                      # 겹치면 먼저 쓴 구간이 이긴다
        for a, b, v in BGM_RANGES:
            if a <= t < b:
                return v
        return BGM_VOL

    def fade(v0, v1):
        d = abs(20 * math.log10(max(v1, 1e-4) / max(v0, 1e-4)))
        return max(0.25, min(2.2, d * 0.09))

    edges = sorted({0.0} | {t for a, b, _ in BGM_RANGES for t in (a, b) if 0 < t < DUB_END})
    marks = [(0.0, level(1e-6))]       # (시각, 그 시각의 값)
    for t in edges:
        if t <= 0:
            continue
        v0, v1 = level(t - 1e-6), level(t + 1e-6)
        if abs(v1 - v0) < 1e-9:
            continue
        F = fade(v0, v1)
        if v1 < v0:
            marks += [(t, v0), (min(DUB_END, t + F), v1)]
        else:
            marks += [(max(0.0, t - F), v0), (t, v1)]
    marks.sort(key=lambda m: m[0])
    marks.append((DUB_END + 1.0, marks[-1][1]))

    parts = []
    for i in range(len(marks) - 1):
        (t0, v0), (t1, v1) = marks[i], marks[i + 1]
        if t1 <= t0 + 1e-6:
            continue
        if abs(v1 - v0) < 1e-9:
            parts.append(f"between(t,{t0:g},{t1:g})*{v0:g}")
        else:
            parts.append(f"between(t,{t0:g},{t1:g})*({v0:g}+({v1:g}-{v0:g})*(t-{t0:g})/{t1-t0:g})")
    return "volume='" + "+".join(parts) + "':eval=frame"


filt.append(f"[0:a]{bgm_filter()},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bed]")
if BGM_RANGES:
    print("  배경음악 구간별 크기: " + ", ".join(f"{a:g}–{b:g}초 {v:g}배" for a, b, v in BGM_RANGES)
          + f" (그 밖은 {BGM_VOL:g}배)")
mixn.append("[bed]")

for i, l in enumerate([l for l in have if l["id"] in files], start=1):
    ins += ["-i", files[l["id"]]]
    # 관리자 화면에서 맞춘 싱크 미세조정을 반영한다
    off = int(latest[l["id"]].get("offset_ms") or 0)
    d = max(0, int(round(l["s"] * 1000)) + off)
    # 관리자 화면에서 맞춘 사람별 볼륨 보정
    gdb = float(latest[l["id"]].get("gain_db") or 0)
    gfil = f"volume={gdb:+.1f}dB," if abs(gdb) > 0.05 else ""
    cfil_ = clean_of(latest[l["id"]])
    tfil_ = trim_of(latest[l["id"]])
    efil_ = eq_of(latest[l["id"]])
    sfil_ = speed_of(latest[l["id"]])
    # 따로 녹음한 목소리를 자연스럽게 잇기 :
    #   앞 묵음 제거 → 음량 평준화 → 양끝 짧은 페이드 → 제자리로 밀기
    filt.append(
        f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"{tfil_}"
        f"{sfil_}"
        f"silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.025:detection=peak,"
        f"{cfil_}"
        f"{efil_}"
        f"{level_filter(files[l['id']], tfil_ + sfil_)}"
        # 양끝을 부드럽게 — 끝쪽은 길이를 몰라도 되게 뒤집어서 페이드한다
        f"afade=t=in:st=0:d={V_FADE_I:.3f},"
        f"areverse,afade=t=in:st=0:d={V_FADE_O:.3f},areverse,"
        f"{gfil}"
        f"volume={VOICE_VOL},"
        f"adelay={d}|{d}[v{i}]")
    mixn.append(f"[v{i}]")

n = len(mixn)
filt.append("".join(mixn) + f"amix=inputs={n}:duration=first:normalize=0,"
            "alimiter=limit=0.95,aformat=sample_fmts=fltp[out]")

mixed = os.path.join(tmp, "mixed.wav")
print("소리 합치는 중…")
cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", *ins,
       "-filter_complex", ";".join(filt), "-map", "[out]",
       "-t", str(DUB_END), "-c:a", "pcm_s16le", mixed]
subprocess.run(cmd, check=True)

body = os.path.join(tmp, "body.mp4")
print("영상과 합치는 중…")
subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y",
                "-i", video, "-i", mixed,
                "-map", "0:v:0", "-map", "1:a:0", "-t", str(DUB_END),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", body], check=True)

# ---------- 자막 ----------
# 파일은 언제나 만들어 둔다 (유튜브 업로드·편집 프로그램에서 쓸 수 있게)
import make_subs
sys.argv = ["make_subs", "--lang", SUBLANG]
try:
    make_subs.main()
except SystemExit:
    pass

if SUBS:
    print("자막을 영상에 새기는 중…")
    ass = os.path.join(HERE, "자막.ass")
    subbed = os.path.join(tmp, "body_sub.mp4")
    esc_ass = ass.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", body,
                    "-vf", f"subtitles='{esc_ass}',format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "copy", "-movflags", "+faststart", subbed], check=True)
    body = subbed

suffix = ('_' + ONLY) if ONLY else ''
# 1) 더빙만 입힌 본편 — 항상 따로 저장한다 (어차피 중간에 만들어지므로 추가 비용이 없다)
plain = os.path.join(HERE, f"본편만{suffix}.mp4")
shutil.copyfile(body, plain)
made = [plain]

# 2) 오프닝 타이틀 + 엔딩 크레딧까지 붙인 완성본
out = os.path.join(HERE, f"완성본{suffix}.mp4")
if NO_TITLES:
    out = None
else:
    import make_credits as MC
    print("타이틀·크레딧 만드는 중…")
    os.makedirs(MC.OUT, exist_ok=True)
    P = MC.read_project()
    voices = MC.fetch_notes(P["key"])
    sched = MC.make_credits(P, voices)

    # 소감 음성 내려받기
    note_files = {}
    for n in sched["notes"]:
        v = voices.get(n["person"])
        if not v or not n["has"]: continue
        dst = os.path.join(tmp, f"note_{abs(hash(n['person']))%10**8}.bin")
        try:
            urllib.request.urlretrieve(v["url"], dst); note_files[n["person"]] = dst
        except Exception as e:
            print(f"  소감 건너뜀 {n['person']}: {e}")

    import motion as MO, hand as HD, music as MU
    speed, ctotal = sched["speed"], sched["total"]
    TCUE, CCUE = MO.CUE_TITLE, MO.CUE_CRED
    TVOL, CVOL = MO.VOL_TITLE, MO.VOL_CRED
    DUCK = float(MO._mix("musicDuck", 0.45))

    # 1) 오프닝
    #    직접 만든 오프닝 파일(캡컷 등)이 있으면 그것을 쓴다.
    #    video/오프닝.mp4  또는  오프닝.mp4  를 찾는다.
    t_mp4 = os.path.join(tmp, "title.mp4")
    mine = next((f for f in (os.path.join(HERE, "video", "오프닝.mp4"),
                             os.path.join(HERE, "오프닝.mp4"))
                 if os.path.exists(f)), None)
    if mine:
        # 길이·크기·프레임수를 본편에 맞춰 통일하고, 소리가 없으면 무음 트랙을 넣는다
        has_audio = subprocess.run(
            [FF.replace("ffmpeg", "ffprobe") if False else FF, "-hide_banner", "-i", mine],
            capture_output=True, text=True).stderr.find("Audio:") >= 0
        dur = probe_dur(mine)
        TITLE_SEC = dur
        print(f"  오프닝: 직접 만드신 파일을 씁니다 ({os.path.basename(mine)}, {dur:.1f}초)")
        cmd = [FF, "-hide_banner", "-loglevel", "error", "-y", "-i", mine]
        if not has_audio:
            cmd += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
            print("    (소리가 없어 무음으로 넣습니다)")
        cmd += ["-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                       "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", "-shortest", t_mp4]
        subprocess.run(cmd, check=True)
    else:
        print(f"  오프닝 {TITLE_SEC:.1f}초 그리는 중…")
        t_wav = MO.write_wav(MU.render(TCUE, TITLE_SEC, TVOL, fade_in=0.6, fade_out=0.9),
                             os.path.join(tmp, "title_music.wav"))
        MO.encode(HD.title_frames(P, TITLE_SEC), TITLE_SEC, t_wav, t_mp4, FF)

    # 2) 크레딧 소리 — 소감 목소리 + 음악(목소리가 나오면 음악이 알아서 눌린다)
    c_wav = MO.write_wav(MU.render(CCUE, ctotal, CVOL, fade_in=2.0, fade_out=2.6),
                         os.path.join(tmp, "credits_music.wav"))
    cin, cfil, amix_in, ai = ["-i", c_wav], [], [], 1
    for n in sched["notes"]:
        f = note_files.get(n["person"])
        if not f: continue
        cin += ["-i", f]
        dly = int(round(n["t0"] * 1000))
        nv_ = voices.get(n["person"]) or {}
        ng = float(nv_.get("gain_db") or 0)
        ngf = f"volume={ng:+.1f}dB," if abs(ng) > 0.05 else ""
        ncl = clean_of(nv_)
        neq = eq_of(nv_)
        nsp = speed_of(nv_)
        ntr = trim_of(dict(nv_, dur=n.get("dur") or nv_.get("dur") or 0))
        cfil.append(f"[{ai}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                    f"{ntr}{nsp}{ncl}{neq}{level_filter(f, ntr+nsp)}{ngf}adelay={dly}|{dly}[n{ai}]")
        amix_in.append(f"[n{ai}]"); ai += 1

    c_audio = os.path.join(tmp, "credits_audio.wav")
    if amix_in:
        # 감지기를 키워(level_sc) 문턱을 확실히 넘게 해야 실제로 눌린다
        ratio = max(2.0, min(20.0, 2.0 + DUCK * 16.0))
        lvsc  = max(1.0, min(12.0, 1.0 + DUCK * 10.0))
        cfil.append("".join(amix_in) + f"amix=inputs={len(amix_in)}:duration=longest:normalize=0,"
                    f"apad,atrim=0:{ctotal:.2f},alimiter=limit=0.95[vo]")
        cfil.append("[vo]asplit=2[vo1][vosc]")
        cfil.append(f"[0:a][vosc]sidechaincompress=threshold=0.02:ratio={ratio:.2f}:"
                    f"level_sc={lvsc:.2f}:attack=20:release=500:makeup=1:knee=4[mus]")
        cfil.append("[vo1][mus]amix=inputs=2:duration=first:normalize=0,"
                    "alimiter=limit=0.95[ca]")
    else:
        cfil.append(f"[0:a]apad,atrim=0:{ctotal:.2f}[ca]")
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *cin,
                    "-filter_complex", ";".join(cfil), "-map", "[ca]",
                    "-t", f"{ctotal:.2f}", "-c:a", "pcm_s16le", c_audio], check=True)

    # 3) 크레딧 그림
    print(f"  크레딧 {ctotal:.1f}초 그리는 중…")
    c_mp4 = os.path.join(tmp, "credits.mp4")
    MO.encode(MO.credits_frames(P, sched, ctotal), ctotal, c_audio, c_mp4, FF)

    # 4) 오프닝 + 본편 + 크레딧 이어붙이기
    print("이어붙이는 중…")
    subprocess.run([FF,"-hide_banner","-loglevel","error","-y",
        "-i",t_mp4,"-i",body,"-i",c_mp4,
        "-filter_complex",
        "[0:v]scale=1280:720,setsar=1[v0];[1:v]scale=1280:720,setsar=1[v1];[2:v]scale=1280:720,setsar=1[v2];"
        "[v0][0:a][v1][1:a][v2][2:a]concat=n=3:v=1:a=1[v][a]",
        "-map","[v]","-map","[a]",
        "-c:v","libx264","-preset","medium","-crf","23","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k","-movflags","+faststart",out], check=True)
    print(f"  타이틀 {TITLE_SEC:.0f}초 + 본편 {DUB_END:.1f}초 + 크레딧 {ctotal:.0f}초")

    if SUBS_SOFT:          # 끄고 켤 수 있는 자막 트랙을 넣는다 (타이틀 길이만큼 밀어서)
        print("끄고 켤 수 있는 자막 넣는 중…")
        sys.argv = ["make_subs", "--lang", SUBLANG, "--offset", str(TITLE_SEC), "--suffix", "_최종"]
        try: make_subs.main()
        except SystemExit: pass
        srt = os.path.join(HERE, "자막_최종.srt")
        tagged = os.path.join(tmp, "with_subs.mp4")
        subprocess.run([FF,"-hide_banner","-loglevel","error","-y","-i",out,"-i",srt,
            "-map","0","-map","1","-c","copy","-c:s","mov_text",
            "-metadata:s:s:0","language=kor","-movflags","+faststart",tagged], check=True)
        shutil.move(tagged, out)
    made.append(out)

if not KEEP:
    shutil.rmtree(tmp, ignore_errors=True)
else:
    print(f"중간 파일: {tmp}")

print()
for f in made:
    mb = os.path.getsize(f) / 1024 / 1024
    tag = "타이틀·크레딧 포함" if f == out else "더빙만 (확인용)"
    print(f"✅ {os.path.basename(f):<22} {mb:6.1f} MB   {tag}")
if missing:
    print(f"\n   ⚠ 아직 {len(missing)}줄은 비어 있습니다 — 다 모이면 다시 돌리세요")
