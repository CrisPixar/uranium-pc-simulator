#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b17b: 3D-гирлянда + текст «+N BTC».

1. 3D-ГИРЛЯНДА В МЕНЮ (level0). На задней стене (z≈11.5) вешаем ряд
   «лампочек» — маленькие сферы (встроенный Sphere), чередуются красный/
   зелёный. Материалы — клоны «Lamp» (sharedassets0, pid 15, уже со
   свечением _EmissionColor): GarlandRed и GarlandGreen.

2. ТЕКСТ «+N BTC» (level0). Клонируем Text кнопки CH (pid 1347) в новый
   объект «BtcPop» на канвасе меню (родитель — канвас, как у заголовка).
   Пустой текст, невидим до показа. Нативный код (mod/patch_b17.py) пишет
   «+N BTC» и прячет через 10 секунд.

Запуск: python3 mod/patch_bundle_b17b.py [дерево]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import struct
import sys

import UnityPy
from UnityPy.files.ObjectReader import ObjectReader

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

# встроенные меши "unity default resources" (level0 fileID=3)
SPHERE = {"m_FileID": 3, "m_PathID": 10207}

GREEN_MAT = "GarlandGreen"
RED_MAT = "GarlandRed"
BULB_NAME = "GarlandBulb"
BTCPOP = "BtcPop"


def new_object(sf, src_pid, pid, tree=None, raw=None):
    src = sf.objects[src_pid]
    obj = ObjectReader(sf, src.reader, pid, src.type_id, src.serialized_type,
                       src.class_id, src.type, src.byte_start, src.byte_size,
                       src.is_destroyed, src.is_stripped)
    if raw is not None:
        obj.set_raw_data(raw)
    else:
        obj.save_typetree(tree)
    sf.objects[pid] = obj
    return obj


def find_go(sf, name):
    for pid, o in sf.objects.items():
        if o.type.name == "GameObject":
            try:
                if o.read_typetree()["m_Name"] == name:
                    return pid
            except Exception:
                pass
    return None


def make_garland_materials(sa0):
    """Клоны Lamp (pid 15) -> GarlandRed / GarlandGreen."""
    out = {}
    for name, color in [(RED_MAT, (1.0, 0.0, 0.0, 1.0)),
                        (GREEN_MAT, (0.0, 1.0, 0.0, 1.0))]:
        existing = [pid for pid, o in sa0.objects.items()
                    if o.type.name == "Material"
                    and o.read_typetree().get("m_Name") == name]
        if existing:
            out[name] = existing[0]
            continue
        pid = max(sa0.objects) + 1
        tree = sa0.objects[15].read_typetree()
        tree["m_Name"] = name
        cols = list(tree["m_SavedProperties"]["m_Colors"])
        for i, (k, v) in enumerate(cols):
            if k == "_Color":
                v = dict(v); v.update({"r": color[0], "g": color[1],
                                       "b": color[2], "a": color[3]})
                cols[i] = (k, v)
            if k == "_EmissionColor":
                v = dict(v); v.update({"r": color[0], "g": color[1],
                                       "b": color[2], "a": 1.0})
                cols[i] = (k, v)
        tree["m_SavedProperties"]["m_Colors"] = cols
        new_object(sa0, 15, pid, tree=tree)
        out[name] = pid
        print(f"[sharedassets0] материал {name} (pid {pid})")
    return out


def add_bulbs(level0, mat_green, mat_red):
    """Ряд лампочек-сфер на задней стене меню."""
    if find_go(level0, f"{BULB_NAME}_0") is not None:
        print("[level0] гирлянда уже есть")
        return
    pid = max(level0.objects) + 1
    count = 24
    import math
    for i in range(count):
        t = i / (count - 1)
        x = -8.0 + 16.0 * t
        y = 5.6 - 0.7 * math.sin(math.pi * t)   # лёгкая дуга
        z = 11.5
        mat = mat_green if i % 2 == 0 else mat_red
        # Transform
        tf_pid = pid
        tf_tree = level0.objects[306].read_typetree()  # Transform шаблон (Snow)
        tf_tree["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid + 3}
        tf_tree["m_Father"] = {"m_FileID": 0, "m_PathID": 0}
        tf_tree["m_Children"] = []
        tf_tree["m_LocalPosition"] = {"x": x, "y": y, "z": z}
        tf_tree["m_LocalScale"] = {"x": 0.22, "y": 0.22, "z": 0.22}
        tf_tree["m_LocalRotation"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        new_object(level0, 306, tf_pid, tree=tf_tree)
        # MeshFilter
        mf_pid = pid + 1
        mf_tree = level0.objects[423].read_typetree()  # MeshFilter шаблон (Snow)
        mf_tree["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid + 3}
        mf_tree["m_Mesh"] = SPHERE
        new_object(level0, 423, mf_pid, tree=mf_tree)
        # MeshRenderer
        mr_pid = pid + 2
        mr_tree = level0.objects[378].read_typetree()  # MeshRenderer (Snow)
        mr_tree["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid + 3}
        mr_tree["m_Materials"] = [{"m_FileID": 2, "m_PathID": mat}]
        new_object(level0, 378, mr_pid, tree=mr_tree)
        # GameObject
        go_pid = pid + 3
        go_tree = level0.objects[141].read_typetree()  # GameObject шаблон (Snow)
        go_tree["m_Name"] = f"{BULB_NAME}_{i}"
        go_tree["m_Component"] = [
            {"component": {"m_FileID": 0, "m_PathID": tf_pid}},
            {"component": {"m_FileID": 0, "m_PathID": mf_pid}},
            {"component": {"m_FileID": 0, "m_PathID": mr_pid}},
        ]
        new_object(level0, 141, go_pid, tree=go_tree)
        pid += 4
    print(f"[level0] гирлянда: {count} лампочек")


def add_btcpop(level0):
    """Клонируем Text CH (1347) -> «BtcPop» на канвасе."""
    if find_go(level0, BTCPOP) is not None:
        print("[level0] BtcPop уже есть")
        return
    pid = max(level0.objects) + 1
    # родитель — канвас (как у заголовка, RT 872)
    parent_rt = 872
    # RectTransform (клон CH_Btn 1345)
    rt_pid = pid
    rt_tree = level0.objects[1345].read_typetree()
    rt_tree["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid + 3}
    rt_tree["m_Father"] = {"m_FileID": 0, "m_PathID": parent_rt}
    rt_tree["m_AnchorMin"] = {"x": 0.5, "y": 0.5}
    rt_tree["m_AnchorMax"] = {"x": 0.5, "y": 0.5}
    rt_tree["m_AnchoredPosition"] = {"x": 0.0, "y": 160.0}
    rt_tree["m_SizeDelta"] = {"x": 400.0, "y": 80.0}
    new_object(level0, 1345, rt_pid, tree=rt_tree)
    # CanvasRenderer (клон CH_Btn 1346)
    cr_pid = pid + 1
    cr_tree = level0.objects[1346].read_typetree()
    cr_tree["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid + 3}
    new_object(level0, 1346, cr_pid, tree=cr_tree)
    # Text (клон CH_Btn 1347, raw: m_Text "CH" -> "")
    text_pid = pid + 2
    raw = bytearray(level0.objects[1347].get_raw_data())
    struct.pack_into("<iq", raw, 0, 0, pid + 3)      # m_GameObject
    # m_Text -> "" (смещение 144: длина, 148: байты)
    struct.pack_into("<i", raw, 144, 0)
    raw[148:152] = b"\x00" * 4
    new_object(level0, 1347, text_pid, raw=bytes(raw))
    # GameObject
    go_pid = pid + 3
    go_tree = level0.objects[1344].read_typetree()  # CH_Btn GO
    go_tree["m_Name"] = BTCPOP
    go_tree["m_IsActive"] = True
    go_tree["m_Component"] = [
        {"component": {"m_FileID": 0, "m_PathID": rt_pid}},
        {"component": {"m_FileID": 0, "m_PathID": cr_pid}},
        {"component": {"m_FileID": 0, "m_PathID": text_pid}},
    ]
    new_object(level0, 1344, go_pid, tree=go_tree)
    # прицепить к родителю (канвас)
    parent = level0.objects[parent_rt].read_typetree()
    parent["m_Children"].append({"m_FileID": 0, "m_PathID": rt_pid})
    level0.objects[parent_rt].save_typetree(parent)
    print(f"[level0] BtcPop (GO {go_pid}) на канвасе")


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]
    sa0 = bf.files["sharedassets0.assets"]
    l0 = bf.files["level0"]

    mats = make_garland_materials(sa0)
    add_bulbs(l0, mats[GREEN_MAT], mats[RED_MAT])
    add_btcpop(l0)

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
