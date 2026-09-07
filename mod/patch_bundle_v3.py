#!/usr/bin/env python3
"""Правки data.unity3d v3 (поверх v2). Идемпотентен.

  1. bitcoin = 0.0 у новых ShopItem (принтеры 512/1024, горизонтальный баннер):
     IsUnlocked() возвращает true при bitcoin<=0 -> карточки в маркете
     инициализируются нормально (фикс "мусорной" карточки Title) и покупаются.
  2. Текстура 164 'rgb' (32x32, near-текстура материала Merge_DistanceMask)
     -> белая RGBA32: убирает RGB-субпиксели на голограммах вблизи и
     остаточную сетку между пикселями.
  3. PrintExpert MB 11239: поле alertText (0x50) переназначено с Text 11958
     на TextureLoader 13747 префаба BannerStand_H. Нативный код v3 использует
     его как префаб горизонтального баннера для картинок 70x32 (alertText
     больше нигде в коде сайта не читается).

Запуск:  python3 patch_bundle_v3.py [путь_к_дереву_apktool]
"""
import sys, os

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")

sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
from modtools import load_env, Ctx

env = load_env()
ctx = Ctx(env)
R = "resources.assets"

def write_existing(fname, pid, tt):
    ctx.write_tt(fname, pid, tt)

# ============================================================================
print("[1] bitcoin = 0.0 у новых ShopItem")
ITEMS = {
    13706: "Apson A3 512x512",
    13739: "Apson A3 1024x1024",
    13754: "{Horizontal Banner}",
}
for pid, want_name in ITEMS.items():
    si = ctx.read_tt(R, pid)
    assert si["m_Name"] == want_name, f"{pid}: {si['m_Name']!r} != {want_name!r}"
    if si["bitcoin"] == 0.0:
        print(f"    [skip] {pid} {want_name}: уже 0.0")
        continue
    assert si["bitcoin"] == 5.0, f"{pid}: bitcoin={si['bitcoin']}"
    si["bitcoin"] = 0.0
    write_existing(R, pid, si)
    print(f"    [ ok ] {pid} {want_name}: bitcoin 5.0 -> 0.0")
print("    OK")

# ============================================================================
print("[2] Текстура 164 'rgb' -> белая (без RGB-субпикселей и сетки вблизи)")
t = ctx.read_tt(R, 164)
assert t["m_Name"] == "rgb" and t["m_Width"] == 32 and t["m_Height"] == 32
assert t["m_TextureFormat"] in (4, 47), t["m_TextureFormat"]  # 47 = ETC2_RGBA8 (оригинал)
px = 32*32 + 16*16 + 8*8 + 4*4 + 2*2 + 1*1                    # 6 mips, как в оригинале
want = px * 4
if t["m_TextureFormat"] == 4 and t["image data"] == b"\xff" * want:
    print("    [skip] уже белая")
else:
    # конвертация в белую RGBA32 inline (как Grid/117 в v2), стрим отключаем
    t["m_TextureFormat"] = 4
    t["m_CompleteImageSize"] = want
    t["image data"] = b"\xff" * want
    t["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    write_existing(R, 164, t)
    print(f"    [ ok ] ETC2(1392, resS) -> RGBA32 белая ({want} байт, inline)")
print("    OK")

# ============================================================================
print("[3] PrintExpert: alertText -> префаб горизонтального баннера")
pe = ctx.read_tt(R, 11239)
assert pe["m_Name"] == "" or True  # MB без имени
if pe["alertText"] == {"m_FileID": 0, "m_PathID": 13747}:
    print("    [skip] уже переназначен")
else:
    assert pe["alertText"] == {"m_FileID": 0, "m_PathID": 11958}, pe["alertText"]
    assert pe["bannerPrefab"] == {"m_FileID": 0, "m_PathID": 12916}
    # убедимся, что 13747 действительно TextureLoader на BannerStand_H (13740)
    tl = ctx.read_tt(R, 13747)
    go = ctx.read_tt(R, tl["m_GameObject"]["m_PathID"])
    assert go["m_Name"] == "BannerStand_H", go["m_Name"]
    pe["alertText"] = {"m_FileID": 0, "m_PathID": 13747}
    write_existing(R, 11239, pe)
    print("    [ ok ] alertText: 11958 (Text) -> 13747 (TextureLoader BannerStand_H)")
print("    OK")

# ============================================================================
print("[4] Заголовок level0: PC тоже красный (консистентно с литералом)")
t0 = ctx.read_tt("level0", 1102)
if "Uranium" in t0["m_Text"] and "red" in t0["m_Text"]:
    print("    [skip] уже красный")
else:
    assert "Uranium" in t0["m_Text"], t0["m_Text"]
    t0["m_Text"] = "<color=cyan>Uranium</color> <color=red>PC</color> Simulator"
    write_existing("level0", 1102, t0)
    print("    [ ok ]", t0["m_Text"])

# ============================================================================
print("[5] Сохранение data.unity3d")
out = env.file.save(packer="original")
with open(BUNDLE, "wb") as f:
    f.write(out)
print(f"    записано {len(out):,} байт")
print("ПАТЧИ v3 ПРИМЕНЕНЫ. Запусти verify_v3.py.")
