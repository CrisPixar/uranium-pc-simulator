#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b17: подарки/снег.

1. ЗЕЛЁНЫЙ ПОДАРОК: стоял в той же точке (x,z), что и мусорка, и «тонул» в ней —
   поэтому «пропадал/появлялся» при ходьбе (перекрытие геометрии). Сдвигаем его
   рядом с мусоркой (x + 1.5), на пол.

2. СНЕЖИНКИ (радужные, ParticleSystem «SnowParticle»): ускоряем падение
   (startSpeed 0.03 -> 0.5) и добавляем гравитацию (0 -> 0.15); эмиттер
   поднимаем к потолку (y=8.0) и делаем тонкой полосой (scaleY 24 -> 4).

3. СНЕГ В МЕНЮ: объект «Snow» (level0) был под полом (y=-7.5) — невидим.
   Ставим его на стол (Table).

Запуск: python3 mod/patch_bundle_b17.py [дерево]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import sys

import UnityPy

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

# уровни с подарком: имя -> смещение зелёного подарка по X
GIFT_LEVELS = ["level1", "level3", "level4", "level5"]
SNOW_LEVELS = ["level1", "level3", "level4", "level5", "level6"]


def get_transform(sf, go_pid):
    t = sf.objects[go_pid].read_typetree()
    for c in t.get("m_Component", []):
        cp = c["component"]["m_PathID"]
        if cp in sf.objects and sf.objects[cp].type.name in ("Transform", "RectTransform"):
            return cp
    return None


def find_go(sf, name):
    for pid, o in sf.objects.items():
        if o.type.name == "GameObject":
            try:
                if o.read_typetree()["m_Name"] == name:
                    return pid
            except Exception:
                pass
    return None


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]

    # ── 1. зелёный подарок рядом с мусоркой ──
    for lvl in GIFT_LEVELS:
        lv = bf.files[lvl]
        gift = find_go(lv, "UraniumGift")
        if gift is None:
            continue
        tr = get_transform(lv, gift)
        tt = lv.objects[tr].read_typetree()
        pos = tt["m_LocalPosition"]
        # сдвигаем по X на +1.5, y — на пол (как у мусорки, -3.6 + 0.3)
        newx = round(pos["x"] + 1.5, 2)
        if abs(pos["x"] - newx) > 0.01:
            tt["m_LocalPosition"] = {"x": newx, "y": pos["y"], "z": pos["z"]}
            lv.objects[tr].save_typetree(tt)
            print(f"[{lvl}] зелёный подарок -> x={newx} (рядом с мусоркой)")
        else:
            print(f"[{lvl}] зелёный подарок уже сдвинут")

    # ── 2. снежинки: быстрее + к потолку ──
    for lvl in SNOW_LEVELS:
        lv = bf.files[lvl]
        sp = find_go(lv, "SnowParticle")
        if sp is None:
            continue
        tr = get_transform(lv, sp)
        tt = lv.objects[tr].read_typetree()
        # поднять к потолку
        if abs(tt["m_LocalPosition"]["y"] - 8.0) > 0.01:
            tt["m_LocalPosition"]["y"] = 8.0
            lv.objects[tr].save_typetree(tt)
            print(f"[{lvl}] SnowParticle -> y=8.0")

        # ParticleSystem
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
        im = ps["InitialModule"]
        changed = False
        if im["startSpeed"].get("scalar") != 0.5:
            im["startSpeed"]["scalar"] = 0.5
            im["startSpeed"]["minScalar"] = 0.5
            changed = True
        if im["gravityModifier"].get("scalar") != 0.15:
            im["gravityModifier"]["scalar"] = 0.15
            im["gravityModifier"]["minScalar"] = 0.15
            changed = True
        sm = ps["ShapeModule"]
        if sm.get("m_Scale", {}).get("y") != 4.0:
            sm["m_Scale"]["y"] = 4.0
            changed = True
        if changed:
            ps["InitialModule"] = im
            ps["ShapeModule"] = sm
            lv.objects[ps_pid].save_typetree(ps)
            print(f"[{lvl}] SnowParticle: speed=0.5 gravity=0.15 shapeY=4")

    # ── 3. снег в меню на стол ──
    l0 = bf.files["level0"]
    snow = find_go(l0, "Snow")
    table = find_go(l0, "Table")
    if snow is not None and table is not None:
        tr_snow = get_transform(l0, snow)
        tr_tbl = get_transform(l0, table)
        st = l0.objects[tr_snow].read_typetree()
        tp = l0.objects[tr_tbl].read_typetree()["m_LocalPosition"]
        target = {"x": tp["x"], "y": tp["y"] + 0.8, "z": tp["z"]}
        cur = st["m_LocalPosition"]
        if (cur["x"], cur["y"], cur["z"]) != (target["x"], target["y"], target["z"]):
            st["m_LocalPosition"] = target
            l0.objects[tr_snow].save_typetree(st)
            print(f"[level0] Snow -> на стол {target}")

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
