#!/usr/bin/env python3
"""Патчи libil2cpp.so v5 (b7) — поверх v3 (b5), ПОСЛЕ ОТКАТА v4-инжектов.

Философия b7: минимум вторжений в рабочий поток. Из v4 остаются только:
  1. Фикс краха PrintExpert: ветки «неверный размер» и «не хватает денег»
     пишут сообщение в fileNameText.text (вирт. set_text) вместо вызова
     Main.FadeText (SEGV). Эти ветки НЕ участвуют в успешной покупке.
  2. Универсальные принтеры: Printer.Supports принимает сторону, равную
     supportedPrintSize, и её удвоения: w, 2w, 4w, 8w (и для h).
     => Apson A3 128x128 печатает 128/256/512/1024; 32x32 — до 256.
     Отдельные карточки 512/1024 не нужны.

Откатено (не применяется): клон PrintExpert и кнопка-переключатель,
Purchase-спавн «всегда bannerPrefab», SelectFile/Purchase selectedFile-хуки.
"""
import sys, os
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KS_ARCH_ARM, KS_MODE_ARM

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

ks64 = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
ks32 = Ks(KS_ARCH_ARM, KS_MODE_ARM)

def asm64(code, addr):
    enc, _ = ks64.asm(code, addr); return bytes(enc)
def asm32(code, addr):
    enc, _ = ks32.asm(code, addr); return bytes(enc)

def patch(data, va, old, new, what):
    cur = data[va:va + len(old)]
    if cur == new[:len(new)]:
        print(f"  [skip] {what} @0x{va:x}"); return
    if cur != old:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex(' ')}, найдено {cur.hex(' ')}")
    assert len(new) == len(old)
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x}")

def asm_block64(va, lines):
    return b"".join(asm64(l, va + 4*i) for i, l in enumerate(lines))
def asm_block32(va, lines):
    return b"".join(asm32(l, va + 4*i) for i, l in enumerate(lines))

def cave(data, va, new, what):
    cur = data[va:va + len(new)]
    if cur == new:
        print(f"  [skip] {what} @0x{va:x}"); return
    if cur != b"\x00" * len(new):
        raise RuntimeError(f"{what} @0x{va:x}: кейв не пуст: {cur[:16].hex(' ')}...")
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x} ({len(new)}Б)")

# ============================================================================
CAVE64_SUP = 0x85DAE0
CAVE32_SUP = 0x1C6A180

def patch_arm64(data):
    print("== arm64-v8a ==")
    # 1a. «Неверный размер» -> fileNameText (0x8674AC, v3-блок FadeText, 23 инструкции)
    old = asm_block64(0x8674AC, [
        "mov x20, x0", "bl #0x7e0c50", "cbz x0, #0x867508",
        "mov x1, x20", "mov x2, xzr", "b #0x7e23b8",
    ] + ["nop"] * 17)
    new = asm_block64(0x8674AC, [
        "mov x20, x0",
        "ldr x0, [x19, #0x38]",
        "mov x2, xzr",
        "cbz x0, #0x867508",
        "mov x1, xzr",
        "bl #0x17d3c10",
        "tbz w0, #0, #0x867508",
        "ldr x0, [x19, #0x38]",
        "ldr x8, [x0]",
        "ldr x3, [x8, #0x5e8]",
        "ldr x2, [x8, #0x5f0]",
        "mov x1, x20",
        "blr x3",
        "b #0x867508",
    ] + ["nop"] * 9)
    patch(data, 0x8674AC, old, new, "Purchase: неверный размер -> fileNameText")

    # 1b. «Не хватает денег» -> fileNameText (0x86751C, 10 инструкций)
    old = asm_block64(0x86751C, [
        "adrp x8, #0x2246000",
        "ldr x8, [x8, #0x940]",
        "mov x0, x21",
        "ldp x19, x30, [sp, #0x30]",
        "ldp x21, x20, [sp, #0x20]",
        "ldr x1, [x8]",
        "ldp x23, x22, [sp, #0x10]",
        "mov x2, xzr",
        "ldp x25, x24, [sp], #0x40",
        "b #0x7e23b8",
    ])
    new = asm_block64(0x86751C, [
        "adrp x8, #0x2246000",
        "ldr x8, [x8, #0x940]",
        "ldr x20, [x8]",
        "ldr x0, [x19, #0x38]",
        "ldr x8, [x0]",
        "ldr x3, [x8, #0x5e8]",
        "ldr x2, [x8, #0x5f0]",
        "mov x1, x20",
        "blr x3",
        "b #0x867508",
    ])
    patch(data, 0x86751C, old, new, "Purchase: не хватает денег -> fileNameText")

    # 2. Supports: w==sw || 2w==sw || 4w==sw || 8w==sw (аналогично h)
    A = CAVE64_SUP
    instrs = [
        "ldr w8, [x19, #0x74]", "cmp w8, #1", "csinc w8, w8, wzr, gt",
        "cmp w0, w8", "b.eq #LokW",
        "lsl w10, w0, #1", "cmp w10, w8", "b.eq #LokW",
        "lsl w10, w0, #2", "cmp w10, w8", "b.eq #LokW",
        "lsl w10, w0, #3", "cmp w10, w8", "b.ne #Lfalse",
        "LokW:",
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x198]", "blr x9",
        "ldr w8, [x19, #0x78]", "cmp w8, #1", "csinc w8, w8, wzr, gt",
        "cmp w0, w8", "b.eq #LokH",
        "lsl w10, w0, #1", "cmp w10, w8", "b.eq #LokH",
        "lsl w10, w0, #2", "cmp w10, w8", "b.eq #LokH",
        "lsl w10, w0, #3", "cmp w10, w8", "b.ne #Lfalse",
        "LokH:", "mov w0, #1", "b #Lend",
        "Lfalse:", "mov w0, wzr",
        "Lend:", "b #0x834f34",
    ]
    # резолв меток в адреса
    labels = {}
    addr = A
    resolved = []
    for ln in instrs:
        ln = ln.strip()
        if ln.endswith(":"):
            labels[ln[:-1]] = addr
            continue
        resolved.append((addr, ln))
        addr += 4
    blob = b""
    for a, ln in resolved:
        for name, target in labels.items():
            ln = ln.replace("#" + name, "#0x%x" % target)
        blob += asm64(ln, a)
    cave(data, A, blob, "кейв sup64 (w|2w|4w|8w)")

    old = asm_block64(0x834EF4, [
        "ldr w8, [x19, #0x74]", "cmp w8, #1", "csinc w8, w8, wzr, gt",
        "cmp w0, w8", "b.ne #0x834f30", "ldr x8, [x20]",
    ])
    new = asm_block64(0x834EF4, ["b #0x%x" % CAVE64_SUP] + ["nop"] * 5)
    patch(data, 0x834EF4, old, new, "Printer.Supports -> кейв")

def patch_arm32(data):
    print("== armeabi-v7a ==")
    # 1a-32. «Неверный размер» (0x58bb48, v3-блок, 22 инструкции)
    old = asm_block32(0x58BB48, [
        "bl #0x4dbd78", "cmp r0, #0", "beq #0x58bba4",
        "mov r1, r5", "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}",
        "b #0x4ddc14",
    ] + ["nop"] * 15)
    new = asm_block32(0x58BB48, [
        "ldr r0, [r4, #0x1c]",
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, #0", "mov r2, #0",
        "bl #0x1881fd8",
        "cmp r0, #0",
        "beq #0x58bba4",
        "ldr r0, [r4, #0x1c]",
        "ldr r3, [r0, #0x314]",
        "ldr r2, [r0, #0x318]",
        "mov r1, r5",
        "blx r3",
        "b #0x58bba4",
    ] + ["nop"] * 8)
    patch(data, 0x58BB48, old, new, "Purchase32: неверный размер -> fileNameText")

    # 1b-32. «Не хватает денег» (0x58bba8, 11 инструкций)
    old = asm_block32(0x58BBA8, [
        "ldr r0, [pc, #0x54]", "cmp r6, #0", "ldr r0, [pc, r0]", "ldr r4, [r0]",
        "bne #0x58bbc0", "bl #0x3b54d0",
        "mov r0, r6", "mov r1, r4", "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}", "b #0x4ddc14",
    ])
    new = asm_block32(0x58BBA8, [
        "ldr r0, [pc, #0x54]", "ldr r0, [pc, r0]", "ldr r1, [r0]",
        "ldr r0, [r4, #0x1c]",
        "ldr r3, [r0, #0x314]", "ldr r2, [r0, #0x318]",
        "blx r3",
        "pop {r4, r5, r6, r7, r8, sb, sl, pc}",
        "nop", "nop", "nop",
    ])
    patch(data, 0x58BBA8, old, new, "Purchase32: не хватает денег -> fileNameText")

    # 2-32. Supports
    A = CAVE32_SUP
    instrs = [
        "ldr r1, [r4, #0x4c]", "mov r7, #1", "cmp r1, #1", "movle r1, r7",
        "cmp r0, r1", "beq #LokW",
        "lsl r2, r0, #1", "cmp r2, r1", "beq #LokW",
        "lsl r2, r0, #2", "cmp r2, r1", "beq #LokW",
        "lsl r2, r0, #3", "cmp r2, r1", "bne #Lfalse",
        "LokW:",
        "ldr r0, [r5]", "ldr r2, [r0, #0xec]", "ldr r1, [r0, #0xf0]",
        "mov r0, r5", "blx r2",
        "ldr r1, [r4, #0x50]", "mov r7, #1", "cmp r1, #1", "movle r1, r7",
        "cmp r0, r1", "beq #LokH",
        "lsl r2, r0, #1", "cmp r2, r1", "beq #LokH",
        "lsl r2, r0, #2", "cmp r2, r1", "beq #LokH",
        "lsl r2, r0, #3", "cmp r2, r1", "bne #Lfalse",
        "LokH:", "mov r0, #1", "b #Lend",
        "Lfalse:", "mov r0, #0",
        "Lend:", "b #0x54abf0",
    ]
    labels = {}
    addr = A
    resolved = []
    for ln in instrs:
        ln = ln.strip()
        if ln.endswith(":"):
            labels[ln[:-1]] = addr
            continue
        resolved.append((addr, ln))
        addr += 4
    blob = b""
    for a, ln in resolved:
        for name, target in labels.items():
            ln = ln.replace("#" + name, "#0x%x" % target)
        blob += asm32(ln, a)
    cave(data, A, blob, "кейв sup32 (w|2w|4w|8w)")

    old = asm_block32(0x54ABA8, ["ldr r1, [r4, #0x4c]"])
    new = asm_block32(0x54ABA8, ["b #0x%x" % CAVE32_SUP])
    patch(data, 0x54ABA8, old, new, "Printer.Supports32 -> кейв")

if __name__ == "__main__":
    for path, fn in ((SO64, patch_arm64), (SO32, patch_arm32)):
        print(f"--- {path}")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
    print("Готово.")
