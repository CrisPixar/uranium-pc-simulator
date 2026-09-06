#!/usr/bin/env python3
"""Патчи libil2cpp.so для мода Uranium PC Simulator (arm64-v8a + armeabi-v7a).

Патчи (одинаковое поведение на обеих архитектурах):
  1. Песочница без 5 BTC   — SceneSettings.SetSandbox: цена 5.0 -> 0.0 и списание -5.0 -> 0.0
  2. Краски x3             — Printer..ctor: totalInk/remainingInk 1.0 -> 3.0
  3. Без искажения цветов  — Printer.PrintAvailableArea: usable = needed (клампы убраны)
  4. Кондиционер охлаждает в 2 раза быстрее — CPU.FixedUpdate: -10.0 -> -5.0

Каждый патч проверяет оригинальные байты перед записью (защита от двойного применения).
"""
import sys, os, keystone
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KS_ARCH_ARM, KS_MODE_ARM

BASE = "/home/user/game_src/Blue_PC_Simulator_v1.9.1.11(1)_base_src"
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

ks64 = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
ks32 = Ks(KS_ARCH_ARM, KS_MODE_ARM)

def asm64(code):
    enc, _ = ks64.asm(code)
    return bytes(enc)

def asm32(code):
    enc, _ = ks32.asm(code)
    return bytes(enc)



def patch(data, va, old, new, what):
    """Применить патч с проверкой оригинала. VA == file offset (проверено по ELF PHDR)."""
    cur = data[va:va+len(old)]
    if cur == new[:len(new)] and len(old) == len(new):
        print(f"  [skip] {what} @0x{va:x}: уже применён")
        return
    if cur != old:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex(' ')}, найдено {cur.hex(' ')}")
    data[va:va+len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x}: {old.hex(' ')} -> {new.hex(' ')}")

# ============================================================================
# ARM64 (arm64-v8a)
# ============================================================================
def patch_arm64(data):
    print("== arm64-v8a ==")

    # --- 1. Песочница бесплатна: SceneSettings.SetSandbox 0x8035B0 ---
    # 0x803684: fmov s1, #5.0   (порог BTC) -> fmov s1, #0.0
    patch(data, 0x803684, asm64("fmov s1, #5.0"), asm64("fmov s1, #0.0"), "sandbox: цена 5->0")
    # 0x803740: fmov s1, #-5.0 (списание)  -> fmov s1, #0.0  (fadd добавит 0)
    patch(data, 0x803740, asm64("fmov s1, #-5.0"), asm64("fmov s1, #0.0"), "sandbox: списание -5->0")

    # --- 2. Краски x3: Printer..ctor 0x835B10 ---
    # 0x835b1c: fmov s8, #1.0 -> #3.0 (totalInk и remainingInk строятся из s8)
    patch(data, 0x835b1c, asm64("fmov s8, #1.0"), asm64("fmov s8, #3.0"), "ink x3 (ctor)")

    # --- 3. Без искажения цветов: Printer.PrintAvailableArea 0x835194 ---
    # usable = min(needed, remaining) если remaining>0, иначе 0 -> usable = needed.
    # Каждая пара fcsel (кламп + защита от <=0) заменяется парой fmov.
    fcsel_fixes = [
        (0x83533c, "fcsel s4, s2, s5, mi", "fmov s4, s2"),  # c
        (0x835344, "fcsel s5, s4, s13, gt", "fmov s5, s4"),
        (0x83534c, "fcsel s4, s1, s7, mi", "fmov s4, s1"),  # m
        (0x835354, "fcsel s2, s4, s13, gt", "fmov s2, s4"),
        (0x83535c, "fcsel s4, s0, s16, mi", "fmov s4, s0"),  # y
        (0x835364, "fcsel s1, s4, s13, gt", "fmov s1, s4"),
        (0x83536c, "fcsel s4, s3, s6, mi",  "fmov s4, s3"),  # k
        (0x835378, "fcsel s3, s4, s13, gt", "fmov s3, s4"),
    ]
    for va, old, new in fcsel_fixes:
        patch(data, va, asm64(old), asm64(new), f"print-colors {old}")

    # --- 4. Кондиционер охлаждает x2: CPU.FixedUpdate 0x82D518 ---
    # 0x82d634: fmov s2, #-10.0 (делитель скорости дрейфа) -> #-5.0
    patch(data, 0x82d634, asm64("fmov s2, #-10.0"), asm64("fmov s2, #-5.0"), "AC cooling x2")

# ============================================================================
# ARM32 (armeabi-v7a, режим ARM, не Thumb)
# ============================================================================
def patch_arm32(data):
    print("== armeabi-v7a ==")

    # --- 1. Песочница: SceneSettings.SetSandbox 0x508C00 ---
    # VMOV-imm не может закодировать +0.0, поэтому:
    # 0x508d10: vcmpe.f32 s2, s0 (bitcoin vs 5.0) -> vcmpe.f32 s2, s2 (всегда PL)
    patch(data, 0x508d10, asm32("vcmpe.f32 s2, s0"), asm32("vcmpe.f32 s2, s2"), "sandbox: цена 5->0")
    # 0x508ddc: vadd.f32 s0, s2, s0 (bitcoin + (-5)) -> vmov.f32 s0, s2 (bitcoin не меняется)
    patch(data, 0x508ddc, asm32("vadd.f32 s0, s2, s0"), asm32("vmov.f32 s0, s2"), "sandbox: списание -5->0")

    # --- 2. Краски x3: Printer..ctor 0x54BD00 ---
    # ARM immediate не может закодировать 0x40400000 (3.0f), поэтому:
    # Блок 1 (0x54bd18..0x54bd2c, 6 инструкций): собрать 3.0f в r1 (movw/movt),
    # продублировать в r2/r3/r7, r0=r5 (sret-буфер). r6 больше не нужен как 0
    # ([sp+4] — выравнивающий паддинг, значение не читается).
    block1_old = b"".join(asm32(s) for s in [
        "mov r6, #0",
        "mov r7, #0x3f800000",
        "mov r0, r5",
        "mov r1, #0x3f800000",
        "mov r2, #0x3f800000",
        "mov r3, #0x3f800000",
    ])
    block1_new = b"".join(asm32(s) for s in [
        "movw r1, #0x4000",
        "movt r1, #0x4040",   # r1 = 0x40400000 = 3.0f
        "mov r2, r1",
        "mov r3, r1",
        "mov r7, r1",         # r7 = 3.0f -> str [sp] (k) в обоих вызовах ctor
        "mov r0, r5",         # sret-буфер
    ])
    patch(data, 0x54bd18, block1_old, block1_new, "ink x3 (ctor блок 1)")
    # Блок 2: три mov rX, #1.0 -> mov rX, r7 (r7 уже 3.0)
    for va, r in [(0x54bd4c, "r1"), (0x54bd54, "r2"), (0x54bd5c, "r3")]:
        patch(data, va, asm32(f"mov {r}, #0x3f800000"), asm32(f"mov {r}, r7"), f"ink x3 (ctor {r})")

    # --- 3. Без искажения цветов: Printer.PrintAvailableArea 0x54AF90 ---
    # NEON-версия клампа:
    #   q7 = needed (FromRgb), q8 = remaining
    #   0x54b1f0: vbsl q9, q7, q8       (min)      -> vmov q9, q7  (needed)
    #   0x54b1f4: vcgt.f32 q8, q8, #0   (rem > 0)  -> vceq.f32 q8, q8, q8 (всегда истина)
    #   0x54b1f8: vand q8, q9, q8       остаётся   -> usable = needed
    patch(data, 0x54b1f0, asm32("vbsl q9, q7, q8"), asm32("vmov q9, q7"), "print-colors (vbsl->needed)")
    patch(data, 0x54b1f4, asm32("vcgt.f32 q8, q8, #0"), asm32("vceq.f32 q8, q8, q8"), "print-colors (mask->true)")

    # --- 4. Кондиционер охлаждает x2: CPU.FixedUpdate 0x540D5C ---
    # 0x540e94: vmov.f32 s2, #-10.0 -> #-5.0
    patch(data, 0x540e94, asm32("vmov.f32 s2, #-10.0"), asm32("vmov.f32 s2, #-5.0"), "AC cooling x2")

# ============================================================================
def main():
    for path, fn in [(SO64, patch_arm64), (SO32, patch_arm32)]:
        with open(path, "rb") as f:
            data = bytearray(f.read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
        print(f"  сохранено: {path} ({len(data)} байт)")
    print("Готово: все .so патчи применены.")

if __name__ == "__main__":
    main()
