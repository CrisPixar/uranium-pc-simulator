#!/usr/bin/env python3
"""Uranium PC Simulator — нативные патчи b16 (поверх b15).

Подарки должны стоять на месте, а не «мигать». Причина мигания: функция
обновления подарков включает/выключает GameObject «UraniumGift» по
таймеру  `fmod(time, 8.0) < 6.5`  (виден 6.5 с, скрыт 1.5 с, по циклу),
ещё и при включённом новогоднем режиме («UraniumNY»).

  arm64 0x85e058: cset w20, lt  ->  mov w20, #1   (всегда включён)
  arm32 0x1c713a0: movlt r5, #1 ->  mov r5, #1   (всегда включён)

После патча подарок виден постоянно (пока включён новогодний режим),
без мигания.

Запуск: python3 mod/patch_b16.py [дерево_apktool]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import sys


def main():
    BASE = sys.argv[1] if len(sys.argv) > 1 else "."
    fixes = [
        ("lib/arm64-v8a/libil2cpp.so", 0x85e058, bytes.fromhex("f4a79f1a"),
         bytes.fromhex("34008052"), "arm64: подарок без мигания"),
        ("lib/armeabi-v7a/libil2cpp.so", 0x1c713a0, bytes.fromhex("0150a0b3"),
         bytes.fromhex("0150a0e3"), "arm32: подарок без мигания"),
    ]
    for rel, va, old, new, what in fixes:
        path = os.path.join(BASE, rel)
        with open(path, "rb") as f:
            d = bytearray(f.read())
        cur = d[va:va + 4]
        if cur == new:
            print(f"  [skip] {what} @0x{va:x}")
            continue
        if cur != old:
            raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex()}, "
                               f"найдено {cur.hex()}")
        d[va:va + 4] = new
        with open(path, "wb") as f:
            f.write(bytes(d))
        print(f"  [ ok ] {what} @0x{va:x} ({cur.hex()} -> {new.hex()})")
    print("Готово.")


if __name__ == "__main__":
    main()
