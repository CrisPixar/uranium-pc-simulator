#!/usr/bin/env python3
"""Uranium PC Simulator — нативные патчи b17 (поверх b16).

1. КНОПКА CH: зелёный/красный.
   В каждом кадре (кейв es64) красим текст «CH» (UnityEngine.UI.Text):
   НГ включён (UraniumNY==1) -> зелёный (0,1,0,1),
   НГ выключен            -> красный (1,0,0,1).
   Text-компонент кешируется в RW-слоте .so (первый раз ищется через
   GameObject.Find("CH_Btn") + GetComponent(typeof(Text))).

2. ТЕКСТ «+N BTC» (пасхалка после 5 кликов).
   В кейве пасхалки после начисления N BTC дополнительно пишем N в RW-слот и
   ставим флаг «показать». Наш кейв в том же кадре строит строку «+N BTC»
   (Int32.ToString + String.Concat), пишет её в Text «BtcPop» (level0) и
   показывает 10 секунд (600 кадров), затем прячет.

Запуск: python3 mod/patch_b17.py [дерево]   (по умолчанию текущее)
Идемпотентен.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asmlib import Asm64, Asm32, a64, a32   # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

# ─────────── arm64 ───────────
K64 = dict(
    NEWSTR=0x6FBCA8, FIND=0x17D00C0, SETACTIVE=0x17CFD04, GETINT=0x17C8614,
    SET_COLOR=0x1849A70, SET_TEXT=0x198CB8C, GETCOMP=0x17CD76C,
    CFN=0x6FB274, DG=0x6FB870, DAO=0x6FB874, AGI=0x6FB23C, CGT=0x6FB2DC,
    TGO=0x6FBD1C, CONCAT3=0xFD5084, I32TOS=0x113D2FC,
)
# строки/константы в кейве (адреса)
S64 = dict(UI=0x85E4E0, TEXT=0x85E4F0, CHBTN=0x85E4F8, NY=0x85E500,
           PLUS=0x85E50C, BTC=0x85E510, POP=0x85E518,
           GREEN=0x85E520, RED=0x85E530)
CACHE64 = 0x2263560          # [0]=Text*, [8]=pending, [0xc]=amount, [0x10]=countdown (в .data, RW)
CH64_EPI_BR = 0x85E204       # `b 0x85df88` в конце кейва CH64
ES64_EPI = 0x85DF88
CAVE64 = 0x85E320            # наш основной кейв
HELPER64 = 0x85E4C0          # помощник «сохранить N» (сразу после кейва, до строк)
EGG64_STORE = 0x85DED0       # `mov x0, xzr` -> `bl HELPER64`


def patch64(d):
    print("== arm64-v8a ==")
    K, S = K64, S64

    # ---- основной кейв (каждый кадр) ----
    c = Asm64(CAVE64)
    c(
        "stp x29, x30, [sp, #-0x10]!",
        "stp x19, x20, [sp, #-0x10]!",
        "stp x21, x22, [sp, #-0x10]!",
        "stp x23, x24, [sp, #-0x10]!",
        # кеш Text
        f"LIT x20, 0x{CACHE64:x}",
        "ldr x19, [x20]",
        "cbnz x19, #Lhave",
        # resolve Type(Text)
        f"bl #0x{K['DG']:x}",
        "mov x21, x0",
        f"LIT x0, 0x{S['UI']:x}",
        f"bl #0x{K['DAO']:x}",
        f"bl #0x{K['AGI']:x}",
        f"LIT x1, 0x{S['UI']:x}",
        f"LIT x2, 0x{S['TEXT']:x}",
        f"bl #0x{K['CFN']:x}",
        f"bl #0x{K['CGT']:x}",
        f"bl #0x{K['TGO']:x}",
        "mov x22, x0",
        f"LIT x0, 0x{S['CHBTN']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cbz x0, #Lnoch",
        "mov x1, x22",
        f"bl #0x{K['GETCOMP']:x}",
        "cbz x0, #Lnoch",
        f"LIT x20, 0x{CACHE64:x}",
        "str x0, [x20]",
        "mov x19, x0",
        "Lhave:",
        # UraniumNY -> цвет
        f"LIT x0, 0x{S['NY']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov w1, wzr",
        f"bl #0x{K['GETINT']:x}",
        "cmp w0, #1",
        "cset w1, eq",
        f"LIT x20, 0x{S['GREEN']:x}",
        f"LIT x21, 0x{S['RED']:x}",
        "cmp w1, #1",
        "csel x20, x20, x21, eq",
        "ldr q0, [x20]",
        "mov x0, x19",
        f"bl #0x{K['SET_COLOR']:x}",
        "Lnoch:",
        # BtcPop: pending?
        f"LIT x20, 0x{CACHE64+8:x}",
        "ldr w21, [x20]",
        "cbz w21, #Lcnt",
        "str wzr, [x20]",
        "ldr w22, [x20, #4]",
        "add x0, x20, #4",
        f"bl #0x{K['I32TOS']:x}",
        "mov x21, x0",
        f"LIT x0, 0x{S['PLUS']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x22, x0",
        f"LIT x0, 0x{S['BTC']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x2, x0",
        "mov x0, x22",
        "mov x1, x21",
        f"bl #0x{K['CONCAT3']:x}",
        "mov x21, x0",
        f"LIT x0, 0x{S['POP']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cbz x0, #Lcnt",
        "mov x1, x21",
        f"bl #0x{K['SET_TEXT']:x}",
        f"LIT x20, 0x{CACHE64+0x10:x}",
        "mov w8, #600",
        "str w8, [x20]",
        "b #Ldone",
        "Lcnt:",
        f"LIT x20, 0x{CACHE64+0x10:x}",
        "ldr w21, [x20]",
        "cbz w21, #Ldone",
        "sub w21, w21, #1",
        "str w21, [x20]",
        "cbnz w21, #Ldone",
        f"LIT x0, 0x{S['POP']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cbz x0, #Ldone",
        "mov w1, wzr",
        f"bl #0x{K['SETACTIVE']:x}",
        "Ldone:",
        "ldp x23, x24, [sp], #0x10",
        "ldp x21, x22, [sp], #0x10",
        "ldp x19, x20, [sp], #0x10",
        "ldp x29, x30, [sp], #0x10",
        f"b #0x{ES64_EPI:x}",
    )
    blob = c.assemble()
    if CAVE64 + len(blob) > HELPER64:
        raise RuntimeError(f"кейв b17 не влез: {len(blob)}")
    put(d, CAVE64, blob, "кейв b17: CH-цвет + BtcPop")

    # ---- помощник «сохранить N» ----
    h = Asm64(HELPER64)
    h(
        f"LIT x9, 0x{CACHE64:x}",
        "str w22, [x9, #0xc]",
        "mov w8, #1",
        "str w8, [x9, #8]",
        "mov x0, xzr",
        "ret",
    )
    put(d, HELPER64, h.assemble(), "хелпер: сохранить N")

    # ---- строки и константы ----
    put(d, S64["UI"], b"UnityEngine.UI\x00\x00", "строка UnityEngine.UI")
    put(d, S64["TEXT"], b"Text\x00\x00\x00\x00", "строка Text")
    put(d, S64["CHBTN"], b"CH_Btn\x00", "строка CH_Btn")
    put(d, S64["NY"], b"UraniumNY\x00\x00\x00", "строка UraniumNY")
    put(d, S64["PLUS"], b"+\x00\x00\x00", "строка +")
    put(d, S64["BTC"], b" BTC\x00\x00\x00", "строка BTC")
    put(d, S64["POP"], b"BtcPop\x00\x00", "строка BtcPop")
    put(d, S64["GREEN"], struct.pack("<4f", 0.0, 1.0, 0.0, 1.0), "константа green")
    put(d, S64["RED"], struct.pack("<4f", 1.0, 0.0, 0.0, 1.0), "константа red")

    # ---- хук: конец кейва CH64 -> наш кейв ----
    new_b = a64(f"b #0x{CAVE64:x}", CH64_EPI_BR)
    if d[CH64_EPI_BR:CH64_EPI_BR + 4] == new_b:
        print("  [skip] CH64: b ES64_EPI -> b CAVE64")
    else:
        want = a64(f"b #0x{ES64_EPI:x}", CH64_EPI_BR)
        if d[CH64_EPI_BR:CH64_EPI_BR + 4] != want:
            raise RuntimeError("не нашёл `b 0x85df88` в конце CH64")
        put(d, CH64_EPI_BR, new_b, "CH64: b ES64_EPI -> b CAVE64")

    # ---- пасхалка: mov x0,xzr -> bl helper (сохранить N) ----
    new_bl = a64(f"bl #0x{HELPER64:x}", EGG64_STORE)
    if d[EGG64_STORE:EGG64_STORE + 4] == new_bl:
        print("  [skip] пасхалка: mov xzr -> bl helper")
    else:
        old = a64("mov x0, xzr", EGG64_STORE)
        if d[EGG64_STORE:EGG64_STORE + 4] != old:
            raise RuntimeError(f"не нашёл `mov x0,xzr` @0x{EGG64_STORE:x}")
        put(d, EGG64_STORE, new_bl, "пасхалка: mov xzr -> bl helper")


# ─────────── arm32 ───────────
K32 = dict(
    NEWSTR=0x415F04, FIND=0x187D118, SETACTIVE=0x187CC88, GETINT=0x1873B50,
    SET_COLOR=0x192B040, SET_TEXT=0x1ADFA48, GETCOMP=0x1879F94,
    CFN=0x415498, DG=0x415B64, DAO=0x415B68, AGI=0x39F8A0, CGT=0x4154F4,
    TGO=0x415F7C, CONCAT3=0xE0D7E4, I32TOS=0xFE14E8,
)
CACHE32 = 0x1FF6C90          # в .data (нулевой паддинг), RW
CAVE32 = 0x1C6A3CC          # код (0x1c6a3cc..0x1c6a62c свободно, 608 Б)
POOL32 = 0x1C6A588          # литеральный пул (14 слотов = 56 Б), заканчивается ровно перед строками
S32 = dict(UI=0x1C6A5C0, TEXT=0x1C6A5D0, CHBTN=0x1C6A5D8, NY=0x1C6A5E0,
           PLUS=0x1C6A5EC, BTC=0x1C6A5F0, POP=0x1C6A5F8)
HELPER32 = 0x1C6A834        # помощник (0x1c6a834..0x1c6a864 свободно)
HELPER32_POOL = 0x1C6A858
ES32_EPI = 0x1C80C14
CH32_EPI_BR = 0x1C80D8C     # `b 0x1c80c14` в конце кейва CH32
EGG32_STORE = 0x1C80B18     # `vmov s16, r0` -> `bl HELPER32`


def patch32(d):
    print("== armeabi-v7a ==")
    K, S = K32, S32

    c = Asm32(CAVE32, POOL32)
    c(
        "push {r4-r11}",
        # кеш Text
        f"LIT r0, 0x{CACHE32:x}",
        "ldr r4, [r0]",
        "cmp r4, #0",
        "bne #Lhave",
        # resolve Type(Text)
        f"bl #0x{K['DG']:x}",
        "mov r5, r0",
        f"LIT r1, 0x{S['UI']:x}",
        "mov r0, r5",
        f"bl #0x{K['DAO']:x}",
        f"bl #0x{K['AGI']:x}",
        "mov r6, r0",
        f"LIT r1, 0x{S['UI']:x}",
        f"LIT r2, 0x{S['TEXT']:x}",
        "mov r0, r6",
        f"bl #0x{K['CFN']:x}",
        f"bl #0x{K['CGT']:x}",
        f"bl #0x{K['TGO']:x}",
        "mov r7, r0",
        f"LIT r0, 0x{S['CHBTN']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0",
        "beq #Lnoch",
        "mov r1, r7",
        f"bl #0x{K['GETCOMP']:x}",
        "cmp r0, #0",
        "beq #Lnoch",
        "mov r4, r0",
        f"LIT r0, 0x{CACHE32:x}",
        "str r4, [r0]",
        "Lhave:",
        # UraniumNY -> цвет
        f"LIT r0, 0x{S['NY']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r1, #0",
        f"bl #0x{K['GETINT']:x}",
        "cmp r0, #1",
        "beq #Lgreen",
        "vmov.f32 s0, #1.0",
        "mov r0, #0",
        "vmov s1, r0",
        "b #Lcolor",
        "Lgreen:",
        "mov r0, #0",
        "vmov s0, r0",
        "vmov.f32 s1, #1.0",
        "Lcolor:",
        "mov r0, #0",
        "vmov s2, r0",
        "vmov.f32 s3, #1.0",
        "mov r0, r4",
        f"bl #0x{K['SET_COLOR']:x}",
        "Lnoch:",
        # BtcPop: pending
        f"LIT r0, 0x{CACHE32+4:x}",
        "ldr r5, [r0]",
        "cmp r5, #0",
        "beq #Lcnt",
        "mov r6, #0",
        "str r6, [r0]",
        "ldr r6, [r0, #4]",
        "add r0, r0, #4",
        f"bl #0x{K['I32TOS']:x}",
        "mov r7, r0",
        f"LIT r0, 0x{S['PLUS']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r8, r0",
        f"LIT r0, 0x{S['BTC']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r2, r0",
        "mov r0, r8",
        "mov r1, r7",
        f"bl #0x{K['CONCAT3']:x}",
        "mov r7, r0",
        f"LIT r0, 0x{S['POP']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0",
        "beq #Lcnt",
        "mov r1, r7",
        f"bl #0x{K['SET_TEXT']:x}",
        f"LIT r0, 0x{CACHE32+12:x}",
        "mov r6, #600",
        "str r6, [r0]",
        "b #Ldone",
        "Lcnt:",
        f"LIT r0, 0x{CACHE32+12:x}",
        "ldr r5, [r0]",
        "cmp r5, #0",
        "beq #Ldone",
        "sub r5, r5, #1",
        "str r5, [r0]",
        "cmp r5, #0",
        "bne #Ldone",
        f"LIT r0, 0x{S['POP']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0",
        "beq #Ldone",
        "mov r1, #0",
        f"bl #0x{K['SETACTIVE']:x}",
        "Ldone:",
        "pop {r4-r11}",
        f"b #0x{ES32_EPI:x}",
    )
    blob, pool = c.assemble()
    if CAVE32 + len(blob) > POOL32:
        raise RuntimeError(f"кейв b17 (arm32) не влез: {len(blob)}")
    put(d, CAVE32, blob, "кейв b17 (arm32): CH-цвет + BtcPop")
    put(d, POOL32, pool, "пул кейва b17 (arm32)")

    # строки
    put(d, S32["UI"], b"UnityEngine.UI\x00\x00", "строка UnityEngine.UI")
    put(d, S32["TEXT"], b"Text\x00\x00\x00\x00", "строка Text")
    put(d, S32["CHBTN"], b"CH_Btn\x00\x00", "строка CH_Btn")
    put(d, S32["NY"], b"UraniumNY\x00\x00\x00", "строка UraniumNY")
    put(d, S32["PLUS"], b"+\x00\x00\x00", "строка +")
    put(d, S32["BTC"], b" BTC\x00\x00\x00", "строка BTC")
    put(d, S32["POP"], b"BtcPop\x00\x00", "строка BtcPop")

    # помощник «сохранить N»
    h = Asm32(HELPER32, HELPER32_POOL)
    h(
        "push {r4-r11, lr}",
        f"LIT r9, 0x{CACHE32:x}",
        "str r0, [r9, #8]",
        "mov r8, #1",
        "str r8, [r9, #4]",
        "vmov s16, r0",
        "pop {r4-r11, pc}",
    )
    hblob, hpool = h.assemble()
    if HELPER32 + len(hblob) > HELPER32_POOL:
        raise RuntimeError(f"хелпер (arm32) не влез: {len(hblob)}")
    put(d, HELPER32, hblob, "хелпер (arm32): сохранить N")
    put(d, HELPER32_POOL, hpool, "пул хелпера (arm32)")

    # хуки
    new_b = a32(f"b #0x{CAVE32:x}", CH32_EPI_BR)
    if d[CH32_EPI_BR:CH32_EPI_BR + 4] == new_b:
        print("  [skip] CH32: b ES32_EPI -> b CAVE32")
    else:
        old = a32("b 0x1c80c14", CH32_EPI_BR)
        if d[CH32_EPI_BR:CH32_EPI_BR + 4] != old:
            raise RuntimeError("не нашёл `b 0x1c80c14` в конце CH32")
        put(d, CH32_EPI_BR, new_b, "CH32: b ES32_EPI -> b CAVE32")

    new_bl = a32(f"bl #0x{HELPER32:x}", EGG32_STORE)
    if d[EGG32_STORE:EGG32_STORE + 4] == new_bl:
        print("  [skip] пасхалка: vmov s16,r0 -> bl helper")
    else:
        old2 = a32("vmov s16, r0", EGG32_STORE)
        if d[EGG32_STORE:EGG32_STORE + 4] != old2:
            raise RuntimeError(f"не нашёл `vmov s16, r0` @0x{EGG32_STORE:x}")
        put(d, EGG32_STORE, new_bl, "пасхалка: vmov s16,r0 -> bl helper")


def put(data, va, blob, what, expect=None):
    if data[va:va + len(blob)] == blob:
        print(f"  [skip] {what} @0x{va:x}")
        return
    if expect is not None and data[va:va + len(expect)] != expect:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {expect.hex(' ')}, "
                           f"найдено {data[va:va + len(expect)].hex(' ')}")
    data[va:va + len(blob)] = blob
    print(f"  [ ok ] {what} @0x{va:x} ({len(blob)} Б)")


def main():
    with open(SO64, "rb") as f:
        d64 = bytearray(f.read())
    patch64(d64)
    with open(SO64, "wb") as f:
        f.write(bytes(d64))
    print("arm64 готово.")

    with open(SO32, "rb") as f:
        d32 = bytearray(f.read())
    patch32(d32)
    with open(SO32, "wb") as f:
        f.write(bytes(d32))
    print("arm32 готово.")


if __name__ == "__main__":
    main()
