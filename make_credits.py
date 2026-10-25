#!/usr/bin/env python3
"""
make_credits.py — 오프닝 타이틀과 엔딩 크레딧 이미지를 만든다.

build_final.py 가 자동으로 불러 쓰므로 따로 실행할 일은 거의 없다.
직접 돌려 미리 보고 싶을 때:

    ~/.dubtools/bin/python make_credits.py          # 소감 없이 미리보기
    ~/.dubtools/bin/python make_credits.py --fetch  # 서버에서 소감까지 받아서

만들어지는 것 (_credits/ 안)
    title.png      오프닝 카드
    credits.png    엔딩 크레딧 (세로로 긴 이미지, 위로 스크롤된다)
    schedule.json  소감 음성을 언제 틀지 + 스크롤 속도
"""
import json, os, re, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "_credits")
W, H = 1280, 720
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

AMBER = (240, 165, 0)
INK   = (240, 236, 226)
DIM   = (147, 141, 126)
BG    = (10, 10, 8)

# 소감이 없는 사람에게도 이만큼은 화면에 머물게 한다
SILENT_SLOT = 2.6
GAP         = 0.45
LEAD        = 1.2        # 크레딧 시작 후 첫 소감까지
TAIL        = 3.0        # 마지막 소감 후 여운


def font(size, bold=False):
    # AppleSDGothicNeo.ttc : 0=Regular 1=Light ... 굵기는 index 로 고른다
    for idx in ((6, 5, 2, 0) if bold else (2, 0)):
        try:
            return ImageFont.truetype(FONT, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def read_project():
    src = open(os.path.join(HERE, "segments.js"), encoding="utf-8").read()
    # 주석(// ...)은 지우고 읽는다 — 주석 처리된 배역까지 세면 안 된다
    src = re.sub(r'^\s*//.*$', '', src, flags=re.M)
    g = lambda k: (re.search(rf'{k}\s*:\s*"([^"]*)"', src) or [None, ""])[1]
    chars = dict(re.findall(r'"([^"]+)":\s*\{\s*en:"([^"]*)",\s*color:"(#[0-9a-fA-F]{6})"'
                            .replace('color', 'color'), src)) if False else {}
    chars = {}
    for m in re.finditer(r'"([^"]+)":\s*\{\s*en:"([^"]*)",\s*color:"(#[0-9a-fA-F]{6})"\s*\}', src):
        chars[m.group(1)] = {"en": m.group(2), "color": m.group(3)}
    teams = {}
    for m in re.finditer(r'(\w+):\s*\{\s*label:\s*"([^"]+)",\s*start:\s*([\d.]+),\s*end:\s*([\d.]+)', src):
        teams[m.group(1)] = {"label": m.group(2), "start": float(m.group(3)), "end": float(m.group(4))}
    cast = []
    for m in re.finditer(r'\{\s*team:"(\w+)",\s*person:"([^"]+)",\s*chars:\[([^\]]*)\]\s*\}', src):
        cs = re.findall(r'"([^"]+)"', m.group(3))
        cast.append({"team": m.group(1), "person": m.group(2), "chars": cs})
    return dict(key=g("key"), title=g("title"), teams=teams, chars=chars, cast=cast)


def fetch_notes(key):
    cfg = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
    g = lambda k: (re.search(rf'{k}\s*:\s*"([^"]*)"', cfg) or [None, ""])[1]
    url, anon, bucket = g("SUPABASE_URL"), g("SUPABASE_ANON_KEY"), g("BUCKET") or "takes"
    if not url or not anon:
        print("  config.js 가 비어 있어 소감 없이 만듭니다.")
        return {}
    req = urllib.request.Request(
        f"{url}/rest/v1/submissions?project=eq.{key}&line_id=eq.0&select=*&order=created_at.asc",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"})
    rows = json.load(urllib.request.urlopen(req))
    out = {}
    for r in rows:                                   # 나중 것이 이김
        out[r["person"]] = {"dur": float(r.get("dur") or 0),
                            "gain_db": float(r.get("gain_db") or 0),
                            "clean": int(r.get("clean") or 0),
                            "url": f"{url}/storage/v1/object/public/{bucket}/{r['path']}"}
    print(f"  소감 {len(out)}개 받음")
    return out


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- 타이틀
def make_title(P):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # 은은한 조명
    for i in range(240):
        a = int(26 * (1 - i / 240))
        d.ellipse([W//2 - 520 - i, -200 - i//3, W//2 + 520 + i, 260 + i//3],
                  outline=(BG[0]+a//3, BG[1]+a//4, 10 + a//6))

    f_k, f_t, f_s, f_m = font(24, True), font(62, True), font(31), font(25)
    def center(y, text, f, fill, spacing=0):
        if spacing:
            total = sum(d.textlength(c, font=f) + spacing for c in text) - spacing
            x = (W - total) / 2
            for c in text:
                d.text((x, y), c, font=f, fill=fill); x += d.textlength(c, font=f) + spacing
        else:
            d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

    center(214, "S O R I T U N E   D U B B I N G", f_k, AMBER, spacing=3)
    title = P["title"].split("—")[0].strip() or P["title"]
    sub   = P["title"].split("—")[1].strip() if "—" in P["title"] else ""
    center(276, title, f_t, INK)
    if sub: center(360, sub, f_s, DIM)

    d.line([(W//2 - 150, 424), (W//2 + 150, 424)], fill=(60, 56, 44), width=1)
    center(452, "플로라 팀", f_m, AMBER)
    img.save(os.path.join(OUT, "title.png"))
    return img


# ---------------------------------------------------------------- 크레딧
def make_credits(P, notes):
    # 1) 등장 순서 : 팀 → segments.js 에 적힌 순서
    # 팀은 녹음 구간을 나누기 위한 것일 뿐, 크레딧에서는 한 팀으로 올린다
    entries = []
    for tk in P["teams"]:
        for c in [x for x in P["cast"] if x["team"] == tk]:
            n = notes.get(c["person"])
            entries.append({
                "person": c["person"], "chars": c["chars"],
                "dur": (n["dur"] if n else 0.0),
                "has": bool(n),
            })
    if not entries:
        raise SystemExit("배역이 없습니다.")

    # 2) 소감 재생 시간표 (소감 없는 사람도 잠깐 머문다)
    t = LEAD
    for e in entries:
        e["slot"] = e["dur"] if e["dur"] > 0.3 else SILENT_SLOT
        e["t0"], e["t1"] = t, t + e["slot"]
        t += e["slot"] + GAP
    total = t + TAIL

    # 3) 스크롤 속도
    #    이름이 '그 사람 소감이 나오는 동안' 화면에 머물러야 한다.
    #    소감이 길수록 천천히 흐르게 자동으로 맞춘다.
    avg = sum(e["slot"] for e in entries) / len(entries)
    speed = max(30.0, min(200.0, 560.0 / avg))

    # 4) 이름이 화면 한가운데 오는 순간 = 그 사람 소감의 한가운데
    for e in entries:
        e["y"] = int(speed * ((e["t0"] + e["t1"]) / 2) + H / 2)

    img_h = int(speed * total + H) + 240
    img = Image.new("RGB", (W, img_h), BG)
    d = ImageDraw.Draw(img)
    f_hd, f_team, f_ch, f_nm, f_note = font(46, True), font(28, True), font(33, True), font(33), font(21)

    # 맨 위 '출연'
    hd_y = entries[0]["y"] - 230
    d.text(((W - d.textlength("출  연", font=f_hd)) / 2, hd_y), "출  연", font=f_hd, fill=AMBER)

    mid = W / 2
    for e in entries:
        y = e["y"]
        ch_txt = " · ".join(e["chars"])
        col = hex2rgb(P["chars"].get(e["chars"][0], {}).get("color", "#f0a500"))
        cw = d.textlength(ch_txt, font=f_ch)
        d.text((mid - 34 - cw, y), ch_txt, font=f_ch, fill=col)
        d.text((mid + 34, y), e["person"], font=f_nm, fill=INK)
        for k in range(5):                                   # 가운데 점선
            cx = mid - 24 + k * 11
            d.ellipse([cx, y + 21, cx + 3, y + 24], fill=(84, 79, 64))
        if e["has"]:
            d.text((mid + 34, y + 46), "소감 한마디", font=f_note, fill=AMBER)

    # 마무리 인사는 '끝나기 1.5초 전' 에 화면 가운데 오도록 놓는다
    end_y = int(speed * (total - 1.5) + H / 2)
    f_end = font(34, True)
    d.text(((W - d.textlength("고생하셨습니다", font=f_end)) / 2, end_y),
           "고생하셨습니다", font=f_end, fill=AMBER)
    d.text(((W - d.textlength("소리튠 더빙 프로젝트", font=f_note)) / 2, end_y + 56),
           "소리튠 더빙 프로젝트", font=f_note, fill=DIM)

    img.save(os.path.join(OUT, "credits.png"))
    sched = {"total": round(total, 2), "speed": round(speed, 2), "img_h": img_h,
             "notes": [{"person": e["person"], "t0": round(e["t0"], 2),
                        "dur": round(e["dur"], 2), "has": e["has"],
                        "y": e["y"]} for e in entries]}
    json.dump(sched, open(os.path.join(OUT, "schedule.json"), "w"), ensure_ascii=False, indent=1)
    return sched


def main():
    os.makedirs(OUT, exist_ok=True)
    P = read_project()
    print(f"프로젝트: {P['title']}  (참가자 {len(P['cast'])}명)")
    notes = fetch_notes(P["key"]) if "--fetch" in sys.argv else {}
    make_title(P)
    s = make_credits(P, notes)
    print(f"  title.png / credits.png 생성")
    print(f"  크레딧 길이 {s['total']}초, 이미지 높이 {s['img_h']}px")
    print(f"  소감 있는 사람 {sum(1 for n in s['notes'] if n['has'])} / {len(s['notes'])}")


if __name__ == "__main__":
    main()
