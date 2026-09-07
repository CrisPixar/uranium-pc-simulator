#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b17c (исправления b17/b17b).

1. ГИРЛЯНДА: лампочки ссылались на встроенную сферу `unity default resources`
   (m_FileID 3, pathID 10207), которой НЕТ в собранном бандле (unity_builtin_extra
   содержит только шейдеры) -> лампочки невидимы. Заменяем меш на «Capacitor»
   (sharedassets0 pid 84, цилиндр ~0.3×0.5), fileID 2 для level0. Масштаб 0.22 -> 1.5.

2. СНЕЖИНКИ: эмиттер был поднят на y=8.0, но потолок комнаты — y≈5.75
   (Room mesh extent). Снежинки висели в пустоте НАД потолком. Опускаем к потолку
   (y=5.5), полосу эмиссии сужаем (shapeY 4 -> 2).

3. СНЕГ НА СТОЛ: объект «Snow» (level0) стоял в y=-2.95 — внутри стола
   (столешница на y=-1.75), поэтому невидим. Поднимаем на столешницу (y=-1.6)
   и уменьшаем до размера стола (scale 0.5).

Запуск: python3 mod/patch_bundle_b17c.py [дерево]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import sys

import UnityPy

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

SNOW_LEVELS = ["level1", "level3", "level4", "level5", "level6"]

# меш-«лампочка» для гирлянды: Capacitor (sharedassets0 pid 84), fileID 2 (level0)
BULB_MESH = {"m_FileID": 2, "m_PathID": 84}
BULB_SCALE = 1.5


def find_go(sf, name):
    for pid, o in sf.objects.items():
        if o.type.name == "GameObject":
            try:
                if o.read_typetree()["m_Name"] == name:
                    return pid
            except Exception:
                pass
    return None


def get_transform(sf, go_pid):
    t = sf.objects[go_pid].read_typetree()
    for c in t.get("m_Component", []):
        cp = c["component"]["m_PathID"]
        if cp in sf.objects and sf.objects[cp].type.name in ("Transform", "RectTransform"):
            return cp
    return None


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]
    l0 = bf.files["level0"]

    # ── 1. гирлянда: меш + масштаб ──
    fixed = 0
    for pid, o in l0.objects.items():
        if o.type.name != "GameObject":
            continue
        try:
            name = o.read_typetree()["m_Name"]
        except Exception:
            continue
        if not str(name).startswith("GarlandBulb"):
            continue
        t = o.read_typetree()
        for c in t["m_Component"]:
            cp = c["component"]["m_PathID"]
            if cp not in l0.objects:
                continue
            ctn = l0.objects[cp].type.name
            if ctn == "MeshFilter":
                mf = l0.objects[cp].read_typetree()
                if mf.get("m_Mesh") != BULB_MESH:
                    mf["m_Mesh"] = BULB_MESH
                    l0.objects[cp].save_typetree(mf)
                    fixed += 1
            elif ctn == "Transform":
                tr = l0.objects[cp].read_typetree()
                if abs(tr["m_LocalScale"]["x"] - BULB_SCALE) > 0.01:
                    tr["m_LocalScale"] = {"x": BULB_SCALE, "y": BULB_SCALE, "z": BULB_SCALE}
                    l0.objects[cp].save_typetree(tr)
    print(f"[level0] гирлянда: меш->Capacitor у {fixed} лампочек")

    # ── 2. снежинки к потолку ──
    for lvl in SNOW_LEVELS:
        lv = bf.files.get(lvl)
        if lv is None:
            continue
        sp = find_go(lv, "SnowParticle")
        if sp is None:
            continue
        tr = get_transform(lv, sp)
        tt = lv.objects[tr].read_typetree()
        if abs(tt["m_LocalPosition"]["y"] - 5.5) > 0.01:
            tt["m_LocalPosition"]["y"] = 5.5
            lv.objects[tr].save_typetree(tt)
            print(f"[{lvl}] SnowParticle -> y=5.5 (потолок)")
        # сузить полосу эмиссии
        t = lv.objects[sp].read_typetree()
        ps_pid = None
        for c in t["m_Component"]:
            cp = c["component"]["m_PathID"]
            if cp in lv.objects and lv.objects[cp].type.name == "ParticleSystem":
                ps_pid = cp
                break
        if ps_pid is None:
            continue
        ps = lv.objects[ps_pid].read_typetree()
        sm = ps["ShapeModule"]
        if sm.get("m_Scale", {}).get("y") != 2.0:
            sm["m_Scale"]["y"] = 2.0
            ps["ShapeModule"] = sm
            lv.objects[ps_pid].save_typetree(ps)
            print(f"[{lvl}] SnowParticle shapeY=2")

    # ── 3. снег на стол ──
    snow = find_go(l0, "Snow")
    table = find_go(l0, "Table")
    if snow is not None and table is not None:
        tr_snow = get_transform(l0, snow)
        tr_tbl = get_transform(l0, table)
        st = l0.objects[tr_snow].read_typetree()
        tp = l0.objects[tr_tbl].read_typetree()["m_LocalPosition"]
        # столешница: стол y=-3.75, extent y=2 -> верх -1.75
        target = {"x": tp["x"], "y": -1.6, "z": tp["z"]}
        cur = st["m_LocalPosition"]
        if (cur["x"], cur["y"], cur["z"]) != (target["x"], target["y"], target["z"]):
            st["m_LocalPosition"] = target
            l0.objects[tr_snow].save_typetree(st)
            print(f"[level0] Snow -> на столешницу {target}")
        sc = st["m_LocalScale"]
        if abs(sc["x"] - 0.5) > 0.01:
            st["m_LocalScale"] = {"x": 0.5, "y": 0.5, "z": 0.5}
            l0.objects[tr_snow].save_typetree(st)
            print("[level0] Snow scale -> 0.5")

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
