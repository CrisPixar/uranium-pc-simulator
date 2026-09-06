#!/usr/bin/env python3
"""Правки data.unity3d для Uranium PC Simulator — v2 (исправленная).

КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ v1: UnityPy ObjectReader.save_typetree() вызывает
set_raw_data() и ПЕРЕЗАПИСЫВАЕТ ОБЪЕКТ-ИСТОЧНИК данными клона. В v1 это
испортило исходные префабы принтера/баннера и шаблоны ShopItem (чужие
m_GameObject-ссылки -> SIGSEGV в libunity при входе в игру).
v2 сериализует клоны через TypeTreeHelper.write_typetree в отдельный writer,
не трогая источники.

Правки (суперсет v1 + новые):
  1. Grid -> белая RGBA32 (без LCD-сетки)
  2. Paint.maxCanvasSize -> 1024
  3. PhysicsManager: итерации 10/4, bounce 1.0, sleep 0.003
  4. productName -> Uranium PC Simulator
  5. Заголовок главного меню (level0 'Title') -> "Uranium PC Simulator"  [НОВОЕ]
  6. Гирлянды (level1,3,4,5,6): материал ParticleFlare + радужный RandomColor
  7. Принтеры Apson A3 512x512 (15000) и 1024x1024 (30000)
  8. Горизонтальный баннер BannerStand_H (100) + PaperFrame
  9. Translate: строка "Horizontal Banner" + чистая подпись песочницы      [НОВОЕ]
     (убрать "(5BTC)" из "Sandbox Mode Price")

Запуск:  python3 patch_bundle.py [путь_к_дереву_apktool]
По умолчанию дерево берётся из /tmp/uranium (клон репозитория).
"""
import sys, os, io, contextlib

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
from modtools import load_env, Ctx
from UnityPy.enums import ClassIDType
from UnityPy.helpers.TypeTreeHelper import write_typetree as _tth_write
from UnityPy.streams import EndianBinaryWriter as EndianBinaryWriter

env = load_env()
ctx = Ctx(env)
R = "resources.assets"
GG = "globalgamemanagers"

# ============================================================================
# Безопасная сериализация (НЕ мутирует объект-источник)
# ============================================================================
def serialize_raw(fname, tt, source_pid):
    o = ctx.obj(fname, source_pid)
    if o.type.name == "MonoBehaviour":
        node = ctx.node_for(fname, source_pid, patch_align=True)
    else:
        node = o._get_typetree_node(None)
    writer = EndianBinaryWriter(endian=o.reader.endian)
    _tth_write(tt, node, writer, ctx.files[fname])
    return writer.bytes

def write_existing(fname, pid, tt):
    """Правка СУЩЕСТВУЮЩЕГО объекта (мутация намеренная)."""
    ctx.write_tt(fname, pid, tt)

# ----------------------------------------------------------------------------
def remap_pptrs(obj, mapping):
    if isinstance(obj, dict):
        if set(obj.keys()) == {"m_FileID", "m_PathID"}:
            if obj["m_FileID"] == 0 and obj["m_PathID"] in mapping:
                return {"m_FileID": 0, "m_PathID": mapping[obj["m_PathID"]]}
            return obj
        return {k: remap_pptrs(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [remap_pptrs(v, mapping) for v in obj]
    return obj

def collect_tree(root_go_pid):
    objs, seen = [], set()
    def walk_go(gpid):
        if gpid in seen: return
        seen.add(gpid)
        go = ctx.read_tt(R, gpid)
        objs.append(("GameObject", gpid))
        tr = None
        for c in go["m_Component"]:
            cpid = c["component"]["m_PathID"]
            if not cpid: continue
            cls = ctx.obj(R, cpid).type.name
            objs.append((cls, cpid))
            if cls == "Transform":
                tr = ctx.read_tt(R, cpid)
        for ch in tr["m_Children"]:
            cht = ctx.read_tt(R, ch["m_PathID"])
            walk_go(cht["m_GameObject"]["m_PathID"])
    walk_go(root_go_pid)
    return objs

def new_pid():
    if not hasattr(ctx, "_next_pid"):
        ctx._next_pid = ctx.max_path_id(R) + 1
    p = ctx._next_pid
    ctx._next_pid = p + 1
    while p in ctx.files[R].objects:
        p = ctx._next_pid
        ctx._next_pid = p + 1
    return p

def clone_tree(root_go_pid):
    """Клонировать дерево. Возвращает (mapping, {new_pid: (cls, tt, src_pid)})."""
    objs = collect_tree(root_go_pid)
    mapping = {pid: new_pid() for _, pid in objs}
    data = {}
    for cls, pid in objs:
        tt = remap_pptrs(ctx.read_tt(R, pid), mapping)
        data[mapping[pid]] = (cls, tt, pid)
    return mapping, data

def commit_clone(data):
    for newpid, (cls, tt, srcpid) in data.items():
        raw = serialize_raw(R, tt, srcpid)
        ctx.add_object(R, newpid, ClassIDType[cls], raw)

# ============================================================================
print("[1] Grid -> белая RGBA32")
g = ctx.read_tt(R, 117)
assert g["m_Name"] == "Grid" and g["m_Width"] == 32 and g["m_Height"] == 32
px = 32*32 + 16*16 + 8*8 + 4*4 + 2*2 + 1*1
g["m_TextureFormat"] = 4
g["m_CompleteImageSize"] = px * 4
g["image data"] = b"\xff" * (px * 4)
g["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
write_existing(R, 117, g)
print("    OK")

# ============================================================================
print("[2] Paint.maxCanvasSize -> 1024")
p = ctx.read_tt(R, 12533)
assert p["maxCanvasSize"] == {"x": 256, "y": 256}
p["maxCanvasSize"] = {"x": 1024, "y": 1024}
write_existing(R, 12533, p)
print("    OK")

# ============================================================================
print("[3] PhysicsManager + [4] productName")
pm = ctx.read_tt(GG, 10)
pm["m_DefaultSolverIterations"] = 10
pm["m_DefaultSolverVelocityIterations"] = 4
pm["m_BounceThreshold"] = 1.0
pm["m_SleepThreshold"] = 0.003
write_existing(GG, 10, pm)
ps = ctx.read_tt(GG, 1)
assert ps["productName"] == "Blue PC Simulator"
ps["productName"] = "Uranium PC Simulator"
write_existing(GG, 1, ps)
print("    OK")

# ============================================================================
print("[5] Заголовок главного меню")
t = ctx.read_tt("level0", 1102)
assert "Blue" in t["m_Text"] and "Simulator" in t["m_Text"]
t["m_Text"] = "<color=cyan>Uranium</color> <color=orange>PC</color> Simulator"
write_existing("level0", 1102, t)
print("    OK:", t["m_Text"])

# ============================================================================
print("[6] Гирлянды (level1,3,4,5,6)")
RAINBOW = [
    (0.000, 1.0, 0.0, 0.0), (0.146, 1.0, 0.5, 0.0), (0.292, 1.0, 1.0, 0.0),
    (0.438, 0.0, 1.0, 0.0), (0.583, 0.0, 1.0, 1.0), (0.729, 0.2, 0.4, 1.0),
    (0.875, 0.6, 0.0, 1.0), (1.000, 1.0, 0.0, 1.0),
]
def rainbow_gradient():
    grad = {("ctime%d" % i): 0 for i in range(8)}
    grad.update({("atime%d" % i): 0 for i in range(8)})
    for i, (tt_, r, g_, b) in enumerate(RAINBOW):
        grad["key%d" % i] = {"r": r, "g": g_, "b": b, "a": 1.0}
        grad["ctime%d" % i] = int(tt_ * 65535)
    grad["atime0"], grad["atime1"] = 0, 65535
    grad["m_Mode"] = 0
    grad["m_NumColorKeys"] = 8
    grad["m_NumAlphaKeys"] = 2
    return grad

for lv in ["level1", "level3", "level4", "level5", "level6"]:
    fid_res = None
    for i, e in enumerate(ctx.files[lv].externals):
        if os.path.basename(e.path.replace("archive:/", "")) == "resources.assets":
            fid_res = i + 1
    assert fid_res, f"{lv}: нет external на resources.assets"
    ps_pid = psr_pid = None
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "ParticleSystem":
            with contextlib.redirect_stderr(io.StringIO()):
                pst = ctx.read_tt(lv, pid)
            go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
            if go["m_Name"] == "SnowParticle":
                ps_pid = pid
                for c in go["m_Component"]:
                    cp = c["component"]["m_PathID"]
                    if cp and ctx.obj(lv, cp).type.name == "ParticleSystemRenderer":
                        psr_pid = cp
    assert ps_pid and psr_pid, f"{lv}: SnowParticle не найден"

    pst = ctx.read_tt(lv, ps_pid)
    sc = pst["InitialModule"]["startColor"]
    sc["minMaxState"] = 4
    sc["maxColor"] = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    sc["minColor"] = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    sc["maxGradient"] = rainbow_gradient()
    im = pst["InitialModule"]
    im["startSpeed"]["scalar"] = 0.25
    im["startSpeed"]["minScalar"] = 0.25
    im["startLifetime"]["scalar"] = 8.0
    im["startLifetime"]["minScalar"] = 8.0
    im["startSize"]["minMaxState"] = 3
    im["startSize"]["scalar"] = 0.75
    im["startSize"]["minScalar"] = 0.4
    pst["EmissionModule"]["rateOverTime"]["scalar"] = 45.0
    write_existing(lv, ps_pid, pst)

    psr = ctx.read_tt(lv, psr_pid)
    psr["m_Materials"] = [{"m_FileID": fid_res, "m_PathID": 57}]  # ParticleFlare
    psr["m_MaxParticleSize"] = 2.0
    write_existing(lv, psr_pid, psr)
    print(f"    {lv}: OK (PS {ps_pid}, PSR {psr_pid}, материал fileID {fid_res})")

# ============================================================================
print("[7] Принтеры 512/1024 + [8] Горизонтальный баннер")
PRINTER_BASE_GO = 1673
SHOPITEM_TMPL = 11097
BANNER_BASE_GO = 1471
BANNERITEM_TMPL = 11143
PAPERFRAME_SAMPLE = 11895
SX, SY = 2.2, 0.45
new_paper_h = 5.1204 * SY
paper_y = (0.308 + 2.5604) - new_paper_h / 2

market = ctx.read_tt(R, 12594)
assert len(market["items"]) == 53

def make_shopitem(newpid, name, price, sprite_pid, spawn_pid, tmpl_pid):
    tt = ctx.read_tt(R, tmpl_pid)
    tt["m_GameObject"] = {"m_FileID": 0, "m_PathID": 0}
    tt["m_Name"] = name
    tt["itemName"] = name
    tt["price"] = price
    tt["bitcoin"] = 5.0
    tt["sprite"] = {"m_FileID": 0, "m_PathID": sprite_pid}
    tt["spawn"] = {"m_FileID": 0, "m_PathID": spawn_pid}
    raw = serialize_raw(R, tt, tmpl_pid)
    ctx.add_object(R, newpid, ClassIDType.MonoBehaviour, raw)

for size, price in [(512, 15000), (1024, 30000)]:
    mapping, data = clone_tree(PRINTER_BASE_GO)
    root_new = mapping[PRINTER_BASE_GO]
    for newpid, (cls, tt, srcpid) in data.items():
        if cls == "GameObject" and srcpid == PRINTER_BASE_GO:
            tt["m_Name"] = f"Apson_A3_{size}"
        elif cls == "MonoBehaviour":
            klass, _ = ctx.mono_class(R, srcpid)
            if klass == "Printer":
                tt["supportedPrintSize"] = {"x": size, "y": size}
            elif klass == "Item":
                tt["spawnId"] = f"Apson_A3_{size}"
    commit_clone(data)
    si_pid = new_pid()
    make_shopitem(si_pid, f"Apson A3 {size}x{size}", price, 699, root_new, SHOPITEM_TMPL)
    market["items"].append({"m_FileID": 0, "m_PathID": si_pid})
    print(f"    принтер {size}: GO {root_new} ({len(data)} об.), ShopItem {si_pid}")

mapping, data = clone_tree(BANNER_BASE_GO)
root_new = mapping[BANNER_BASE_GO]
pf_pid = new_pid()
for newpid, (cls, tt, srcpid) in data.items():
    if cls == "GameObject" and srcpid == BANNER_BASE_GO:
        tt["m_Name"] = "BannerStand_H"
        tt["m_Component"].append({"component": {"m_FileID": 0, "m_PathID": pf_pid}})
    elif cls == "Transform" and srcpid == 4822:
        tt["m_LocalScale"] = {"x": SX, "y": SY, "z": 1.0}
        tt["m_LocalPosition"] = {"x": 0.0, "y": paper_y, "z": 0.169}
    elif cls == "BoxCollider" and srcpid == 9078:
        tt["m_Size"] = {"x": 5.2, "y": 6.57, "z": 0.28}
    elif cls == "MonoBehaviour":
        klass, _ = ctx.mono_class(R, srcpid)
        if klass == "Item":
            tt["spawnId"] = "BannerStand_H"
pf_tmpl = ctx.read_tt(R, PAPERFRAME_SAMPLE)
pf_tt = {"m_GameObject": {"m_FileID": 0, "m_PathID": root_new},
         "m_Enabled": 1, "m_Script": pf_tmpl["m_Script"], "m_Name": ""}
commit_clone(data)
raw = serialize_raw(R, pf_tt, PAPERFRAME_SAMPLE)
ctx.add_object(R, pf_pid, ClassIDType.MonoBehaviour, raw)
b_si = new_pid()
make_shopitem(b_si, "{Horizontal Banner}", 100, 816, root_new, BANNERITEM_TMPL)
market["items"].append({"m_FileID": 0, "m_PathID": b_si})
print(f"    баннер: GO {root_new} ({len(data)} об. + PaperFrame {pf_pid}), ShopItem {b_si}")

print("[9] Market -> 56 товаров")
write_existing(R, 12594, market)

# ============================================================================
print("[10] Translate: Horizontal Banner + убрать (5BTC) у песочницы")
tr = ctx.read_tt(R, 633)
assert tr["m_Name"] == "Translate"
script = tr["m_Script"]
lines = script.rstrip("\n").split("\n")
header = lines[0].split("\t")
langs = header[1:]
idx = {l: i + 1 for i, l in enumerate(langs)}

def set_row(key, values_by_lang, default):
    """Заменить значения существующей строки."""
    for li, ln in enumerate(lines):
        cols = ln.split("\t")
        if cols and cols[0] == key:
            for i in range(1, len(cols)):
                lang = langs[i - 1] if i - 1 < len(langs) else None
                cols[i] = values_by_lang.get(lang, default)
            lines[li] = "\t".join(cols)
            return True
    return False

# Sandbox Mode Price: "Sandbox Mode (5BTC)" -> без цены
assert set_row("Sandbox Mode Price",
               {"RU": "Режим песочницы", "UA": "Режим пісочниці"}, "Sandbox Mode")
# Подпись ошибки (не должна показываться, но пусть не врёт)
set_row("Sandbox Not Enough Bitcoin",
        {"RU": "Режим песочницы сейчас бесплатный.", "UA": "Режим пісочниці тепер безкоштовний."},
        "Sandbox mode is now free.")
# Новая строка Horizontal Banner
row = {"Horizontal Banner": None}
row.update({l: "Horizontal Banner" for l in langs})
row.update({"RU": "Горизонтальный баннер", "UA": "Горизонтальний баннер",
            "DE": "Horizontales Banner", "FR": "Bannière horizontale",
            "FR-CA": "Bannière horizontale", "ES": "Banner horizontal",
            "PL": "Poziomy baner", "TR": "Yatay banner", "KZ": "Көлденең баннер",
            "BY": "Гарызантальны банер"})
new_line = "\t".join(["Horizontal Banner"] + [row.get(l, "Horizontal Banner") for l in langs])
assert new_line.count("\t") == len(langs), "кол-во колонок!"
lines.append(new_line)
tr["m_Script"] = "\n".join(lines) + "\n"
write_existing(R, 633, tr)
print(f"    OK ({len(langs)} языков)")

# ============================================================================
print("[11] Сохранение data.unity3d")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ПАТЧИ ПРИМЕНЕНЫ. Запусти verify_bundle.py для полной проверки.")
