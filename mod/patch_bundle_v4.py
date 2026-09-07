#!/usr/bin/env python3
"""Правки бандла v4 (поверх v3) для Uranium PC Simulator.

  1. Универсальный принтер Apson A3 Universal (1024x1024, 20000$):
     Printer.Supports (патч .so) принимает w==sw и 2w==sw => один принтер
     печатает и 512x512, и 1024x1024. Карточки 512/1024 из маркета убраны,
     новая карточка вставлена сразу после Apson A3 (128x128).
  2. Переключатель баннера на сайте PrintExpert:
     - клон MonoBehaviour PrintExpert (bannerPrefab = горизонтальный 13747)
       добавлен вторым компонентом на GO сайта 1480;
     - клонирована кнопка Purchase (GO 969) -> 'Horizontal', onClick
       m_Target = клон-MB, method 'Purchase';
     - оригинальная кнопка переименована в 'Vertical';
     - .so: Purchase всегда спавнит this.bannerPrefab; SelectFile пишет файл
       в слот, клон-MB (selectedFile==null) берёт его оттуда.
  3. Карточка {Horizontal Banner} (13754) удалена из маркета — баннер
     покупается на сайте PrintExpert.
  4. Стекло: GO 'Crate_Cover_ATX(Glass)' (2832) и 'Crate_Cover_ITX(Glass)'
     (2901) получают TextureLoader (rend=MeshRenderer, matIndex=0) и
     PaperFrame => купленную стеклянную панель можно украсить картинкой,
     приложив её из руки (PaperFrame.OnCollisionEnter).

Запуск: python3 patch_bundle_v4.py [дерево_apktool]   (по умолчанию /tmp/uranium)
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
    ctx.write_tt(fname, pid, tt)

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
            if cls in ("Transform", "RectTransform"):
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

def mono_class_name(pid):
    k, _ = ctx.mono_class(R, pid)
    return k

# ============================================================================
print("[0] Проверка исходных данных")
market = ctx.read_tt(R, 12594)
items = market["items"]
print("    items:", len(items))

print("[1] Универсальный принтер Apson A3 Universal")
PRINTER_BASE_GO = 1673          # Apson A3 128x128 (шаблон v2)
mapping, data = clone_tree(PRINTER_BASE_GO)
root_new = mapping[PRINTER_BASE_GO]
for newpid, (cls, tt, srcpid) in data.items():
    if cls == "GameObject" and srcpid == PRINTER_BASE_GO:
        tt["m_Name"] = "Apson_A3_Universal"
    elif cls == "MonoBehaviour":
        if mono_class_name(srcpid) == "Printer":
            tt["supportedPrintSize"] = {"x": 1024, "y": 1024}
        elif mono_class_name(srcpid) == "Item":
            tt["spawnId"] = "Apson_A3_Universal"
commit_clone(data)
print(f"    принтер: GO {root_new} ({len(data)} об.)")

# ShopItem на основе 13706 (Apson 512x512 из v2)
si_tmpl = ctx.read_tt(R, 13706)
assert si_tmpl["itemName"] == "Apson A3 512x512", si_tmpl["itemName"]
si_new_pid = new_pid()
si_tmpl["m_GameObject"] = {"m_FileID": 0, "m_PathID": 0}
si_tmpl["m_Name"] = "Apson A3 Universal"
si_tmpl["itemName"] = "Apson A3 Universal"
si_tmpl["price"] = 20000
si_tmpl["bitcoin"] = 0.0
si_tmpl["spawn"] = {"m_FileID": 0, "m_PathID": root_new}
raw = serialize_raw(R, si_tmpl, 13706)
ctx.add_object(R, si_new_pid, ClassIDType.MonoBehaviour, raw)
print(f"    ShopItem {si_new_pid}: 'Apson A3 Universal', 20000$, spawn {root_new}")

print("[2] Маркет: убрать 512/1024/{Horizontal Banner}, вставить Universal")
DROP = {13706, 13739, 13754}
kept = [p for p in items if p["m_PathID"] not in DROP]
idx = next(i for i, p in enumerate(kept) if p["m_PathID"] == 11097)  # Apson 128x128
kept.insert(idx + 1, {"m_FileID": 0, "m_PathID": si_new_pid})
market["items"] = kept
write_existing(R, 12594, market)
print(f"    было {len(items)} -> стало {len(kept)}; Universal после позиции {idx}")

print("[3] PrintExpertH: клон MB + кнопка-переключатель")
# 3a. Клон MonoBehaviour PrintExpert (11239) с горизонтальным префабом
pe = ctx.read_tt(R, 11239)
peH_pid = new_pid()
peH = dict(pe)
peH["bannerPrefab"] = {"m_FileID": 0, "m_PathID": 13747}   # горизонтальный
raw = serialize_raw(R, peH, 11239)
ctx.add_object(R, peH_pid, ClassIDType.MonoBehaviour, raw)

# 3b. Добавить клон компонентом на GO сайта 1480
site_go = ctx.read_tt(R, 1480)
assert site_go["m_Name"] == "PrintExpert"
site_go["m_Component"].append({"component": {"m_FileID": 0, "m_PathID": peH_pid}})
write_existing(R, 1480, site_go)
print(f"    PrintExpertH MB {peH_pid} -> GO 1480 (bannerPrefab=13747)")

# 3c. Клон кнопки Purchase (GO 969)
btn_mapping, btn_data = clone_tree(969)
btn_root = btn_mapping[969]
for newpid, (cls, tt, srcpid) in btn_data.items():
    if srcpid == 10661:                          # RectTransform кнопки
        tt["m_AnchoredPosition"] = {"x": 170.0, "y": 30.0}
    elif cls == "MonoBehaviour":
        k = mono_class_name(srcpid)
        if k == "Button":
            # onClick: target = PrintExpertH
            calls = tt["m_OnClick"]["m_PersistentCalls"]["m_Calls"]
            assert len(calls) == 1 and calls[0]["m_MethodName"] == "Purchase", calls
            calls[0]["m_Target"] = {"m_FileID": 0, "m_PathID": peH_pid}
        elif k == "Translate":
            pass                                  # переводы ниже
        elif srcpid == 11296:                     # Text кнопки
            tt["m_Text"] = "Horizontal"
    elif cls == "GameObject" and srcpid == 969:
        tt["m_Name"] = "PurchaseH"
commit_clone(btn_data)
print(f"    кнопка 'Horizontal': GO {btn_root} ({len(btn_data)} об.), target {peH_pid}")

# 3d. Оригинальная кнопка -> 'Vertical', компактная раскладка
orig_text = ctx.read_tt(R, 11296)
orig_text["m_Text"] = "Vertical"
write_existing(R, 11296, orig_text)
tr_orig = ctx.read_tt(R, 10661)
tr_orig["m_AnchoredPosition"] = {"x": 0.0, "y": 30.0}
write_existing(R, 10661, tr_orig)
tr_price = ctx.read_tt(R, 10906)
tr_price["m_AnchoredPosition"] = {"x": 300.0, "y": 30.0}
write_existing(R, 10906, tr_price)
print("    'Vertical' (0,30) + 'Horizontal' (170,30) + Price (300,30)")

print("[4] Стекло: TextureLoader + PaperFrame на панели ATX/ITX")
TEXLOADER_TMPL = 12576    # PictureFrame_2 TextureLoader
PAPERFRAME_TMPL = 11895
for glass_go in (2832, 2901):
    go = ctx.read_tt(R, glass_go)
    mesh_rend = None
    for c in go["m_Component"]:
        pid = c["component"]["m_PathID"]
        if pid and ctx.obj(R, pid).type.name == "MeshRenderer":
            mesh_rend = pid
    assert mesh_rend, f"GO {glass_go}: нет MeshRenderer"
    tl_tmpl = ctx.read_tt(R, TEXLOADER_TMPL)
    tl_pid = new_pid()
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
    pf_pid = new_pid()
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
    print(f"    GO {glass_go} {go['m_Name']!r}: TextureLoader {tl_pid} (rend {mesh_rend}) + PaperFrame {pf_pid}")

print("[5] Сохранение")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ГОТОВО. Запусти verify_v4.py для проверки.")
