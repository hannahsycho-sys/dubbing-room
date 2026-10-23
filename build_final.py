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
import json, os, re, subprocess, sys, tempfile, urllib.request, shutil

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

LINES = []
for m in re.finditer(r'\{\s*id:\s*(\d+),\s*team:"(\w+)",\s*char:"([^"]+)",\s*s:\s*([\d.]+),\s*e:\s*([\d.]+)', seg):
    LINES.append(dict(id=int(m.group(1)), team=m.group(2), char=m.group(3),
                      s=float(m.group(4)), e=float(m.group(5))))
if not LINES:
    sys.exit("segments.js 에서 대사를 못 읽었습니다.")

argv = sys.argv[1:]
USE_ORIG = "--orig" in argv
KEEP     = "--keep" in argv
NO_TITLES= "--no-titles" in argv
ONLY     = argv[argv.index("--only")+1] if "--only" in argv else None

# ---------- 제출 목록 ----------
if not URL or not KEY:
    sys.exit("config.js 의 SUPABASE_URL / SUPABASE_ANON_KEY 가 비어 있습니다.")

def api(path):
    req = urllib.request.Request(f"{URL}/rest/v1/{path}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
    return json.load(urllib.request.urlopen(req))

print("제출 목록 가져오는 중…")
rows = api(f"submissions?project=eq.{PKEY}&select=*&order=created_at.asc")
latest = {}
for r in rows:
    latest[r["line_id"]] = r          # 나중 것이 이김
print(f"  {len(latest)} / {len(LINES)} 줄 제출됨")

wanted = [l for l in LINES if (ONLY is None or l["team"] == ONLY)]
missing = [l for l in wanted if l["id"] not in latest]
if missing:
    print(f"  ⚠ 아직 안 올라온 줄 {len(missing)}개: " +
          ", ".join(f'{l["id"]}({l["char"]})' for l in missing))
    print("    그 자리는 배경음악만 들어갑니다.")

have = [l for l in wanted if l["id"] in latest]
if not have:
    sys.exit("제출된 녹음이 하나도 없습니다.")

# ---------- 내려받기 ----------
tmp = tempfile.mkdtemp(prefix="dubmix_")
print(f"녹음 내려받는 중… ({len(have)}개)")
files = {}
for l in have:
    r = latest[l["id"]]
    url = f"{URL}/storage/v1/object/public/{BUCKET}/{r['path']}"
    dst = os.path.join(tmp, f"{l['id']:02d}.bin")
    try:
        urllib.request.urlretrieve(url, dst)
        files[l["id"]] = dst
    except Exception as e:
        print(f"  건너뜀 line {l['id']}: {e}")

# ---------- 믹스 ----------
bed = os.path.join(HERE, BGM) if (BGM and not USE_ORIG) else None
if bed and not os.path.exists(bed):
    print(f"  배경음악 {BGM} 이 없어서 원본 소리를 씁니다.")
    bed = None

video = os.path.join(HERE, VIDEO)
if not os.path.exists(video):
    sys.exit(f"영상이 없습니다: {video}")

ins, filt, mixn = [], [], []
if bed:
    ins += ["-i", bed]
else:
    ins += ["-i", video]        # 원본 소리를 깔개로
filt.append("[0:a]volume=0.9,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bed]")
mixn.append("[bed]")

for i, l in enumerate([l for l in have if l["id"] in files], start=1):
    ins += ["-i", files[l["id"]]]
    # 관리자 화면에서 맞춘 싱크 미세조정을 반영한다
    off = int(latest[l["id"]].get("offset_ms") or 0)
    d = max(0, int(round(l["s"] * 1000)) + off)
    # 따로 녹음한 목소리를 자연스럽게 잇기 :
    #   앞 묵음 제거 → 음량 평준화 → 양끝 짧은 페이드 → 제자리로 밀기
    filt.append(
        f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.025:detection=peak,"
        f"loudnorm=I=-20:TP=-2.0:LRA=11,"
        f"afade=t=in:st=0:d=0.015,"
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
    MC.make_title(P)
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

    TITLE_SEC = 4.0
    title_png = os.path.join(MC.OUT, "title.png")
    cred_png  = os.path.join(MC.OUT, "credits.png")
    speed, ctotal = sched["speed"], sched["total"]

    # 1) 타이틀 (무음)
    t_mp4 = os.path.join(tmp, "title.mp4")
    subprocess.run([FF,"-hide_banner","-loglevel","error","-y",
        "-loop","1","-framerate","30","-t",str(TITLE_SEC),"-i",title_png,
        "-f","lavfi","-t",str(TITLE_SEC),"-i","anullsrc=r=44100:cl=stereo",
        "-vf",f"fade=t=in:st=0:d=0.7,fade=t=out:st={TITLE_SEC-0.7:.2f}:d=0.7,format=yuv420p",
        "-c:v","libx264","-preset","medium","-crf","23","-r","30",
        "-c:a","aac","-b:a","192k","-shortest",t_mp4], check=True)

    # 2) 크레딧 (스크롤 + 소감 음성)
    c_mp4 = os.path.join(tmp, "credits.mp4")
    cin = ["-loop","1","-framerate","30","-t",f"{ctotal:.2f}","-i",cred_png]
    cfil = [f"[0:v]crop=1280:720:0:'min(max(0\\,{speed:.3f}*t)\\,ih-720)',"
            f"fade=t=in:st=0:d=1,fade=t=out:st={ctotal-2:.2f}:d=2,format=yuv420p[cv]"]
    amix_in, ai = [], 1
    for n in sched["notes"]:
        f = note_files.get(n["person"])
        if not f: continue
        cin += ["-i", f]
        dly = int(round(n["t0"]*1000))
        cfil.append(f"[{ai}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                    f"loudnorm=I=-20:TP=-2.0:LRA=11,adelay={dly}|{dly}[n{ai}]")
        amix_in.append(f"[n{ai}]"); ai += 1
    if amix_in:
        cfil.append("".join(amix_in)+f"amix=inputs={len(amix_in)}:duration=longest:normalize=0,"
                    f"apad,atrim=0:{ctotal:.2f},alimiter=limit=0.95[ca]")
    else:
        cin += ["-f","lavfi","-t",f"{ctotal:.2f}","-i","anullsrc=r=44100:cl=stereo"]
        cfil.append(f"[{ai}:a]anull[ca]")
    subprocess.run([FF,"-hide_banner","-loglevel","error","-y",*cin,
        "-filter_complex",";".join(cfil),"-map","[cv]","-map","[ca]",
        "-c:v","libx264","-preset","medium","-crf","23","-r","30",
        "-c:a","aac","-b:a","192k","-t",f"{ctotal:.2f}",c_mp4], check=True)

    # 3) 타이틀 + 본편 + 크레딧 이어붙이기
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
