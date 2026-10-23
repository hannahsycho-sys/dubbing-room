#!/usr/bin/env python3
"""
make_subs.py — segments.js 의 대사로 자막 파일을 만든다.

    ~/.dubtools/bin/python make_subs.py              # 영어+한글 (기본)
    ~/.dubtools/bin/python make_subs.py --lang en    # 영어만
    ~/.dubtools/bin/python make_subs.py --lang ko    # 한글만
    ~/.dubtools/bin/python make_subs.py --offset 4   # 앞에 4초 밀기 (타이틀 길이만큼)

만들어지는 것
    자막.srt   유튜브 업로드·편집 프로그램용 (끄고 켤 수 있는 자막)
    자막.ass   영상에 직접 새길 때 쓰는 것 (글꼴·색 지정됨)
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def read_lines():
    src = open(os.path.join(HERE, "segments.js"), encoding="utf-8").read()
    src = re.sub(r'^\s*//.*$', '', src, flags=re.M)
    out = []
    pat = re.compile(
        r'\{\s*id:\s*(\d+),\s*team:"(\w+)",\s*char:"([^"]+)",\s*s:\s*([\d.]+),\s*e:\s*([\d.]+),\s*\n'
        r'\s*text:"((?:[^"\\]|\\.)*)",\s*\n'
        r'\s*ipa:"(?:[^"\\]|\\.)*",\s*\n'
        r'\s*trans:"((?:[^"\\]|\\.)*)"')
    for m in pat.finditer(src):
        out.append(dict(id=int(m.group(1)), char=m.group(3),
                        s=float(m.group(4)), e=float(m.group(5)),
                        text=m.group(6).replace('\\"', '"'),
                        trans=m.group(7).replace('\\"', '"')))
    return out

def t_srt(t):
    h, r = divmod(max(0.0, t), 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s%1)*1000)):03d}"

def t_ass(t):
    h, r = divmod(max(0.0, t), 3600); m, s = divmod(r, 60)
    return f"{int(h):d}:{int(m):02d}:{s:05.2f}"

ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: SUB,Apple SD Gothic Neo,34,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,2.6,1.3,2,70,70,34,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

# 한 줄 안에서 영어/한글을 각각 다르게 꾸민다 (겹침 배치에 맡기지 않는다)
EN_TAG = r"{\fs34\b1\c&HFFFFFF&}"
KO_TAG = r"{\fs25\b0\c&HC9DCF2&}"

def main():
    a = sys.argv[1:]
    lang = a[a.index("--lang")+1] if "--lang" in a else "both"
    off  = float(a[a.index("--offset")+1]) if "--offset" in a else 0.0
    suffix = a[a.index("--suffix")+1] if "--suffix" in a else ""
    lines = read_lines()
    if not lines:
        sys.exit("segments.js 에서 대사를 못 읽었습니다.")

    # ---- SRT ----
    srt = []
    for i, l in enumerate(lines, 1):
        body = {"en": l["text"], "ko": l["trans"]}.get(lang, f'{l["text"]}\n{l["trans"]}')
        srt.append(f'{i}\n{t_srt(l["s"]+off)} --> {t_srt(l["e"]+off)}\n{body}\n')
    p_srt = os.path.join(HERE, f"자막{suffix}.srt")
    open(p_srt, "w", encoding="utf-8").write("\n".join(srt))

    # ---- ASS (영상에 새길 때) ----
    ev = []
    for l in lines:
        st, en = t_ass(l["s"]+off), t_ass(l["e"]+off)
        if lang == "en":   body = EN_TAG + l["text"]
        elif lang == "ko": body = KO_TAG + l["trans"]
        else:              body = EN_TAG + l["text"] + r"\N" + KO_TAG + l["trans"]
        ev.append(f'Dialogue: 0,{st},{en},SUB,,0,0,0,,{body}')
    p_ass = os.path.join(HERE, f"자막{suffix}.ass")
    open(p_ass, "w", encoding="utf-8").write(ASS_HEAD + "\n".join(ev) + "\n")

    print(f"대사 {len(lines)}줄 · 표시: {{'both':'영어+한글','en':'영어만','ko':'한글만'}}[lang]"
          .replace("{'both':'영어+한글','en':'영어만','ko':'한글만'}[lang]",
                   {"both":"영어+한글","en":"영어만","ko":"한글만"}[lang])
          + (f" · {off:+.1f}초 밀기" if off else ""))
    print(f"  {os.path.basename(p_srt)}")
    print(f"  {os.path.basename(p_ass)}")

if __name__ == "__main__":
    main()
