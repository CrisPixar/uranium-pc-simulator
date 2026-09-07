#!/usr/bin/env python3
"""Бандл v7 (b9): стекло печатает КАРТИНКУ, а не «весь верх коробки».

Проблема b8: у Crate_Cover_ATX/ITX(Glass) меш Crate (402) — ОДИН submesh и
ОДИН материал: TextureLoader с matIndex=0 красил весь меш (стенки+верх).

Решение (не трогая оригинальные объекты — только клоны в resources.assets):
  1. Клон меша Crate -> «Crate_Glass»: те же вершины/UV, но индексный буфер
     переупорядочен [стенки+t10/t11 | верх t8/t9] и РАЗБИТ на 2 submesh:
       sub[0] = стенки+низ (30 индексов), sub[1] = верхняя грань (6 индексов).
  2. Клон материала 22 -> «Crate_Glass»: та же текстура 184, но _MainTex
     scale/offset скомпенсированы под UV-окно верхней грани
     (окно u[0.425..0.575] v[0.375..0.625] -> вся текстура [0..1]):
       scale=(6.6666665, 4.0), offset=(-2.8333333, -1.5).
     => в покое верх выглядит как обычно (текстура ящика),
        при печати TextureLoader подставляет картинку и она занимает ВСЁ стекло.
  3. GO 2832 (ATX Glass) и GO 2901 (ITX Glass):
     MeshFilter -> клон меша, MeshRenderer.m_Materials -> [Crate, Crate_Glass],
     TextureLoader.matIndex 0 -> 1.

Остальное (маркет 53, гирлянды level1/3/4/5, PrintExpert alertText=13747)
уже в бандле b8 — скрипт работает поверх текущего /tmp/uranium.
Запуск: python3 patch_bundle_v7.py [дерево_apktool]
"""
import sys, os, struct

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

MESH_SRC = 402          # Mesh Crate
MAT_SRC = 22            # Material Crate
GLASS = [               # GO, MeshFilter, MeshRenderer, TextureLoader
    (2832, 6663, 6028, 13755),   # Crate_Cover_ATX(Glass)
    (2901, 6519, 5754, 13757),   # Crate_Cover_ITX(Glass)
]

def serialize_raw(fname, tt, source_pid):
    o = ctx.obj(fname, source_pid)
    if o.type.name == "MonoBehaviour":
        node = ctx.node_for(fname, source_pid, patch_align=True)
    else:
        node = o._get_typetree_node(None)
    writer = EndianBinaryWriter(endian=o.reader.endian)
    _tth_write(tt, node, writer, ctx.files[fname])
    return writer.bytes

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

def write_existing(fname, pid, tt):
    ctx.write_tt(fname, pid, tt)

# ============================================================================
print("[1] Клон меша Crate -> Crate_Glass (2 submesh: стенки+низ | верх)")
mesh = ctx.read_tt(R, MESH_SRC)
assert mesh["m_Name"] == "Crate", mesh["m_Name"]
idx = list(mesh["m_IndexBuffer"])
assert len(idx) == 72, len(idx)  # 36 индексов u16
tri = [struct.unpack_from("<3H", bytes(idx), i * 6) for i in range(12)]
# верх = t8 (16,17,18), t9 (16,18,19); низ = t10 (20,21,22), t11 (20,22,23)
assert tri[8] == (16, 17, 18) and tri[9] == (16, 18, 19)
assert tri[10] == (20, 21, 22) and tri[11] == (20, 22, 23)
new_idx = b"".join(
    struct.pack("<3H", *tri[i]) for i in (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 8, 9)
)
# sub[0]: 30 индексов (байты 0..59), sub[1]: 6 индексов (байты 60..71)
sm0 = dict(mesh["m_SubMeshes"][0])
sm1 = dict(mesh["m_SubMeshes"][0])
sm0["firstByte"] = 0
sm0["indexCount"] = 30
sm1["firstByte"] = 60
sm1["indexCount"] = 6
mesh["m_Name"] = "Crate_Glass"
mesh["m_IndexBuffer"] = list(new_idx)
mesh["m_SubMeshes"] = [sm0, sm1]
# idempotent: ищем существующий клон по имени
mesh_pid = None
for pid, o in ctx.files[R].objects.items():
    if o.type.name == "Mesh":
        try:
            nm = ctx.read_tt(R, pid)["m_Name"]
        except Exception:
            continue
        if nm == "Crate_Glass":
            mesh_pid = pid
            break
if mesh_pid is None:
    mesh_pid = new_pid(R)
    raw = serialize_raw(R, mesh, MESH_SRC)
    ctx.add_object(R, mesh_pid, ClassIDType.Mesh, raw)
    print(f"    Mesh {mesh_pid} «Crate_Glass»: 24 верт., sub0=30 ind, sub1=6 ind (верх)")
else:
    raw = serialize_raw(R, mesh, MESH_SRC)
    o = ctx.obj(R, mesh_pid)
    o.data = raw
    print(f"    Mesh {mesh_pid} «Crate_Glass» обновлён")

print("[2] Клон материала Crate -> Crate_Glass (scale/offset под UV-окно)")
mat = ctx.read_tt(R, MAT_SRC)
assert mat["m_Name"] == "Crate", mat["m_Name"]
SU, SV = 1.0 / 0.15, 1.0 / 0.25          # 6.6667, 4.0
OU, OV = -0.425 * SU, -0.375 * SV        # -2.8333, -1.5
sp = mat["m_SavedProperties"]
texenvs = []
for k, v in sp["m_TexEnvs"]:
    v = dict(v)
    if k == "_MainTex":
        v["m_Scale"] = {"x": SU, "y": SV}
        v["m_Offset"] = {"x": OU, "y": OV}
    texenvs.append((k, v))
sp["m_TexEnvs"] = texenvs
mat["m_Name"] = "Crate_Glass"
mat_pid = None
for pid, o in ctx.files[R].objects.items():
    if o.type.name == "Material":
        try:
            nm = ctx.read_tt(R, pid)["m_Name"]
        except Exception:
            continue
        if nm == "Crate_Glass":
            mat_pid = pid
            break
if mat_pid is None:
    mat_pid = new_pid(R)
    raw = serialize_raw(R, mat, MAT_SRC)
    ctx.add_object(R, mat_pid, ClassIDType.Material, raw)
    print(f"    Material {mat_pid} «Crate_Glass»: scale=({SU:.4f},{SV:.1f}) offset=({OU:.4f},{OV:.1f})")
else:
    raw = serialize_raw(R, mat, MAT_SRC)
    o = ctx.obj(R, mat_pid)
    o.data = raw
    print(f"    Material {mat_pid} «Crate_Glass» обновлён")

print("[3] GO стекла: MeshFilter -> клон, MR -> 2 материала, TextureLoader.matIndex=1")
for go_pid, mf_pid, mr_pid, tl_pid in GLASS:
    go = ctx.read_tt(R, go_pid)
    mf = ctx.read_tt(R, mf_pid)
    mr = ctx.read_tt(R, mr_pid)
    tl = ctx.read_tt(R, tl_pid)
    name = go["m_Name"]
    assert mf["m_Mesh"]["m_PathID"] == MESH_SRC, (name, mf["m_Mesh"])
    assert tl["rend"]["m_PathID"] == mr_pid, (name, tl["rend"])
    mats = mr["m_Materials"]
    if len(mats) == 1:
        mats.append({"m_FileID": 0, "m_PathID": mat_pid})
    else:
        assert mats[1]["m_PathID"] == mat_pid
    mf["m_Mesh"] = {"m_FileID": 0, "m_PathID": mesh_pid}
    tl["matIndex"] = 1
    write_existing(R, mf_pid, mf)
    write_existing(R, mr_pid, mr)
    write_existing(R, tl_pid, tl)
    print(f"    {name}: mesh={mesh_pid}, mats=[22,{mat_pid}], TextureLoader.matIndex=1")

print("[4] Сохранение")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ГОТОВО.")
