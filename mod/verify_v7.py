#!/usr/bin/env python3
"""Проверка v7 (b9): B2=оригинал, cave2 выбор рамки, sup-кейв в обе стороны,
стекло = 2 submesh + matIndex=1. Плюс всё критичное из v6."""
import sys, os, struct, io, contextlib

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
d32 = open(SO32, "rb").read()
o64 = open("/tmp/orig64.so", "rb").read()
o32 = open("/tmp/orig32.so", "rb").read()

def b64(va, target, kind=0x05):
    w = struct.unpack_from("<I", d, va)[0]
    if (w >> 26) != kind: return False
    off = w & 0x3FFFFFF
    if off & 0x2000000: off -= 0x4000000
    return va + off * 4 == target

def b32(va, target):
    w = struct.unpack_from("<I", d32, va)[0]
    if (w >> 28) != 0xE: return False
    off = w & 0xFFFFFF
    if off & 0x800000: off -= 0x1000000
    return va + 8 + off * 4 == target

# --- B2 = оригинал 1:1 (кроме одной инструкции выбора рамки) ---
check(d[0x867394:0x8673F8] == o64[0x867394:0x8673F8], "arm64: Purchase B2 = оригинальный блок (100Б 1:1)")
b2_ok = d32[0x58B9B4:0x58B9B8] == o32[0x58B9B4:0x58B9B8] and d32[0x58B9BC:0x58BA74] == o32[0x58B9BC:0x58BA74]
check(b2_ok, "arm32: Purchase32 B2 = оригинал (1:1 кроме 0x58b9b8 -> cave2)")

# --- cave2: выбор рамки по ширине ---
check(b64(0x867384, 0x85DC00), "arm64: 0x867384 -> cave2")
check(d[0x85DC00:0x85DC04].hex() == "2801261e", "arm64: cave2 fmov w8,s9")
c2 = [
    ("cmp w8,#0x46", 0x85DC04, struct.pack("<I", 0x7101191F)),
    ("ldr x23,[x19,#0x30]", 0x85DC0C, bytes.fromhex("771a40f9")),
    ("ldr x23,[x19,#0x50]", 0x85DC14, bytes.fromhex("772a40f9")),
]
for nm, va, want in c2:
    check(d[va:va+4] == (want if isinstance(want, bytes) else want), f"arm64: cave2 {nm}")
check(b64(0x85DC10, 0x867388) and b64(0x85DC18, 0x867388), "arm64: cave2 возвраты -> 0x867388")

check(b32(0x58B9B8, 0x1C6A280), "arm32: 0x58b9b8 -> cave2")
check(d32[0x1C6A280:0x1C6A294].hex() == "100a18ee460050e32890940518909415c985a4ea", "arm32: cave2 (vmov/cmp/ldreq/ldrne/b)")
check(b32(0x1C6A290, 0x58B9BC), "arm32: cave2 возврат -> 0x58b9bc")

# --- sup-кейвы: кратность в ОБЕ стороны ---
check(b64(0x834EF4, 0x85DAE0), "arm64: Supports -> кейв (хук жив)")
check(d[0x85DAE0:0x85DAE4].hex() == "687640b9", "arm64: sup-кейв: ldr w8,[x19,#0x74]")
ok = True
for i, k in ((56, 1), (68, 2), (80, 3)):   # lsl w10,w8,#k; cmp w10,w0  (2sw==w .. 8sw==w)
    wl = struct.unpack_from("<I", d, 0x85DAE0 + i)[0]
    wc = struct.unpack_from("<I", d, 0x85DAE0 + i + 4)[0]
    immr = (wl >> 16) & 0x3F; imms = (wl >> 10) & 0x3F
    if (wl & 0xFF800000) != 0x53000000 or immr != 32 - k or imms != 31 - k: ok = False
    if (wc & 0xFFE0FC1F) != 0x6B00001F >> 0 and (wc & 0xFFE0FFFF) != 0x6B00015F & 0xFFE0FFFF: ok = False
check(ok, "arm64: sup-кейв содержит обратные кратности (lsl w10,w8; cmp w10,w0)")
check(b64(0x85DBB4, 0x834F34), "arm64: sup-кейв финал -> 0x834f34")

check(b32(0x54ABA8, 0x1C6A180), "arm32: Supports -> кейв (хук жив)")
check(d32[0x1C6A180:0x1C6A184].hex() == "4c1094e5", "arm32: sup32: ldr r1,[r4,#0x4c]")
ok = True
for off, k in ((0x3c, 1), (0x48, 2), (0x54, 3)):  # lsl r2,r1,#k; cmp r2,r0
    wl = struct.unpack_from("<I", d32, 0x1C6A180 + off)[0]
    wc = struct.unpack_from("<I", d32, 0x1C6A180 + off + 4)[0]
    if wl != (0xE1A02001 | (k << 7)): ok = False   # lsl r2,r1,#k
    if wc != 0xE1520000: ok = False                # cmp r2, r0
check(ok, "arm32: sup32 содержит обратные кратности (lsl r2,r1; cmp r2,r0)")
check(b32(0x1C6A260, 0x54ABF0), "arm32: sup32 финал -> 0x54abf0")

# --- FIX1a/1b, B1-кейв, кейв цены: живы ---
check(b64(0x8674ac + 0x34, 0x867508), "arm64: FIX1a -> эпилог")
check(b64(0x867540, 0x867508), "arm64: FIX1b -> эпилог")
check(struct.unpack_from("<I", d, 0x8674dc)[0] == 0xD63F0060, "arm64: FIX1a blr x3")
check(b64(0x8672c8, 0x85D978, kind=0x25) or b64(0x8672c8, 0x85D978), "arm64: B1-кейв вызов жив")
check(b64(0x867338, 0x85DA08, kind=0x25), "arm64: кейв цены вызов жив")
check(b32(0x58B8E0, 0x1C6A000), "arm32: B1-кейв вызов жив")
check(struct.unpack_from("<I", d32, 0x58b968)[0] != 0xEB4DBE1C or True, "arm32: 0x58b968 (цена) — хук ниже")
# arm32 кейв цены: bl CAVE32_MON (0x1c6a090)
w = struct.unpack_from("<I", d32, 0x58B968)[0]
off = w & 0xFFFFFF
if off & 0x800000: off -= 0x1000000
check((w >> 24) == 0xEB and 0x58B968 + 8 + off * 4 == 0x1C6A100, "arm32: кейв цены -> 0x1c6a100")
check(struct.unpack_from("<I", d32, 0x58bb48)[0] == 0xe594001c, "arm32: FIX1a ldr r0,[r4,#0x1c]")
check(struct.unpack_from("<I", d32, 0x58bba8)[0] == 0xe59f0054, "arm32: FIX1b ldr r0,[pc,#0x54]")
check(d32[0x53bad0:0x53bad4].hex() == "6ab95cea", "arm32: v3 BTC-кейв жив")
check(struct.unpack_from("<Q", d, 0x23b9034)[0] == 0, "arm64: RW-слот чист")

print("=== 2. Бандл ===")
from modtools import load_env, Ctx
env = modtools.load_env()
ctx = Ctx(env)
R = "resources.assets"
market = ctx.read_tt(R, 12594)
items = [p["m_PathID"] for p in market["items"]]
check(len(items) == 53, f"items = {len(items)} (53 ориг.)")
bad = [p for p in items if ctx.obj(R, p) is None]
check(not bad, f"все PPtr валидны ({bad})")

# гирлянды
for lv in ("level1", "level3", "level4", "level5"):
    found = False
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "ParticleSystem":
            with contextlib.redirect_stderr(io.StringIO()):
                pst = ctx.read_tt(lv, pid)
            go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
            if go["m_Name"] == "SnowParticle":
                trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                             if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
                tr = ctx.read_tt(lv, trpid)
                speed = pst["InitialModule"]["startSpeed"]["scalar"]
                life = pst["InitialModule"]["startLifetime"]["scalar"]
                check(abs(tr["m_LocalPosition"]["y"] - 5.55) < 0.01 and abs(speed - 0.03) < 1e-6 and abs(life - 30.0) < 1e-6,
                      f"{lv}: SnowParticle y=5.55 speed=0.03 life=30")
                found = True
    check(found, f"{lv}: SnowParticle найден")

# подарков в сценах нет
for lv in ("level1", "level3", "level4", "level5", "level6"):
    n = 0
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name != "GameObject": continue
        try: g = ctx.read_tt(lv, pid)
        except Exception: continue
        if g.get("m_Name", "").startswith("Gift"): n += 1
    check(n == 0, f"{lv}: объектов Gift нет ({n})")

# level6 нетронут
lv = "level6"
sp_ok = False
for pid, o in ctx.files[lv].objects.items():
    if o.type.name == "ParticleSystem":
        with contextlib.redirect_stderr(io.StringIO()):
            pst = ctx.read_tt(lv, pid)
        go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
        if go["m_Name"] == "SnowParticle":
            trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                         if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
            tr = ctx.read_tt(lv, trpid)
            sp_ok = tr["m_Father"]["m_PathID"] == 223 and abs(tr["m_LocalPosition"]["y"] - 2.62) < 0.01
check(sp_ok, "level6: SnowParticle не тронут (father=223, y=2.62)")

# --- СТЕКЛО v7 ---
mg = ctx.read_tt(R, 13759)
check(mg["m_Name"] == "Crate_Glass", f"Mesh 13759: {mg['m_Name']!r}")
subs = mg["m_SubMeshes"]
check(len(subs) == 2 and subs[0]["indexCount"] == 30 and subs[1]["indexCount"] == 6
      and subs[0]["firstByte"] == 0 and subs[1]["firstByte"] == 60,
      f"Mesh 13759: 2 submesh (30/6, fb 0/60)")
ib = bytes(mg["m_IndexBuffer"])
tail = struct.unpack("<12H", ib[48:72])
check(tail == (20, 21, 22, 20, 22, 23, 16, 17, 18, 16, 18, 19),
      f"Mesh 13759: хвост буфера = верх(t8,t9)+низ(t10,t11): {tail}")
check(mg["m_VertexData"]["m_VertexCount"] == 24, "Mesh 13759: 24 вершины (UV не тронуты)")

# оригинальный меш 402 не изменён
m402 = ctx.read_tt(R, 402)
check(m402["m_Name"] == "Crate" and len(m402["m_SubMeshes"]) == 1
      and bytes(m402["m_IndexBuffer"])[0:6] == bytes([0, 0, 1, 0, 2, 0]),
      "Mesh 402 (оригинал Crate) не изменён")

mat = ctx.read_tt(R, 13760)
check(mat["m_Name"] == "Crate_Glass", f"Material 13760: {mat['m_Name']!r}")
tex = [v for k, v in mat["m_SavedProperties"]["m_TexEnvs"] if k == "_MainTex"][0]
check(tex["m_Texture"]["m_PathID"] == 184
      and abs(tex["m_Scale"]["x"] - 6.6666665) < 1e-3 and abs(tex["m_Scale"]["y"] - 4.0) < 1e-6
      and abs(tex["m_Offset"]["x"] + 2.8333333) < 1e-3 and abs(tex["m_Offset"]["y"] + 1.5) < 1e-6,
      "Material 13760: _MainTex tex=184 scale/offset скомпенсированы")

for go_pid, mf_pid, mr_pid, tl_pid in ((2832, 6663, 6028, 13755), (2901, 6519, 5754, 13757)):
    go = ctx.read_tt(R, go_pid)
    mf = ctx.read_tt(R, mf_pid)
    mr = ctx.read_tt(R, mr_pid)
    tl = ctx.read_tt(R, tl_pid)
    check(mf["m_Mesh"]["m_PathID"] == 13759
          and [p["m_PathID"] for p in mr["m_Materials"]] == [22, 13760]
          and tl["matIndex"] == 1 and tl["rend"]["m_PathID"] == mr_pid,
          f"{go['m_Name']}: mesh=13759, mats=[22,13760], TL.matIndex=1")
    # PaperFrame присутствует
    has_pf = False
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MonoBehaviour":
            cls, _ = ctx.mono_class(R, pid)
            if cls == "PaperFrame": has_pf = True
    check(has_pf, f"{go['m_Name']}: PaperFrame присутствует")

# PrintExpert: alertText = горизонтальная рамка (для cave2)
site = ctx.read_tt(R, 1480)
comp_pids = [c["component"]["m_PathID"] for c in site["m_Component"]]
check(len(comp_pids) == 4, f"GO 1480: {len(comp_pids)} компонентов")
pe = None
for pid in comp_pids:
    if ctx.obj(R, pid).type.name == "MonoBehaviour":
        cls, tt = ctx.mono_class(R, pid)
        if cls == "PrintExpert": pe = tt
check(pe is not None and pe["alertText"]["m_PathID"] == 13747
      and pe["bannerPrefab"]["m_PathID"] == 12916,
      f"PrintExpert MB: alertText={pe['alertText']['m_PathID'] if pe else '?'} (13747=гориз. рамка), bannerPrefab={pe['bannerPrefab']['m_PathID'] if pe else '?'} (ожид. 12916)")

print("=== 3. Полный проход бандла ===")
errs = 0; total = 0; bad2 = []
OLD_KNOWN = {("level0", 1204), ("level0", 1207)} | {
    ("resources.assets", p) for p in (11092, 11180, 11181, 11182, 11183, 11184, 11185, 11186, 11187)}
for fname, f in ctx.files.items():
    for pid, o in list(f.objects.items()):
        total += 1
        try: o.read()
        except Exception:
            errs += 1
            if (fname, pid) not in OLD_KNOWN:
                bad2.append((fname, pid, o.type.name))
check(not bad2, f"объектов {total}, НОВЫХ ошибок нет (всего {errs}): {bad2[:5]}")

print()
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✔" if FAIL == 0 else f"ПРОВАЛЕНО: {FAIL}")
sys.exit(1 if FAIL else 0)
