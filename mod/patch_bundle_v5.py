#!/usr/bin/env python3
"""Правки бандла v5 (b7) — поверх v3 (b5). Откат v4-экспериментов.

  1. Маркет: 53 оригинальных товара (убраны наши карточки 512/1024/баннер —
     они ломали загрузку сайта Market: мусорная карточка 'Title' + обрыв).
     Универсальность принтеров даёт патч .so (Supports ×1/2/4/8).
  2. Гирлянды: SnowParticle поднять К ПОТОЛКУ (level5 висел на y=17 над
     потолком, level6 — на y=2.6 посреди стены) и сделать частицы почти
     неподвижными (speed 0.03, lifetime 30) — радужная пелена у потолка.
  3. НГ-подарки: инстансы префаба Gift (1631) на level1,3,4,5 — по 4 на полу
     + 1 на кондиционере; на level6 — рядом с точкой старта игрока.
  4. Стекло: TextureLoader (rend=MeshRenderer панели, matIndex=0) + PaperFrame
     на GO 'Crate_Cover_ATX(Glass)' (2832) и 'Crate_Cover_ITX(Glass)' (2901).
     Работает для СВЕЖЕКУПЛЕННЫХ панелей (старые из сейва не пересоздаются).

Запуск: python3 patch_bundle_v5.py [дерево_apktool]
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

def ext_fid(fname, target_basename):
    """m_FileID ссылки из файла fname на файл target_basename (0 = сам fname)."""
    for i, e in enumerate(ctx.files[fname].externals):
        if os.path.basename(e.path.replace("archive:/", "")) == target_basename:
            return i + 1
    return None

# ============================================================================
print("[1] Маркет: 53 оригинальных товара")
ORIG53 = [11098, 11099, 11097, 11100, 11101, 11102, 11104, 11105, 11114, 11115,
          11116, 11117, 11118, 11119, 11120, 11121, 11122, 11123, 11124, 11125,
          11126, 11127, 11128, 11129, 11130, 11131, 11132, 11133, 11134, 11135,
          11136, 11137, 11138, 11139, 11140, 11141, 11142, 11143, 11144, 11145,
          11146, 11147, 11148, 11149, 11150, 11151, 11152, 11153, 11154, 11155,
          11156, 11157, 11158]
# надёжнее: прочитать список из json, а константа выше — контроль длины
import json
items = json.load(open("/tmp/v1_items.json"))
assert len(items) == 53, len(items)
market = ctx.read_tt(R, 12594)
market["items"] = [{"m_FileID": 0, "m_PathID": p} for p in items]
write_existing(R, 12594, market)
print(f"    items: {len(market['items'])} (наши карточки убраны)")

# ============================================================================
print("[2] Гирлянды: к потолку + неподвижная радужная пелена")
FLOOR_Y = -3.8
CEIL_Y = 5.55          # потолок ~5.69 (Lamp), пелена чуть ниже
for lv in ["level1", "level3", "level4", "level5", "level6"]:
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
    # позиция
    go = ctx.read_tt(lv, pst["m_GameObject"]["m_PathID"])
    trpid = next(c["component"]["m_PathID"] for c in go["m_Component"]
                 if c["component"]["m_PathID"] and ctx.obj(lv, c["component"]["m_PathID"]).type.name == "Transform")
    tr = ctx.read_tt(lv, trpid)
    if lv == "level6":
        # Factory: перенести к точке старта игрока, чуть выше
        pl_pid = None
        for pid, o in ctx.files[lv].objects.items():
            if o.type.name != "GameObject": continue
            try: g = ctx.read_tt(lv, pid)
            except: continue
            if g.get("m_Name") == "Player":
                for c in g["m_Component"]:
                    cp = c["component"]["m_PathID"]
                    if cp and ctx.obj(lv, cp).type.name == "Transform":
                        pl_pid = cp; break
                break
        plt = ctx.read_tt(lv, pl_pid)
        pp = plt["m_LocalPosition"]
        tr["m_Father"] = dict(plt["m_Father"])
        tr["m_LocalPosition"] = {"x": pp["x"], "y": pp["y"] + 5.0, "z": pp["z"]}
    else:
        p = tr["m_LocalPosition"]
        tr["m_LocalPosition"] = {"x": p["x"], "y": CEIL_Y, "z": p["z"]}
    write_existing(lv, trpid, tr)
    print(f"    {lv}: speed 0.03, life 30, y -> {tr['m_LocalPosition']['y']}")

# ============================================================================
print("[3] НГ-подарки (Gift 1631) на сценах")
GIFT_GO = 1631
def collect_tree_res(root_go_pid):
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
        if tr:
            for ch in tr["m_Children"]:
                cht = ctx.read_tt(R, ch["m_PathID"])
                walk_go(cht["m_GameObject"]["m_PathID"])
    walk_go(root_go_pid)
    return objs

GIFT_TREE = collect_tree_res(GIFT_GO)
GIFT_COMP = {pid: cls for cls, pid in GIFT_TREE}
GIFT_ROOT_TR = next(pid for c in ctx.read_tt(R, GIFT_GO)["m_Component"]
                    if (pid := c["component"]["m_PathID"]) and ctx.obj(R, pid).type.name == "Transform")

def add_gift(lv, pos, name="Gift"):
    """Создать копию дерева Gift в файле сцены lv с позицией pos."""
    fid_res = ext_fid(lv, "resources.assets")
    fid_gg = ext_fid(lv, "globalgamemanagers.assets")
    assert fid_res and fid_gg, f"{lv}: нет externals"
    mapping = {pid: new_pid(lv) for _, pid in GIFT_TREE}
    # remap: внутренние -> {0,new}; ресурсы resources.assets -> {fid_res,old};
    # MonoScript (m_FileID=1 = globalgamemanagers в resources) -> {fid_gg,old}
    def conv(obj):
        if isinstance(obj, dict):
            if set(obj.keys()) == {"m_FileID", "m_PathID"}:
                fid, pid = obj["m_FileID"], obj["m_PathID"]
                if fid == 0 and pid in mapping:
                    return {"m_FileID": 0, "m_PathID": mapping[pid]}
                if fid == 0 and pid and ctx.obj(R, pid) is not None:
                    return {"m_FileID": fid_res, "m_PathID": pid}
                if fid == 1:
                    return {"m_FileID": fid_gg, "m_PathID": pid}
                return obj
            return {k: conv(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [conv(v) for v in obj]
        return obj
    father = {"m_FileID": 0, "m_PathID": 0}
    for cls, pid in GIFT_TREE:
        tt = conv(ctx.read_tt(R, pid))
        npid = mapping[pid]
        if cls == "GameObject" and pid == GIFT_GO:
            tt["m_Name"] = name
        if cls == "Transform" and pid == GIFT_ROOT_TR:
            tt["m_LocalPosition"] = {"x": pos[0], "y": pos[1], "z": pos[2]}
            tt["m_Father"] = dict(father)
            tt["m_Children"] = []
        raw = serialize_raw(R, tt, pid)
        ctx.add_object(lv, npid, ClassIDType[cls], raw)
    return mapping[GIFT_GO]

GIFTS = {
    "level1": [(-8.0, -3.3, -8.0), (0.0, -3.3, -9.0), (7.5, -3.3, -6.0), (5.0, -3.3, 7.0), (9.0, 4.55, -11.0)],
    "level3": [(-8.0, -3.3, -8.0), (0.0, -3.3, -9.0), (7.5, -3.3, -6.0), (5.0, -3.3, 7.0), (9.0, 4.55, -11.0)],
    "level4": [(-7.0, -3.3, 14.0), (2.0, -3.3, 16.0), (-6.0, -3.3, 8.0), (6.0, -3.3, 10.0), (14.0, 4.55, -21.0)],
    "level5": [(-7.0, -3.3, 14.0), (2.0, -3.3, 16.0), (-6.0, -3.3, 8.0), (6.0, -3.3, 10.0), (9.0, 4.55, -21.0)],
}
for lv, positions in GIFTS.items():
    for i, pos in enumerate(positions):
        add_gift(lv, pos, name=f"Gift{i+1}")
    print(f"    {lv}: {len(positions)} подарков")
# level6: рядом со стартом игрока (тот же родитель, что у Player)
lv = "level6"
pl_pid = None
for pid, o in ctx.files[lv].objects.items():
    if o.type.name != "GameObject": continue
    try: g = ctx.read_tt(lv, pid)
    except: continue
    if g.get("m_Name") == "Player":
        for c in g["m_Component"]:
            cp = c["component"]["m_PathID"]
            if cp and ctx.obj(lv, cp).type.name == "Transform":
                pl_pid = cp; break
        break
plt = ctx.read_tt(lv, pl_pid)
pp = plt["m_LocalPosition"]
for dx, dz in ((2.5, 1.0), (3.5, -1.0)):
    add_gift(lv, (pp["x"] + dx, pp["y"] - 1.0, pp["z"] + dz), name="Gift")
print(f"    level6: 2 подарка у старта игрока")

# ============================================================================
print("[4] Стекло: TextureLoader + PaperFrame на ATX/ITX панелях")
TEXLOADER_TMPL = 12576
PAPERFRAME_TMPL = 11895
for glass_go, rend_expect in ((2832, 6028), (2901, 5754)):
    go = ctx.read_tt(R, glass_go)
    mesh_rend = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MeshRenderer":
            mesh_rend = pid
    assert mesh_rend == rend_expect, (glass_go, mesh_rend)
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

# ============================================================================
print("[5] Сохранение")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ГОТОВО.")
