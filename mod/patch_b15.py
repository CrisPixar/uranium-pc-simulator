#!/usr/bin/env python3
"""Uranium PC Simulator — нативные патчи b15 (поверх b14).

Пасхалка «Bitcoin Searcher» срабатывает после 5 кликов по заголовку меню
(было 10). Клики по надписи «Uranium PC Simulator» в главном меню — после
5-го нажатия даётся случайно 100–10000 BTC, максимум 2 раза.

  arm64 0x85de88: cmp w21, #0xa  ->  cmp w21, #0x5
  arm32 0x1c80ad4: cmp r5, #0xa  ->  cmp r5, #0x5

Запуск: python3 mod/patch_b15.py [дерево_apktool]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import sys


def main():
    BASE = sys.argv[1] if len(sys.argv) > 1 else "."
    fixes = [
        ("lib/arm64-v8a/libil2cpp.so", 0x85de88, bytes.fromhex("bf2a0071"),
         bytes.fromhex("bf160071"), "arm64 egg: 10 кликов -> 5"),
        ("lib/armeabi-v7a/libil2cpp.so", 0x1c80ad4, bytes.fromhex("0a0055e3"),
         bytes.fromhex("050055e3"), "arm32 egg: 10 кликов -> 5"),
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
