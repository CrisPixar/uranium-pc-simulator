#!/usr/bin/env python3
"""Uranium PC Simulator — нативные патчи b14 (поверх b13).

Исправляет: «Биткоинов даже если хватает — пишет, что не хватает».

Причина (аналог бага кейва money64, который чинили в b10, но там был фриз):
в кейве BTC-разблокировки (ShopUI.ButtonDown -> 0x85d9b8 / 0x1c6a080) две
ветки «не песочница» (cbz/beq) прыгали НЕ на оригинальное сравнение
цены с балансом («Lorig»), а сразу на ветку «не хватает»:

  arm64 0x85d9c0: cbz x0, #0x85d9dc   -> должно быть #0x85d9e0 (Lorig)
  arm64 0x85d9c8: cbz w8, #0x85d9dc   -> должно быть #0x85d9e0 (Lorig)
  arm32 0x1c6a090: beq #0x1c6a0b8     -> должно быть #0x1c6a0bc (Lorig)
  arm32 0x1c6a09c: beq #0x1c6a0b8     -> должно быть #0x1c6a0bc (Lorig)

0x85d9dc / 0x1c6a0b8 — это `b #0x829674` / `b #0x53badc` («не хватает»).
Поэтому вне песочницы ЛЮБАЯ покупка за BTC (даже при достаточном балансе)
всегда выводила «не хватает»: оригинальное сравнение «цена <= баланс»
вообще не исполнялось (оно стало недостижимым кодом).

Фикс: обе ветки «не песочница» (и «Main == null») теперь идут на Lorig —
оригинальное сравнение, как и было задумано («вне песочницы всё как в
оригинале»).

Запуск: python3 mod/patch_b14.py [дерево_apktool]   (по умолчанию текущее)
Идемпотентен: повторный запуск ничего не меняет.
"""
import os
import sys

from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KS_ARCH_ARM, KS_MODE_ARM

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

ks64 = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
ks32 = Ks(KS_ARCH_ARM, KS_MODE_ARM)


def asm64(code, addr):
    enc, _ = ks64.asm(code, addr)
    return bytes(enc)


def asm32(code, addr):
    enc, _ = ks32.asm(code, addr)
    return bytes(enc)


def patch(data, va, old, new, what):
    cur = data[va:va + len(old)]
    if cur == new:
        print(f"  [skip] {what} @0x{va:x}")
        return
    if cur != old:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex(' ')}, "
                           f"найдено {cur.hex(' ')}")
    assert len(new) == len(old)
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x} ({cur.hex(' ')} -> {new.hex(' ')})")


def main():
    # arm64: Lorig = 0x85d9e0
    print("== arm64-v8a ==")
    with open(SO64, "rb") as f:
        d = bytearray(f.read())
    patch(d, 0x85d9c0, asm64("cbz x0, #0x85d9dc", 0x85d9c0),
          asm64("cbz x0, #0x85d9e0", 0x85d9c0), "btc64: Main==null -> Lorig")
    patch(d, 0x85d9c8, asm64("cbz w8, #0x85d9dc", 0x85d9c8),
          asm64("cbz w8, #0x85d9e0", 0x85d9c8), "btc64: не-sandbox -> Lorig")
    with open(SO64, "wb") as f:
        f.write(bytes(d))

    # arm32: Lorig = 0x1c6a0bc
    print("== armeabi-v7a ==")
    with open(SO32, "rb") as f:
        d = bytearray(f.read())
    patch(d, 0x1c6a090, asm32("beq #0x1c6a0b8", 0x1c6a090),
          asm32("beq #0x1c6a0bc", 0x1c6a090), "btc32: Main==null -> Lorig")
    patch(d, 0x1c6a09c, asm32("beq #0x1c6a0b8", 0x1c6a09c),
          asm32("beq #0x1c6a0bc", 0x1c6a09c), "btc32: не-sandbox -> Lorig")
    with open(SO32, "wb") as f:
        f.write(bytes(d))

    print("Готово.")


if __name__ == "__main__":
    main()
