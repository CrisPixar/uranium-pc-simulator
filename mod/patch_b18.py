#!/usr/bin/env python3
"""Uranium PC Simulator — b18: фикс краша (SIGSEGV null deref) из b17.

Причина краша b17 (arm64, сигнатурный лог с Infinix X676B, Android 12):
  кейв b17 @0x85e320 перед вызовом DomainAssemblyOpen (венер 0x6fb874 =
  `mov x0, x1; b 0x724778`) клал адрес строки "UnityEngine.UI" в x0,
  затирая домен (x0 от DG), а имя передавалось мусором из x1
  (в arm32-версии то же место написано ПРАВИЛЬНО: mov r0,r5; LIT r1,UI).
  DomainAssemblyOpen возвращал NULL -> следующий вызов AssemblyGetImage
  (венер 0x6fb23c -> `ldr x0,[x0]; ret` @0x724770) читал [NULL] -> SIGSEGV.
  Дополнительно: кэш Text был сырым указателем в .data (не GC-root) —
  потенциальный dangling после смены сцены.

b18 (обе арки, идемпотентно):
  1. Правильные аргументы: mov x0, x21 (домен); LIT x1, "UnityEngine.UI".
  2. null-guard (cbz -> Lnoch) после КАЖДОГО шага рефлексии:
     DG -> DAO -> AGI -> CFN -> TGO -> FIND -> GETCOMP.
     При неудаче кадр просто пропускает покраску (ретрай в следующем кадре).
  3. Кэш Text убран: Find("CH_Btn")+GetComponent каждый кадр (как в остальном
     коде мода) — нет dangling-указателей, слот [CACHE+0] больше не используется
     (флаги BtcPop [+8/+0xc/+0x10] и хелпер 0x85e4c0 не изменились).

Запуск: python3 mod/patch_b18.py [дерево]   (по умолчанию текущее)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asmlib import Asm64, Asm32, a64, a32  # noqa: E402

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
S64 = dict(UI=0x85E4E0, TEXT=0x85E4F0, CHBTN=0x85E4F8, NY=0x85E500,
           PLUS=0x85E50C, BTC=0x85E510, POP=0x85E518,
           GREEN=0x85E520, RED=0x85E530)
CACHE64 = 0x2263560          # [8]=pending, [0xc]=amount, [0x10]=countdown
CH64_EPI_BR = 0x85E204       # `b 0x85e320` (поставлен в b17) — не меняем
ES64_EPI = 0x85DF88
CAVE64 = 0x85E320            # кейв (0x85e320..0x85e4c0, 660 Б)
HELPER64 = 0x85E4C0          # хелпер «сохранить N» — не меняем
EGG64_STORE = 0x85DED0       # bl HELPER64 (b17) — не меняем


def patch64(d):
    print("== arm64-v8a ==")
    K, S = K64, S64

    # sanity: хуки b17 на месте
    assert d[CH64_EPI_BR:CH64_EPI_BR + 4] == a64(f"b #0x{CAVE64:x}", CH64_EPI_BR), \
        "CH64_EPI_BR: нет b -> CAVE64 (сначала patch_b17)"
    assert d[EGG64_STORE:EGG64_STORE + 4] == a64(f"bl #0x{HELPER64:x}", EGG64_STORE), \
        "EGG64_STORE: нет bl HELPER64 (сначала patch_b17)"

    c = Asm64(CAVE64)
    c(
        "stp x29, x30, [sp, #-0x10]!",
        "stp x19, x20, [sp, #-0x10]!",
        "stp x21, x22, [sp, #-0x10]!",
        "stp x23, x24, [sp, #-0x10]!",
        # ---- resolve Type(UnityEngine.UI.Text): каждый кадр, с гардами ----
        "Lresolve:",
        f"bl #0x{K['DG']:x}",                 # x0 = il2cpp domain
        "cbz x0, #Lnoch",
        "mov x21, x0",                        # x21 = domain  (ФИКС: сохраняем)
        f"LIT x1, 0x{S['UI']:x}",             # x1 = "UnityEngine.UI"  (ФИКС: x1, не x0)
        "mov x0, x21",                        # x0 = domain            (ФИКС)
        f"bl #0x{K['DAO']:x}",                # x0 = assembly (DomainAssemblyOpen)
        "cbz x0, #Lnoch",
        f"bl #0x{K['AGI']:x}",                # x0 = image (AssemblyGetImage)
        "cbz x0, #Lnoch",
        f"LIT x1, 0x{S['UI']:x}",             # x1 = namespace
        f"LIT x2, 0x{S['TEXT']:x}",           # x2 = "Text"
        f"bl #0x{K['CFN']:x}",                # x0 = klass (ClassFromName)
        "cbz x0, #Lnoch",
        f"bl #0x{K['CGT']:x}",
        f"bl #0x{K['TGO']:x}",                # x0 = System.Type
        "cbz x0, #Lnoch",
        "mov x22, x0",
        f"LIT x0, 0x{S['CHBTN']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",               # x0 = GO "CH_Btn"
        "cbz x0, #Lnoch",
        "mov x1, x22",
        f"bl #0x{K['GETCOMP']:x}",            # x0 = Text
        "cbz x0, #Lnoch",
        "mov x19, x0",
        # ---- цвет по UraniumNY ----
        "Lcolor:",
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
        # ---- BtcPop: pending? (как в b17) ----
        f"LIT x20, 0x{CACHE64 + 8:x}",
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
        f"LIT x20, 0x{CACHE64 + 0x10:x}",
        "mov w8, #0x258",
        "str w8, [x20]",
        "b #Ldone",
        "Lcnt:",
        f"LIT x20, 0x{CACHE64 + 0x10:x}",
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
        raise RuntimeError(f"кейв b18 не влез: {len(blob)}")
    put(d, CAVE64, blob, "кейв b18: CH-цвет + BtcPop (фикс регистров + гарды)")

    # строки/константы — те же адреса (идемпотентно)
    put(d, S64["UI"], b"UnityEngine.UI\x00\x00", "строка UnityEngine.UI")
    put(d, S64["TEXT"], b"Text\x00\x00\x00\x00", "строка Text")
    put(d, S64["CHBTN"], b"CH_Btn\x00", "строка CH_Btn")
    put(d, S64["NY"], b"UraniumNY\x00\x00\x00", "строка UraniumNY")
    put(d, S64["PLUS"], b"+\x00\x00\x00", "строка +")
    put(d, S64["BTC"], b" BTC\x00\x00\x00", "строка BTC")
    put(d, S64["POP"], b"BtcPop\x00\x00", "строка BtcPop")
    put(d, S64["GREEN"], struct.pack("<4f", 0.0, 1.0, 0.0, 1.0), "константа green")
    put(d, S64["RED"], struct.pack("<4f", 1.0, 0.0, 0.0, 1.0), "константа red")

    # чек-инфо для build.yml
    print("  -- чек-байты b18 (arm64) --")
    for off in (CAVE64, CAVE64 + 0x10, CAVE64 + 0x14, CAVE64 + 0x1C, CAVE64 + 0x24):
        print(f"   @0x{off:x}: {d[off:off+4].hex()}")


# ─────────── arm32 ───────────
K32 = dict(
    NEWSTR=0x415F04, FIND=0x187D118, SETACTIVE=0x187CC88, GETINT=0x1873B50,
    SET_COLOR=0x192B040, SET_TEXT=0x1ADFA48, GETCOMP=0x1879F94,
    CFN=0x415498, DG=0x415B64, DAO=0x415B68, AGI=0x39F8A0, CGT=0x4154F4,
    TGO=0x415F7C, CONCAT3=0xE0D7E4, I32TOS=0xFE14E8,
)
CACHE32 = 0x1FF6C90          # [4]=pending, [8]=amount, [0xc]=countdown
CAVE32 = 0x1C6A3CC
POOL32 = 0x1C6A588
S32 = dict(UI=0x1C6A5C0, TEXT=0x1C6A5D0, CHBTN=0x1C6A5D8, NY=0x1C6A5E0,
           PLUS=0x1C6A5EC, BTC=0x1C6A5F0, POP=0x1C6A5F8)
HELPER32 = 0x1C6A834
HELPER32_POOL = 0x1C6A858
ES32_EPI = 0x1C80C14
CH32_EPI_BR = 0x1C80D8C
EGG32_STORE = 0x1C80B18


def patch32(d):
    print("== armeabi-v7a ==")
    K, S = K32, S32

    assert d[CH32_EPI_BR:CH32_EPI_BR + 4] == a32(f"b #0x{CAVE32:x}", CH32_EPI_BR), \
        "CH32_EPI_BR: нет b -> CAVE32 (сначала patch_b17)"
    assert d[EGG32_STORE:EGG32_STORE + 4] == a32(f"bl #0x{HELPER32:x}", EGG32_STORE), \
        "EGG32_STORE: нет bl HELPER32 (сначала patch_b17)"

    c = Asm32(CAVE32, POOL32)
    c(
        "push {r4-r11}",
        "Lresolve:",
        f"bl #0x{K['DG']:x}",                 # r0 = domain (держим в r0)
        "cmp r0, #0",
        "beq #Lnoch",
        f"LIT r1, 0x{S['UI']:x}",             # r1 = "UnityEngine.UI" (r0 = домен)
        f"bl #0x{K['DAO']:x}",
        "cmp r0, #0",
        "beq #Lnoch",
        f"bl #0x{K['AGI']:x}",                # r0 = image (держим в r0)
        "cmp r0, #0",
        "beq #Lnoch",
        f"LIT r1, 0x{S['UI']:x}",
        f"LIT r2, 0x{S['TEXT']:x}",
        f"bl #0x{K['CFN']:x}",
        "cmp r0, #0",
        "beq #Lnoch",
        f"bl #0x{K['CGT']:x}",
        f"bl #0x{K['TGO']:x}",
        "cmp r0, #0",
        "beq #Lnoch",
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
        # ---- цвет ----
        "Lcolor:",
        f"LIT r0, 0x{S['NY']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r1, #0",
        f"bl #0x{K['GETINT']:x}",
        "cmp r0, #1",
        "beq #Lgreen",
        "vmov.f32 s0, #1.0",
        "mov r0, #0",
        "vmov s1, r0",
        "b #Lcolorset",
        "Lgreen:",
        "mov r0, #0",
        "vmov s0, r0",
        "vmov.f32 s1, #1.0",
        "Lcolorset:",
        "mov r0, #0",
        "vmov s2, r0",
        "vmov.f32 s3, #1.0",
        "mov r0, r4",
        f"bl #0x{K['SET_COLOR']:x}",
        "Lnoch:",
        # ---- BtcPop (как в b17) ----
        f"LIT r0, 0x{CACHE32 + 4:x}",
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
        f"LIT r0, 0x{CACHE32 + 12:x}",
        "mov r6, #600",
        "str r6, [r0]",
        "b #Ldone",
        "Lcnt:",
        f"LIT r0, 0x{CACHE32 + 12:x}",
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
        raise RuntimeError(f"кейв b18 (arm32) не влез: {len(blob)}")
    if POOL32 + len(pool) > S32["UI"]:
        raise RuntimeError(f"пул b18 (arm32) не влез: {len(pool)}")
    put(d, CAVE32, blob, "кейв b18 (arm32): CH-цвет + BtcPop (гарды)")
    put(d, POOL32, pool, "пул кейва b18 (arm32)")

    put(d, S32["UI"], b"UnityEngine.UI\x00\x00", "строка UnityEngine.UI")
    put(d, S32["TEXT"], b"Text\x00\x00\x00\x00", "строка Text")
    put(d, S32["CHBTN"], b"CH_Btn\x00\x00", "строка CH_Btn")
    put(d, S32["NY"], b"UraniumNY\x00\x00\x00", "строка UraniumNY")
    put(d, S32["PLUS"], b"+\x00\x00\x00", "строка +")
    put(d, S32["BTC"], b" BTC\x00\x00\x00", "строка BTC")
    put(d, S32["POP"], b"BtcPop\x00\x00", "строка BtcPop")

    print("  -- чек-байты b18 (arm32) --")
    for off in (CAVE32, CAVE32 + 0x14, CAVE32 + 0x18):
        print(f"   @0x{off:x}: {d[off:off+4].hex()}")


def put(data, va, blob, what):
    if data[va:va + len(blob)] == blob:
        print(f"  [skip] {what} @0x{va:x}")
        return
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
