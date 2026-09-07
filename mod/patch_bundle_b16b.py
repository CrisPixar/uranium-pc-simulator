#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b16: снег/музыка + красный подарок.

1. МУЗЫКА (снег): GameObject «Snow» (level0, pid 141) неактивен
   (m_IsActive=False), поэтому `GameObject.Find("Snow")` в IL2CPP его не
   находит — музыка и снег не включаются. Делаем его активным.

2. КРАСНЫЙ ПОДАРОК: клон «UraniumGift2» (на кондиционере) пока зелёный —
   использует тот же материал «Gift». Создаём красную текстуру «GiftRed»
   (перекраска зелёной 175) и красный материал «GiftRed», привязываем к
   клону во всех комнатах.

Запуск: python3 mod/patch_bundle_b16b.py [дерево]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import sys

import UnityPy
from UnityPy.files.ObjectReader import ObjectReader

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

GIFT2_NAME = "UraniumGift2"
RED_TEX_NAME = "GiftRed"
RED_MAT_NAME = "GiftRed"


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


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]
    res = bf.files["resources.assets"]

    # ── 1. Snow активен (музыка) ──
    l0 = bf.files["level0"]
    snow = l0.objects[141].read_typetree()
    if snow.get("m_IsActive") is not True:
        snow["m_IsActive"] = True
        l0.objects[141].save_typetree(snow)
        print("[level0] Snow -> активен (музыка)")
    else:
        print("[level0] Snow уже активен")

    # ── 2. красная текстура + материал ──
    next_pid = max(res.objects) + 1
    red_tex_pid = next_pid
    red_mat_pid = next_pid + 1

    existing = [pid for pid, o in res.objects.items()
                if o.type.name == "Texture2D"
                and o.read_typetree().get("m_Name") == RED_TEX_NAME]
    if not existing:
        from PIL import Image
        src_tex_obj = res.objects[175].read()  # Texture2D
        img = src_tex_obj.image.convert("RGBA")
        # перекраска: зелёный -> красный (обмен каналов R и G)
        r, g, b, a = img.split()
        red_img = Image.merge("RGBA", (g, r, b, a))

        tex_tree = res.objects[175].read_typetree()
        tex_tree["m_Name"] = RED_TEX_NAME
        tex_tree["m_TextureFormat"] = 4  # RGBA32
        tex_tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
        tex_tree["image data"] = b""
        new_object(res, 175, red_tex_pid, tree=tex_tree)
        tex2d = res.objects[red_tex_pid].read()
        tex2d.set_image(red_img, target_format=4)
        tex2d.save()
        print(f"[resources] текстура {RED_TEX_NAME} (pid {red_tex_pid})")
    else:
        red_tex_pid = existing[0]
        print(f"[resources] текстура {RED_TEX_NAME} уже есть (pid {red_tex_pid})")

    existing_mat = [pid for pid, o in res.objects.items()
                    if o.type.name == "Material"
                    and o.read_typetree().get("m_Name") == RED_MAT_NAME]
    if not existing_mat:
        mat_tree = res.objects[36].read_typetree()
        mat_tree["m_Name"] = RED_MAT_NAME
        for i, (k, v) in enumerate(mat_tree["m_SavedProperties"]["m_TexEnvs"]):
            if k == "_MainTex":
                v["m_Texture"] = {"m_FileID": 0, "m_PathID": red_tex_pid}
                mat_tree["m_SavedProperties"]["m_TexEnvs"][i] = (k, v)
        new_object(res, 36, red_mat_pid, tree=mat_tree)
        print(f"[resources] материал {RED_MAT_NAME} (pid {red_mat_pid})")
    else:
        red_mat_pid = existing_mat[0]
        print(f"[resources] материал {RED_MAT_NAME} уже есть (pid {red_mat_pid})")

    # ── 3. привязка клона к красному материалу ──
    for lvl in ["level1", "level3", "level4", "level5"]:
        lv = bf.files[lvl]
        # fileID ресурсного файла (1-based в externals)
        res_idx = None
        for i, e in enumerate(lv.externals):
            if e.name == "resources.assets":
                res_idx = i + 1  # 1-based
                break
        if res_idx is None:
            print(f"[{lvl}] resources.assets не найден в externals — пропуск")
            continue
        go = find_go(lv, GIFT2_NAME)
        if go is None:
            print(f"[{lvl}] клон не найден — пропуск")
            continue
        ggo = lv.objects[go].read_typetree()
        mr_pid = None
        for c in ggo["m_Component"]:
            cp = c["component"]["m_PathID"]
            if cp in lv.objects and lv.objects[cp].type.name == "MeshRenderer":
                mr_pid = cp
                break
        if mr_pid is None:
            print(f"[{lvl}] MeshRenderer клона не найден — пропуск")
            continue
        mr = lv.objects[mr_pid].read_typetree()
        want = {"m_FileID": res_idx, "m_PathID": red_mat_pid}
        cur = mr.get("m_Materials", [{}])[0] if mr.get("m_Materials") else {}
        if cur.get("m_PathID") != red_mat_pid:
            mr["m_Materials"] = [want]
            lv.objects[mr_pid].save_typetree(mr)
            print(f"[{lvl}] клон {GIFT2_NAME} -> красный материал "
                  f"(file{res_idx}:{red_mat_pid})")
        else:
            print(f"[{lvl}] клон уже красный")

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
