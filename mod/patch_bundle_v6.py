#!/usr/bin/env python3
"""Бандл v6 (b8): откат сцен к b5 + только безопасные правки.

Причина краша b7 при загрузке: новые объекты-подарки в файлах сцен
(level1..6) — SIGSEGV в libunity при инициализации сцены. В b8 сцены
ВОЗВРАЩЕНЫ К ОРИГИНАЛУ (восстановлением data.unity3d из v3), подарки
убраны до отдельного исследования (PrefabInstance-механика).

Правки b8 (поверх восстановленного v3-бандла):
  1. Маркет: 53 оригинальных товара (без наших карточек).
  2. Гирлянды (level1/3/4/5): SnowParticle к потолку (y=5.55) +
     неподвижная пелена (speed 0.03, lifetime 30). Только правка полей
     существующих объектов — методика v2, доказано безопасная.
     level6 не трогаем (геометрию фабрики разберём отдельно).
  3. Стекло: TextureLoader + PaperFrame на Crate_Cover_ATX(Glass) и
     Crate_Cover_ITX(Glass) (в b6 с этим краша при загрузке не было).

Запуск: python3 patch_bundle_v6.py [дерево_apktool]
"""
import sys, os, io, contextlib, json

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
from modtools import load_env, Ctx
from UnityPy.enums import ClassIDType
from UnityPy.helpers.TypeTreeHelper import write_typetree as _tth_write
from UnityPy.streams import EndianBinaryWriter

env = load_env()
ctx = Ctx(env)
R = "resources.assets"

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
    ctx.write_tt(fname, pid, tt)

def new_pid(fname):
    if not hasattr(ctx, "_np"):
        ctx._np = {}
    if fname not in ctx._np:
        ctx._np[fname] = ctx.max_path_id(fname) + 1
    p = ctx._np[fname]
    ctx._np[fname] = p + 1
    while p in ctx.files[fname].objects:
        p = ctx._np[fname]
        ctx._np[fname] = p + 1
    return p

print("[0] Контроль: сцены не содержат наших объектов")
for lv in ["level1", "level3", "level4", "level5", "level6"]:
    n_gifts = 0
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "GameObject":
            try:
                g = ctx.read_tt(lv, pid)
            except Exception:
                continue
            if g.get("m_Name", "").startswith("Gift"):
                n_gifts += 1
    assert n_gifts == 0, f"{lv}: найдены объекты Gift — бандл не из v3!"
print("    OK: подарков в сценах нет")

print("[1] Маркет: 53 оригинальных товара")
items = json.load(open("/tmp/v1_items.json"))
assert len(items) == 53
market = ctx.read_tt(R, 12594)
market["items"] = [{"m_FileID": 0, "m_PathID": p} for p in items]
write_existing(R, 12594, market)
print(f"    items: {len(market['items'])}")

print("[2] Гирлянды (level1/3/4/5): к потолку, неподвижная пелена")
CEIL_Y = 5.55
for lv in ["level1", "level3", "level4", "level5"]:
    ps_pid = None
    for pid, o in ctx.files[lv].objects.items():
        if o.type.name == "ParticleSystem":
            with contextlib.redirect_stderr(io.StringIO()):
                pst = ctx.read_tt(lv, pid)
            go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
            if go["m_Name"] == "SnowParticle":
                ps_pid = pid; break
    assert ps_pid, f"{lv}: SnowParticle не найден"
    pst = ctx.read_tt(lv, ps_pid)
    pst["InitialModule"]["startSpeed"]["scalar"] = 0.03
    pst["InitialModule"]["startSpeed"]["minScalar"] = 0.03
    pst["InitialModule"]["startLifetime"]["scalar"] = 30.0
    pst["InitialModule"]["startLifetime"]["minScalar"] = 30.0
    write_existing(lv, ps_pid, pst)
    go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
    trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                 if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
    tr = ctx.read_tt(lv, trpid)
    p = tr["m_LocalPosition"]
    tr["m_LocalPosition"] = {"x": p["x"], "y": CEIL_Y, "z": p["z"]}
    write_existing(lv, trpid, tr)
    print(f"    {lv}: y -> {CEIL_Y}, speed 0.03, life 30")

print("[3] Стекло: TextureLoader + PaperFrame")
TEXLOADER_TMPL = 12576
PAPERFRAME_TMPL = 11895
for glass_go, rend_expect in ((2832, 6028), (2901, 5754)):
    go = ctx.read_tt(R, glass_go)
    # не дублировать, если уже есть (идемпотентность при повторном запуске)
    have = False
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MonoBehaviour":
            cls, _ = ctx.mono_class(R, pid)
            if cls in ("TextureLoader", "PaperFrame"):
                have = True
    if have:
        print(f"    GO {glass_go}: компоненты уже есть — пропуск")
        continue
    mesh_rend = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MeshRenderer":
            mesh_rend = pid
    assert mesh_rend == rend_expect
    tl_tmpl = ctx.read_tt(R, TEXLOADER_TMPL)
    tl_pid = new_pid(R)
    tl = {
        "m_GameObject": {"m_FileID": 0, "m_PathID": glass_go},
        "m_Enabled": 1,
        "m_Script": tl_tmpl["m_Script"],
        "m_Name": "",
        "rend": {"m_FileID": 0, "m_PathID": mesh_rend},
        "matIndex": 0,
    }
    raw = serialize_raw(R, tl, TEXLOADER_TMPL)
    ctx.add_object(R, tl_pid, ClassIDType.MonoBehaviour, raw)
    pf_pid = new_pid(R)
    pf_tmpl = ctx.read_tt(R, PAPERFRAME_TMPL)
    pf = {
        "m_GameObject": {"m_FileID": 0, "m_PathID": glass_go},
        "m_Enabled": 1,
        "m_Script": pf_tmpl["m_Script"],
        "m_Name": "",
    }
    raw = serialize_raw(R, pf, PAPERFRAME_TMPL)
    ctx.add_object(R, pf_pid, ClassIDType.MonoBehaviour, raw)
    go["m_Component"].append({"component": {"m_FileID": 0, "m_PathID": tl_pid}})
    go["m_Component"].append({"component": {"m_FileID": 0, "m_PathID": pf_pid}})
    write_existing(R, glass_go, go)
    print(f"    GO {glass_go} {go['m_Name']!r}: TextureLoader {tl_pid} + PaperFrame {pf_pid}")

print("[4] Сохранение")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ГОТОВО.")
