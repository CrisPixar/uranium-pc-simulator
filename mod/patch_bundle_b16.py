#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b16: НГ-подарки в комнатах.

Было: по одному подарку «UraniumGift» в level1/3/4/5, все висят в воздухе
рядом с кондиционером (y=4.6). Пользователь просил:
  • зелёный подарок — на полу рядом с мусоркой (RecycleBin);
  • красный подарок — на кондиционере (AirConditioner).

Делаем:
  1. Существующий (зелёный) подарок переносим на пол рядом с мусоркой
     (y = y_мусорки + 0.3).
  2. Клонируем подарок и ставим клон на кондиционер (текущая позиция y=4.6).
  3. Цвет клона пока оставляем зелёным (красный — отдельной правкой текстуры).

Запуск: python3 mod/patch_bundle_b16.py [дерево]   (по умолчанию текущее)
Идемпотентен: повторный запуск пропускает уже сделанное.
"""
import os
import sys

import UnityPy
from UnityPy.files.ObjectReader import ObjectReader

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

# комнаты: имя -> (go подарка, go мусорки, go кондиционера)
ROOMS = {
    "level1": ("UraniumGift", "RecycleBin", "AirConditioner"),
    "level3": ("UraniumGift", "RecycleBin", "AirConditioner"),
    "level4": ("UraniumGift", "RecycleBin", "AirConditioner"),
    "level5": ("UraniumGift", "RecycleBin", "AirConditioner"),
}
GIFT2_NAME = "UraniumGift2"


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
    go = sf.objects[go_pid].read_typetree()
    for c in go["m_Component"]:
        cp = c["component"]["m_PathID"]
        if cp in sf.objects and sf.objects[cp].type.name == "Transform":
            return cp
    return None


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


def next_pid(sf):
    return max(sf.objects) + 1


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]

    for lvl, (gift_name, bin_name, ac_name) in ROOMS.items():
        lv = bf.files[lvl]
        gift_go = find_go(lv, gift_name)
        if gift_go is None:
            print(f"[{lvl}] подарок не найден — пропуск")
            continue
        bin_go = find_go(lv, bin_name)
        ac_go = find_go(lv, ac_name)

        # позиции
        bin_tr = get_transform(lv, bin_go) if bin_go else None
        ac_tr = get_transform(lv, ac_go) if ac_go else None
        bin_pos = lv.objects[bin_tr].read_typetree()["m_LocalPosition"] if bin_tr else None
        ac_pos = lv.objects[ac_tr].read_typetree()["m_LocalPosition"] if ac_tr else None

        gift_tr = get_transform(lv, gift_go)
        gtr = lv.objects[gift_tr].read_typetree()
        cur_pos = gtr["m_LocalPosition"]

        # ── 1. зелёный на пол рядом с мусоркой ──
        if bin_pos is not None:
            new_pos = {"x": bin_pos["x"], "y": bin_pos["y"] + 0.3, "z": bin_pos["z"]}
            if (gtr["m_LocalPosition"]["x"], gtr["m_LocalPosition"]["y"],
                    gtr["m_LocalPosition"]["z"]) != (new_pos["x"], new_pos["y"], new_pos["z"]):
                gtr["m_LocalPosition"] = new_pos
                lv.objects[gift_tr].save_typetree(gtr)
                print(f"[{lvl}] {gift_name} -> пол у мусорки {new_pos}")
            else:
                print(f"[{lvl}] {gift_name} уже на полу")

        # ── 2. клон на кондиционере ──
        if find_go(lv, GIFT2_NAME) is None:
            # собрать компоненты исходного подарка
            ggo = lv.objects[gift_go].read_typetree()
            comps = []
            for c in ggo["m_Component"]:
                cp = c["component"]["m_PathID"]
                comps.append((cp, lv.objects[cp].type.name if cp in lv.objects else None))

            # новые pathID
            pid_go = next_pid(lv)
            pid_tr = pid_go + 1
            pid_mf = pid_go + 2
            pid_mr = pid_go + 3

            # клонируем Transform (меняем GO + позицию + родителя = Room)
            # позиция клона — НА кондиционере: как у исходного подарка (y=4.6)
            # (исходный стоял над кондиционером; центр кондиционера y=4.0 — это
            #  «внутри» него, поэтому берём прежнюю высоту подарка)
            src_tr_pid = next(p for p, t in comps if t == "Transform")
            tr = lv.objects[src_tr_pid].read_typetree()
            tr["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid_go}
            if ac_pos is not None:
                on_ac = {"x": ac_pos["x"], "y": ac_pos["y"] + 0.6,
                         "z": ac_pos["z"]}
            else:
                on_ac = cur_pos
            tr["m_LocalPosition"] = on_ac
            tr["m_Father"] = gtr["m_Father"]
            tr["m_Children"] = []
            new_object(lv, src_tr_pid, pid_tr, tr)

            # клонируем MeshFilter (меняем GO)
            src_mf_pid = next(p for p, t in comps if t == "MeshFilter")
            mf = lv.objects[src_mf_pid].read_typetree()
            mf["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid_go}
            new_object(lv, src_mf_pid, pid_mf, mf)

            # клонируем MeshRenderer (меняем GO)
            src_mr_pid = next(p for p, t in comps if t == "MeshRenderer")
            mr = lv.objects[src_mr_pid].read_typetree()
            mr["m_GameObject"] = {"m_FileID": 0, "m_PathID": pid_go}
            new_object(lv, src_mr_pid, pid_mr, mr)

            # клонируем GameObject
            ggo2 = lv.objects[gift_go].read_typetree()
            ggo2["m_Name"] = GIFT2_NAME
            ggo2["m_Component"] = [
                {"component": {"m_FileID": 0, "m_PathID": pid_tr}},
                {"component": {"m_FileID": 0, "m_PathID": pid_mf}},
                {"component": {"m_FileID": 0, "m_PathID": pid_mr}},
            ]
            new_object(lv, gift_go, pid_go, ggo2)

            # добавить клон в children родителя (Room)
            parent_tr_pid = gtr["m_Father"]["m_PathID"]
            parent = lv.objects[parent_tr_pid].read_typetree()
            parent["m_Children"].append({"m_FileID": 0, "m_PathID": pid_tr})
            lv.objects[parent_tr_pid].save_typetree(parent)

            print(f"[{lvl}] клон {GIFT2_NAME} (GO {pid_go}) на кондиционере {tr['m_LocalPosition']}")
        else:
            print(f"[{lvl}] клон {GIFT2_NAME} уже есть")

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
