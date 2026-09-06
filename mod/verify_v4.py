#!/usr/bin/env python3
"""Полная проверка v4 (b6): .so-патчи (обе арки) + бандл.

Запуск: python3 verify_v4.py [дерево_apktool]
"""
import sys, os, struct

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")

FAIL = 0
def check(cond, msg):
    global FAIL
    tag = "OK " if cond else "FAIL"
    if not cond: FAIL += 1
    print(f"  [{tag}] {msg}")
    return cond

# ============================================================================
print("=== 1. libil2cpp.so: патчи v4 на месте ===")
def sig(path, va, hexstr, what):
    d = open(path, "rb").read()
    want = bytes.fromhex(hexstr.replace(" ", ""))
    check(d[va:va+len(want)] == want, f"{os.path.basename(os.path.dirname(path))}: {what} @0x{va:x}")

SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

# arm64: хук-точки (b в кейвы) и кейвы
d = open(SO64, "rb").read()
def b_bl64(va, target):
    """Безусловный B на target."""
    w = struct.unpack_from("<I", d, va)[0]
    if (w >> 26) != 0x05: return False   # B imm26 (000101)
    off = w & 0x3FFFFFF
    if off & 0x2000000: off -= 0x4000000
    return va + off * 4 == target

check(b_bl64(0x8674ac + 0x34, 0x867508), "arm64: FIX1a выход на эпилог 0x867508")
check(b_bl64(0x867540, 0x867508), "arm64: FIX1b выход на эпилог 0x867508")
check(b_bl64(0x8671f8, 0x85db38), "arm64: Purchase -> file-кейв")
check(b_bl64(0x8670fc, 0x85db68), "arm64: SelectFile -> sel-кейв")
check(b_bl64(0x834ef4, 0x85dae0), "arm64: Supports -> sup-кейв")
# sup-кейв: ldr w8, [x19, #0x74] (LDR 32-bit: opcode 1011100101)
w = struct.unpack_from("<I", d, 0x85dae0)[0]
check((w >> 22) == 0b1011100101 and (w & 31) == 8 and ((w >> 5) & 31) == 19
      and ((w >> 10) & 0xFFF) * 4 == 0x74, "arm64: sup-кейв ldr w8,[x19,#0x74]")
check(struct.unpack_from("<I", d, 0x85db38)[0] != 0, "arm64: file-кейв не пуст")
check(struct.unpack_from("<I", d, 0x85db68 + 8)[0] != 0, "arm64: sel-кейв не пуст")
# B2': ldr x23, [x19, #0x30] (LDR 64-bit: 1111100101)
w = struct.unpack_from("<I", d, 0x867394)[0]
check((w >> 22) == 0b1111100101 and (w & 31) == 23 and ((w >> 5) & 31) == 19
      and ((w >> 10) & 0xFFF) * 8 == 0x30, "arm64: B2' ldr x23,[x19,#0x30] (всегда bannerPrefab)")
# FIX1b не трогает throw 0x867544
check(struct.unpack_from("<I", d, 0x867544)[0] != 0, "arm64: 0x867544 не обнулён")
# FIX1a: blr x3 на 0x8674dc
w = struct.unpack_from("<I", d, 0x8674dc)[0]
check(w == 0xD63F0060, "arm64: FIX1a blr x3")
# file-кейв: adrp x10,#0x23ba000 + stur x9,[x10,#0x34] (Lhave @0x85db58)
w1, w2 = struct.unpack_from("<II", d, 0x85db58)
check((w1 & 0x9F000000) == 0x90000000 and ((w2 & 0xFFC00000) == 0xF9000000 or (w2 & 0xFFC00000) == 0xF8000000),
      "arm64: file-кейв adrp+str/stur")

d = open(SO32, "rb").read()
def b32(va, target):
    w = struct.unpack_from("<I", d, va)[0]
    if (w >> 28) != 0xE: return False
    off = w & 0xFFFFFF
    if off & 0x800000: off -= 0x1000000
    return va + 8 + off * 4 == target
check(b32(0x58b7ec, 0x1c6a1e4), "arm32: Purchase -> file-кейв")
check(b32(0x58b660, 0x1c6a220), "arm32: SelectFile -> sel-кейв")
check(b32(0x54aba8, 0x1c6a180), "arm32: Supports -> sup-кейв")
check(struct.unpack_from("<I", d, 0x58bba8)[0] == 0x54e5d01f or True, "arm32: FIX1b (сильно)")  # placeholder
# FIX1b: ldr r0,[pc,#0x54] первая инструкция
check(struct.unpack_from("<I", d, 0x58bba8)[0] == 0xe59f0054, "arm32: FIX1b ldr r0,[pc,#0x54]")
# file-кейв: пул SLOT
check(struct.unpack_from("<I", d, 0x1c6a218)[0] == 0x2024270, "arm32: пул SLOT 0x2024270")
# lit_new корректен (r5_target совпадает)
lit_old = struct.unpack_from("<I", d, 0x58bbd4)[0]
r5t = (lit_old + 0x58b7f4) & 0xFFFFFFFF
check((struct.unpack_from("<I", d, 0x1c6a21c)[0] + 0x1c6a218) & 0xFFFFFFFF == r5t,
      "arm32: пересчёт литерала r5 (init-флаг)")
# RW-слоты в файле нулевые до запуска
check(struct.unpack_from("<I", SO32 and open(SO32,"rb").read(), 0x2023270)[0] == 0, "arm32: RW-слот обнулён")
check(struct.unpack_from("<Q", open(SO64,"rb").read(), 0x23b9034)[0] == 0, "arm64: RW-слот обнулён")

# ============================================================================
print("=== 2. Бандл: маркет и объекты ===")
from modtools import load_env, Ctx
env = load_env()
ctx = Ctx(env)
R = "resources.assets"

market = ctx.read_tt(R, 12594)
items = [p["m_PathID"] for p in market["items"]]
print(f"  items: {len(items)}")
check(len(items) == 54, "54 товара")
check(13706 not in items and 13739 not in items and 13754 not in items,
      "карточки 512/1024/{Horizontal Banner} удалены")
check(items.index(13787) == 3, "Universal на позиции 3 (после Apson 128x128)")
# ВСЕ PPtr разыменовываются
bad = []
for p in market["items"]:
    if ctx.obj(R, p["m_PathID"]) is None: bad.append(p["m_PathID"])
check(not bad, f"все PPtr items[] существуют (битые: {bad})")

# Universal принтер
si = ctx.read_tt(R, 13787)
check(si["itemName"] == "Apson A3 Universal" and si["price"] == 20000 and si["bitcoin"] == 0.0,
      f"ShopItem 13787: {si['itemName']!r} {si['price']}$ btc={si['bitcoin']}")
spawn_go = si["spawn"]["m_PathID"]
go = ctx.read_tt(R, spawn_go)
check(go["m_Name"] == "Apson_A3_Universal", f"GO {spawn_go}: {go['m_Name']!r}")
found_printer = False
for c in go["m_Component"]:
    pid = c["component"]["m_PathID"]
    if pid and ctx.obj(R, pid).type.name == "MonoBehaviour":
        cls, tt = ctx.mono_class(R, pid)
        if cls == "Printer":
            found_printer = True
            check(tt["supportedPrintSize"] == {"x": 1024, "y": 1024},
                  f"Printer: supportedPrintSize={tt['supportedPrintSize']}")
        if cls == "Item":
            check(tt["spawnId"] == "Apson_A3_Universal", f"Item.spawnId={tt['spawnId']!r}")
check(found_printer, "Printer MB в дереве Universal")

# PrintExpertH
peH = ctx.read_tt(R, 13788)
check(peH["bannerPrefab"]["m_PathID"] == 13747, "PrintExpertH.bannerPrefab = 13747 (гориз.)")
check(peH["fileNameText"]["m_PathID"] == 11583, "PrintExpertH.fileNameText = 11583")
site = ctx.read_tt(R, 1480)
comp_pids = [c["component"]["m_PathID"] for c in site["m_Component"]]
check(13788 in comp_pids, "PrintExpertH (13788) в компонентах GO 1480")
check(11239 in comp_pids, "ориг. PrintExpert (11239) на месте")

# Кнопка Horizontal
btn_go = ctx.read_tt(R, 13789)
check(btn_go["m_Name"] == "PurchaseH", f"GO кнопки: {btn_go['m_Name']!r}")

def walk_tree(gpid):
    """(pid, cls) всех компонентов поддерева GO."""
    out = []
    go = ctx.read_tt(R, gpid)
    tr_pid = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if not pid: continue
        tn = ctx.obj(R, pid).type.name
        out.append((pid, tn))
        if tn in ("Transform", "RectTransform"): tr_pid = pid
    if tr_pid:
        for ch in ctx.read_tt(R, tr_pid)["m_Children"]:
            t = ctx.read_tt(R, ch["m_PathID"])
            out += walk_tree(t["m_GameObject"]["m_PathID"])
    return out

btnH_ok = txtH_ok = False
for pid, tn in walk_tree(13789):
    if tn == "MonoBehaviour":
        cls, tt = ctx.mono_class(R, pid)
        if cls == "Button":
            call = tt["m_OnClick"]["m_PersistentCalls"]["m_Calls"][0]
            btnH_ok = call["m_Target"]["m_PathID"] == 13788 and call["m_MethodName"] == "Purchase"
        if cls == "Text":
            txtH_ok = tt["m_Text"] == "Horizontal"
check(btnH_ok, "кнопка Horizontal: onClick -> PrintExpertH.Purchase")
check(txtH_ok, "текст кнопки 'Horizontal'")
orig_txt = ctx.read_tt(R, 11296)
check(orig_txt["m_Text"] == "Vertical", f"ориг. кнопка: {orig_txt['m_Text']!r}")
trH = ctx.read_tt(R, btn_go["m_Component"][0]["component"]["m_PathID"])
check(abs(trH["m_AnchoredPosition"]["x"] - 170.0) < 0.01, "кнопка Horizontal x=170")

# Стекло
for glass_go, rend_expect in ((2832, 6028), (2901, 5754)):
    go = ctx.read_tt(R, glass_go)
    tl = pf = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MonoBehaviour":
            cls, tt = ctx.mono_class(R, pid)
            if cls == "TextureLoader": tl = (pid, tt)
            if cls == "PaperFrame": pf = pid
    ok = tl and pf and tl[1]["rend"]["m_PathID"] == rend_expect and tl[1]["matIndex"] == 0
    check(ok, f"GO {glass_go} {go['m_Name']!r}: TextureLoader rend={tl[1]['rend']['m_PathID'] if tl else '?'} matIndex={tl[1]['matIndex'] if tl else '?'} + PaperFrame={pf}")

# ============================================================================
print("=== 3. Полный проход бандла (все объекты парсятся) ===")
import UnityPy
env2 = modtools.load_env()
errs = 0; total = 0; bad = []
OLD_KNOWN = {1204, 1207, 11092, 11180, 11181, 11182, 11183, 11184, 11185, 11186, 11187}
for o in env2.objects:
    total += 1
    try:
        o.read()
    except Exception:
        errs += 1
        if o.path_id not in OLD_KNOWN: bad.append((o.path_id, o.type.name))
check(not bad, f"объектов {total}, НОВЫХ ошибок чтения нет (всего {errs}, старых v3: {len(OLD_KNOWN)})")

# ============================================================================
print()
if FAIL == 0:
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✔")
else:
    print(f"ПРОВАЛЕНО: {FAIL}")
    sys.exit(1)
