#!/usr/bin/env python3
"""Проверка v6 (b8): сцены = b5 (без подарков — краш b7), 53 товара,
гирлянды к потолку (level1/3/4/5), стекло, Supports ×1/2/4/8."""
import sys, os, struct, json

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")

FAIL = 0
def check(cond, msg):
    global FAIL
    if not cond: FAIL += 1
    print(f"  [{'OK ' if cond else 'FAIL'}] {msg}")
    return cond

print("=== 1. libil2cpp.so ===")
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")
d = open(SO64, "rb").read()
def b64(va, target):
    w = struct.unpack_from("<I", d, va)[0]
    if (w >> 26) != 0x05: return False
    off = w & 0x3FFFFFF
    if off & 0x2000000: off -= 0x4000000
    return va + off * 4 == target
check(b64(0x8674ac + 0x34, 0x867508), "arm64: FIX1a -> эпилог")
check(b64(0x867540, 0x867508), "arm64: FIX1b -> эпилог")
check(b64(0x834ef4, 0x85dae0), "arm64: Supports -> кейв")
check(struct.unpack_from("<I", d, 0x8674dc)[0] == 0xD63F0060, "arm64: FIX1a blr x3")
# v3-оригиналы НЕ тронуты (откат v4)
check(struct.unpack_from("<I", d, 0x867394)[0] == 0x1E260137, "arm64: B2 = v3 fmov w23,s9 (откат)")
w = struct.unpack_from("<I", d, 0x8671f8)[0]
check((w >> 24) == 0x37, "arm64: 0x8671f8 = v3 tbnz (хуков нет)")
# кейв sup64: серия x1/x2/x4/x8
ok = True
base = 0x85dae0
for i, sh in ((5, 1), (8, 2), (11, 3)):   # lsl w10,w0,#sh  (x2/x4/x8)
    w = struct.unpack_from("<I", d, base + 4*i)[0]
    immr = (w >> 16) & 0x3F
    imms = (w >> 10) & 0x3F
    if (w & 0xFF800000) != 0x53000000 or immr != 32 - sh or imms != 31 - sh: ok = False
check(ok, "arm64: sup-кейв lsl x2/x4/x8")
check(struct.unpack_from("<Q", d, 0x23b9034)[0] == 0, "arm64: RW-слот чист (v4-слоты убраны)")

d32 = open(SO32, "rb").read()
def b32(va, target):
    w = struct.unpack_from("<I", d32, va)[0]
    if (w >> 28) != 0xE: return False
    off = w & 0xFFFFFF
    if off & 0x800000: off -= 0x1000000
    return va + 8 + off * 4 == target
check(b32(0x54aba8, 0x1c6a180), "arm32: Supports -> кейв")
check(d32[0x58b9b4:0x58b9b8].hex() == '100a18ee', "arm32: B2 = v3 vmov r0,s16 (откат)")
check(d32[0x58b7ec:0x58b7f0].hex() == '05508fe0', "arm32: 0x58b7ec = ориг add r5,pc,r5 (хуков нет)")
check(d32[0x58b660:0x58b664].hex() == '0050a0e1', "arm32: 0x58b660 = ориг mov r5,r0 (хуков нет)")
check(struct.unpack_from("<I", d32, 0x58bba8)[0] == 0xe59f0054, "arm32: FIX1b ldr r0,[pc,#0x54]")
w = struct.unpack_from("<I", d32, 0x58bb48)[0]
check(w == 0xe594001c, "arm32: FIX1a ldr r0,[r4,#0x1c]")
# v3 BTC-кейвы живы
check(d32[0x53bad0:0x53bad4].hex() == '6ab95cea', "arm32: v3 BTC-кейв жив")

print("=== 2. Бандл ===")
from modtools import load_env, Ctx
env = modtools.load_env()
ctx = Ctx(env)
R = "resources.assets"
market = ctx.read_tt(R, 12594)
items = [p["m_PathID"] for p in market["items"]]
check(len(items) == 53, f"items = {len(items)} (53 ориг.)")
ours = {13706, 13739, 13754, 13787}
check(not ours & set(items), "наши карточки убраны")
bad = [p for p in items if ctx.obj(R, p) is None]
check(not bad, f"все PPtr валидны ({bad})")

# гирлянды
for lv, want_y in (("level1", 5.55), ("level3", 5.55), ("level4", 5.55), ("level5", 5.55)):
    found = False
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "ParticleSystem":
            import io, contextlib
            with contextlib.redirect_stderr(io.StringIO()):
                pst = ctx.read_tt(lv, pid)
            go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
            if go["m_Name"] == "SnowParticle":
                trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                             if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
                tr = ctx.read_tt(lv, trpid)
                speed = pst["InitialModule"]["startSpeed"]["scalar"]
                life = pst["InitialModule"]["startLifetime"]["scalar"]
                check(abs(tr["m_LocalPosition"]["y"] - want_y) < 0.01 and abs(speed - 0.03) < 1e-6 and abs(life - 30.0) < 1e-6,
                      f"{lv}: SnowParticle y={tr['m_LocalPosition']['y']} speed={speed} life={life}")
                found = True
    check(found, f"{lv}: SnowParticle найден")

# подарки: В СЦЕНАХ ИХ БЫТЬ НЕ ДОЛЖНО (краш b7)
for lv, _ in (("level1", 5), ("level3", 5), ("level4", 5), ("level5", 5), ("level6", 2)):
    n = 0
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name != "GameObject": continue
        try: g = ctx.read_tt(lv, pid)
        except: continue
        if g.get("m_Name", "").startswith("Gift"): n += 1
    check(n == 0, f"{lv}: объектов Gift нет ({n})")

# level6: гирлянда не тронута (v3)
lv = "level6"
sp_ok = False
for pid, o in ctx.files[lv].objects.items():
    if o.type.name == "ParticleSystem":
        import io, contextlib
        with contextlib.redirect_stderr(io.StringIO()):
            pst = ctx.read_tt(lv, pid)
        go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
        if go["m_Name"] == "SnowParticle":
            trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                         if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
            tr = ctx.read_tt(lv, trpid)
            sp_ok = tr["m_Father"]["m_PathID"] == 223 and abs(tr["m_LocalPosition"]["y"] - 2.62) < 0.01
check(sp_ok, "level6: SnowParticle не тронут (v3, father=223, y=2.62)")

# стекло
for glass_go in (2832, 2901):
    go = ctx.read_tt(R, glass_go)
    tl = pf = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MonoBehaviour":
            cls, tt = ctx.mono_class(R, pid)
            if cls == "TextureLoader": tl = tt
            if cls == "PaperFrame": pf = True
    check(tl and pf and tl["matIndex"] == 0 and tl["rend"]["m_PathID"] in (6028, 5754),
          f"GO {glass_go}: TextureLoader matIndex={tl['matIndex'] if tl else '?'} rend={tl['rend']['m_PathID'] if tl else '?'} + PaperFrame={bool(pf)}")

# PrintExpert-сайт: чист (как b5)
site = ctx.read_tt(R, 1480)
comp_pids = [c["component"]["m_PathID"] for c in site["m_Component"]]
check(13788 not in comp_pids and len(comp_pids) == 4, f"GO 1480: {len(comp_pids)} компонентов (без клона)")
txt = ctx.read_tt(R, 11296)
check(txt["m_Text"] == "Purchase", f"кнопка Purchase: {txt['m_Text']!r} (откат)")
home_tr = ctx.read_tt(R, 10565)
check(len(home_tr["m_Children"]) == 6, f"Home: {len(home_tr['m_Children'])} детей (без клона кнопки)")

print("=== 3. Полный проход бандла (по ctx, без повторной загрузки) ===")
errs = 0; total = 0; bad = []
OLD_KNOWN = {("level0", 1204), ("level0", 1207)} | {
    ("resources.assets", p) for p in (11092, 11180, 11181, 11182, 11183, 11184, 11185, 11186, 11187)}
for fname, f in ctx.files.items():
    for pid, o in list(f.objects.items()):
        total += 1
        try: o.read()
        except Exception:
            errs += 1
            if (fname, pid) not in OLD_KNOWN:
                bad.append((fname, pid, o.type.name))
check(not bad, f"объектов {total}, НОВЫХ ошибок нет (всего {errs}): {bad[:5]}")

print()
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✔" if FAIL == 0 else f"ПРОВАЛЕНО: {FAIL}")
sys.exit(1 if FAIL else 0)
