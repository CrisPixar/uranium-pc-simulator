#!/usr/bin/env python3
"""Правки data.unity3d для мода Uranium PC Simulator (Blue PC Simulator v1.9.1.11).

Изменения:
  1. Grid (LCD-сетка) -> полностью белая RGBA32 (сетка исчезает, экран чистый)
  2. Paint.maxCanvasSize 256 -> 1024 (максимальный холст)
  3. PhysicsManager: SolverIterations 6->10, VelocityIterations 1->4,
     BounceThreshold 2->1, SleepThreshold 0.005->0.003 ("нормальная физика")
  4. PlayerSettings.productName -> "Uranium PC Simulator"
  5. Снег кондиционера -> радужная гирлянда (level1,3,4,5,6):
     материал ParticleFlare, startColor = RandomColor радужный градиент,
     крупнее/медленнее частицы, плотнее emission
  6. Новые принтеры Apson A3 512x512 (15000) и 1024x1024 (30000) — клоны
     префаба 1673 + ShopItem + регистрация в Маркете
  7. Горизонтальный баннер BannerStand_H (100) — клон BannerStand 1471 с
     широким полотном + PaperFrame (ловит брошенные распечатки) + ShopItem
     + регистрация в Маркете
  8. Translate: строка "Horizontal Banner" (мультиязычная)

Результат пишется поверх assets/bin/Data/data.unity3d (оригинал доступен по
ссылке на catbox; .so патчит отдельно mod/patch_so.py).
"""
import sys, os, io, json, struct, shutil

sys.path.insert(0, "/home/user/tools")
from modtools import load_env, Ctx
from UnityPy.enums import ClassIDType

BASE = "/home/user/game_src/Blue_PC_Simulator_v1.9.1.11(1)_base_src"
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")
R = "resources.assets"
GG = "globalgamemanagers"

env = load_env()
ctx = Ctx(env)

# ============================================================================
# Утилиты клонирования
# ============================================================================

def remap_pptrs(obj, mapping):
    """Глубоко заменить PPtr{m_FileID:0, m_PathID in mapping} на новые pid."""
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
    """Все (class, pid) префаба: GO + компоненты + потомки рекурсивно."""
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
    ctx._next_pid = getattr(ctx, "_next_pid", 0) or (ctx.max_path_id(R) + 1)
    p = ctx._next_pid
    ctx._next_pid = p + 1
    while p in ctx.files[R].objects:  # на всякий случай
        p = ctx._next_pid
        ctx._next_pid = p + 1
    return p

def clone_tree(root_go_pid):
    """Клонировать дерево префаба. Возвращает (mapping, data) где
    data = {new_pid: (class_name, tt)} — tt уже с ремапом, но до модификаций."""
    objs = collect_tree(root_go_pid)
    mapping = {pid: new_pid() for _, pid in objs}
    data = {}
    for cls, pid in objs:
        tt = remap_pptrs(ctx.read_tt(R, pid), mapping)
        data[mapping[pid]] = (cls, tt)
    return mapping, data

def serialize_new(newpid, cls, tt, source_pid):
    """Сериализовать tt нового объекта, используя узлы источника, и добавить в файл."""
    src = ctx.obj(R, source_pid)
    if cls == "MonoBehaviour":
        raw = src.save_typetree(tt, nodes=ctx.node_for(R, source_pid, patch_align=True))
    else:
        raw = src.save_typetree(tt)
    ctx.add_object(R, newpid, ClassIDType[cls], raw)

def commit_clone(data):
    """data = {new_pid: (class, tt, source_pid)}; source_pid берём из orig_pid_map."""
    for newpid, (cls, tt, srcpid) in data.items():
        serialize_new(newpid, cls, tt, srcpid)

# модифицированный clone_tree с сохранением источника
def clone_tree2(root_go_pid):
    objs = collect_tree(root_go_pid)
    mapping = {pid: new_pid() for _, pid in objs}
    data = {}
    for cls, pid in objs:
        tt = remap_pptrs(ctx.read_tt(R, pid), mapping)
        data[mapping[pid]] = (cls, tt, pid)
    return mapping, data

def write_existing(fname, pid, tt):
    ctx.write_tt(fname, pid, tt)

# ============================================================================
print("[1] Grid -> белая RGBA32 (без LCD-сетки)")
# ============================================================================
g = ctx.read_tt(R, 117)
assert g["m_Name"] == "Grid" and g["m_Width"] == 32 and g["m_Height"] == 32
W, H, MIPS = 32, 32, 6
px = W * W + 16 * 16 + 8 * 8 + 4 * 4 + 2 * 2 + 1 * 1  # 32..1: 1365 пикселей
img = b"\xff" * (px * 4)
g["m_TextureFormat"] = 4          # RGBA32
g["m_CompleteImageSize"] = px * 4
g["image data"] = img
g["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
write_existing(R, 117, g)
print(f"    формат 34(ETC2)->4(RGBA32), {px*4} байт белого, стрим выключен")

# ============================================================================
print("[2] Paint.maxCanvasSize -> 1024")
# ============================================================================
p = ctx.read_tt(R, 12533)
assert p["maxCanvasSize"] == {"x": 256, "y": 256}
p["maxCanvasSize"] = {"x": 1024, "y": 1024}
write_existing(R, 12533, p)
print("    256x256 -> 1024x1024")

# ============================================================================
print("[3] PhysicsManager + [4] productName")
# ============================================================================
pm = ctx.read_tt(GG, 10)
old_pm = {k: pm[k] for k in ("m_Gravity", "m_DefaultSolverIterations",
        "m_DefaultSolverVelocityIterations", "m_BounceThreshold", "m_SleepThreshold")}
pm["m_DefaultSolverIterations"] = 10
pm["m_DefaultSolverVelocityIterations"] = 4
pm["m_BounceThreshold"] = 1.0
pm["m_SleepThreshold"] = 0.003
write_existing(GG, 10, pm)
print(f"    {old_pm} -> iterations 10/4, bounce 1.0, sleep 0.003 (гравитация не тронута)")

ps = ctx.read_tt(GG, 1)
assert ps["productName"] == "Blue PC Simulator"
ps["productName"] = "Uranium PC Simulator"
write_existing(GG, 1, ps)
print("    productName -> Uranium PC Simulator")

# ============================================================================
print("[5] Гирлянды вместо снега (level1,3,4,5,6)")
# ============================================================================
RAINBOW = [  # (time/65535, r, g, b)
    (0,     1.0, 0.0, 0.0),   # красный
    (0.146, 1.0, 0.5, 0.0),   # оранжевый
    (0.292, 1.0, 1.0, 0.0),   # жёлтый
    (0.438, 0.0, 1.0, 0.0),   # зелёный
    (0.583, 0.0, 1.0, 1.0),   # циан
    (0.729, 0.2, 0.4, 1.0),   # голубой->синий
    (0.875, 0.6, 0.0, 1.0),   # фиолетовый
    (1.0,   1.0, 0.0, 1.0),   # пурпурный
]

def rainbow_gradient():
    grad = {"ctime%d" % i: 0 for i in range(8)}
    grad.update({"atime%d" % i: 0 for i in range(8)})
    for i, (t, r, g_, b) in enumerate(RAINBOW):
        grad["key%d" % i] = {"r": r, "g": g_, "b": b, "a": 1.0}
        grad["ctime%d" % i] = int(t * 65535)
    grad["atime0"] = 0
    grad["atime1"] = 65535
    grad["m_Mode"] = 0
    grad["m_NumColorKeys"] = 8
    grad["m_NumAlphaKeys"] = 2
    return grad

garland_levels = {}
for lv in ["level1", "level3", "level4", "level5", "level6"]:
    fid_res = None
    for i, e in enumerate(ctx.files[lv].externals):
        if os.path.basename(e.path.replace("archive:/", "")) == "resources.assets":
            fid_res = i + 1
    assert fid_res, f"{lv}: нет external на resources.assets!"
    ps_pid = psr_pid = None
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "ParticleSystem":
            pst = ctx.read_tt(lv, pid)
            go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
            if go["m_Name"] == "SnowParticle":
                ps_pid = pid
                for c in go["m_Component"]:
                    cp = c["component"]["m_PathID"]
                    if cp and ctx.obj(lv, cp).type.name == "ParticleSystemRenderer":
                        psr_pid = cp
    assert ps_pid and psr_pid, f"{lv}: SnowParticle не найден!"
    garland_levels[lv] = (ps_pid, psr_pid, fid_res)

for lv, (ps_pid, psr_pid, fid_res) in garland_levels.items():
    # --- ParticleSystem ---
    pst = ctx.read_tt(lv, ps_pid)
    im = pst["InitialModule"]
    sc = im["startColor"]
    sc["minMaxState"] = 4  # RandomColor -> используется maxGradient
    sc["maxColor"] = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    sc["minColor"] = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    sc["maxGradient"] = rainbow_gradient()
    im["startColor"] = sc
    im["startSpeed"]["scalar"] = 0.25
    im["startSpeed"]["minScalar"] = 0.25
    im["startLifetime"]["scalar"] = 8.0
    im["startLifetime"]["minScalar"] = 8.0
    im["startSize"]["minMaxState"] = 3          # случайный размер
    im["startSize"]["scalar"] = 0.75
    im["startSize"]["minScalar"] = 0.4
    pst["EmissionModule"]["rateOverTime"]["scalar"] = 45.0
    write_existing(lv, ps_pid, pst)
    # --- Renderer ---
    psr = ctx.read_tt(lv, psr_pid)
    psr["m_Materials"] = [{"m_FileID": fid_res, "m_PathID": 57}]  # ParticleFlare
    psr["m_MaxParticleSize"] = 2.0
    write_existing(lv, psr_pid, psr)
    print(f"    {lv}: PS {ps_pid} + PSR {psr_pid} -> ParticleFlare({fid_res}:57), радуга, скорость 0.25, размер 0.4-0.75, rate 45")

# ============================================================================
print("[6] Принтеры 512x512 и 1024x1024")
# ============================================================================
PRINTER_BASE_GO = 1673          # Apson_A3 256x256 (не продаётся — идеальный донор)
SHOPITEM_TMPL = 11097           # Apson A3 128x128

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
    serialize_new(newpid, "MonoBehaviour", tt, tmpl_pid)

new_printer_pids = []
for size, price in [(512, 15000), (1024, 30000)]:
    mapping, data = clone_tree2(PRINTER_BASE_GO)
    root_new = mapping[PRINTER_BASE_GO]
    # модификации клонов
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
    # ShopItem
    si_pid = new_pid()
    make_shopitem(si_pid, f"Apson A3 {size}x{size}", price, 699, root_new, SHOPITEM_TMPL)
    market["items"].append({"m_FileID": 0, "m_PathID": si_pid})
    new_printer_pids.append((root_new, si_pid))
    print(f"    Apson A3 {size}x{size}: префаб GO {root_new} ({len(data)} объектов), ShopItem {si_pid}, цена {price}")

# ============================================================================
print("[7] Горизонтальный баннер + PaperFrame")
# ============================================================================
BANNER_BASE_GO = 1471
BANNER_PAPER_GO = 2365
PAPERFRAME_SAMPLE = 11895       # PaperFrame с PictureFrame_2
BANNERITEM_TMPL = 11143         # {Picture Frame} как шаблон цен/полей
# Paper mesh: 2.23 x 5.12, верх на y=2.868 (центр 0.308 + 2.560)
SX, SY = 2.2, 0.45              # полотно 4.91 x 2.30
new_paper_h = 5.1204 * SY
paper_y = (0.308 + 2.5604) - new_paper_h / 2   # верхний край прежний

mapping, data = clone_tree2(BANNER_BASE_GO)
root_new = mapping[BANNER_BASE_GO]
paper_tr_new = mapping[4822]    # Transform полотна
for newpid, (cls, tt, srcpid) in data.items():
    if cls == "GameObject" and srcpid == BANNER_BASE_GO:
        tt["m_Name"] = "BannerStand_H"
    elif cls == "Transform" and srcpid == 4822:
        tt["m_LocalScale"] = {"x": SX, "y": SY, "z": 1.0}
        tt["m_LocalPosition"] = {"x": 0.0, "y": paper_y, "z": 0.169}
    elif cls == "BoxCollider" and srcpid == 9078:   # широкий "захват" под полотно
        tt["m_Size"] = {"x": 5.2, "y": 6.57, "z": 0.28}
    elif cls == "MonoBehaviour":
        klass, _ = ctx.mono_class(R, srcpid)
        if klass == "Item":
            tt["spawnId"] = "BannerStand_H"

# PaperFrame на корневом GO (ловит брошенные распечатки, применяет через TextureLoader)
pf_pid = new_pid()
pf_tmpl = ctx.read_tt(R, PAPERFRAME_SAMPLE)
pf_tt = {
    "m_GameObject": {"m_FileID": 0, "m_PathID": root_new},
    "m_Enabled": 1,
    "m_Script": pf_tmpl["m_Script"],
    "m_Name": "",
}
serialize_new(pf_pid, "MonoBehaviour", pf_tt, PAPERFRAME_SAMPLE)
# добавить в m_Component корня
for newpid, (cls, tt, srcpid) in data.items():
    if cls == "GameObject" and srcpid == BANNER_BASE_GO:
        tt["m_Component"].append({"component": {"m_FileID": 0, "m_PathID": pf_pid}})
commit_clone(data)

b_si = new_pid()
make_shopitem(b_si, "{Horizontal Banner}", 100, 816, root_new, BANNERITEM_TMPL)
market["items"].append({"m_FileID": 0, "m_PathID": b_si})
print(f"    BannerStand_H: GO {root_new} ({len(data)} объектов + PaperFrame {pf_pid}), "
      f"полотно {2.2326*SX:.2f}x{new_paper_h:.2f}, y={paper_y:.3f}, ShopItem {b_si}, цена 100")

# ============================================================================
print("[8] Market: {} товаров".format(53 + 3))
# ============================================================================
write_existing(R, 12594, market)

# ============================================================================
print("[9] Translate: строка Horizontal Banner")
# ============================================================================
tr = ctx.read_tt(R, 633)
assert tr["m_Name"] == "Translate"
lines = tr["m_Script"].split("\n")
header = lines[0].split("\t")
langs = header[1:]
row = {l: "Horizontal Banner" for l in langs}
row.update({
    "EN": "Horizontal Banner", "RU": "Горизонтальный баннер",
    "UA": "Горизонтальний баннер", "DE": "Horizontales Banner",
    "FR": "Bannière horizontale", "FR-CA": "Bannière horizontale",
    "ES": "Banner horizontal", "PL": "Poziomy baner", "TR": "Yatay banner",
    "KZ": "Көлденең баннер", "BY": "Гарызантальны банер",
})
out_row = ["Horizontal Banner"] + [row.get(l, "Horizontal Banner") for l in langs]
tr["m_Script"] = tr["m_Script"].rstrip("\n") + "\n" + "\t".join(out_row) + "\n"
write_existing(R, 633, tr)
print(f"    добавлена строка ({len(langs)} языков), RU='{row['RU']}'")

# ============================================================================
print("[10] Сохранение data.unity3d")
# ============================================================================
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out)} байт в {BUNDLE}")
print("ГОТОВО")
