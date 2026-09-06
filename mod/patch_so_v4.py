#!/usr/bin/env python3
"""Патчи libil2cpp.so v4 для мода Uranium PC Simulator (arm64-v8a + armeabi-v7a).

Требования v4 (поверх v3):
  1. Фикс краха сайта PrintExpert: Main.FadeText (StopCoroutine("Fade") → SEGV
     при живых корутинах) больше НЕ вызывается. Сообщения об ошибках
     («неверный размер», «не хватает денег») выводятся через виртуальный
     Text.set_text на fileNameText (PrintExpert.fileNameText).
  2. Переключатель баннера на сайте: Purchase всегда спавнит this.bannerPrefab
     (какой MB-клон вызван — такой баннер и появится). Проверка размера
     (sz-кейв v3) принимает 32x70 и 70x32 — не зависит от кнопки.
  3. Универсальный принтер: Printer.Supports принимает w==sw или w*2==sw
     (512x512 и 1024x1024 при supportedPrintSize=1024x1024).

Идемпотентен: если байты уже равны новым — пропуск.
"""
import sys, os
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KS_ARCH_ARM, KS_MODE_ARM

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
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
    """Применить патч с проверкой оригинала. VA == file offset (RX-сегмент)."""
    cur = data[va:va + len(old)]
    if cur == new[:len(new)]:
        print(f"  [skip] {what} @0x{va:x}: уже применён")
        return
    if cur != old:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex(' ')}, найдено {cur.hex(' ')}")
    assert len(new) == len(old), f"{what}: размер {len(new)} != {len(old)}"
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x} ({len(new)} байт)")

def asm_block64(va, lines):
    out = b""
    for i, ln in enumerate(lines):
        out += asm64(ln, va + 4 * i)
    return out

def asm_block32(va, lines):
    out = b""
    for i, ln in enumerate(lines):
        out += asm32(ln, va + 4 * i)
    return out

def cave(data, va, new, what):
    cur = data[va:va + len(new)]
    if cur == new:
        print(f"  [skip] {what} @0x{va:x}: уже записан")
        return
    if cur != b"\x00" * len(new):
        raise RuntimeError(f"{what} @0x{va:x}: кейв не пуст: {cur[:16].hex(' ')}...")
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x} ({len(new)} байт)")

# ============================================================================
#  ARM64 (arm64-v8a)
# ============================================================================
CAVE64     = 0x85D978   # нулевой паддинг 0x85d978..0x85e96c (v3 занял ~0xb0)
CAVE64_SUP = 0x85DAE0   # универсальный Supports (свободная нулевая зона)
CAVE64_FILE = 0x85DB38  # selectedFile-слот (после sup-кейва)
FILE_SLOT64 = 0x23BA034 # RW-сегмент: vaddr (файл 0x23b9034, нулевой паддинг 148Б)

def patch_arm64(data):
    print("== arm64-v8a ==")

    # --- 1a. «Неверный размер»: v3-блок FadeText → fileNameText (0x8674AC, 23 инструкции) ---
    old = asm_block64(0x8674AC, [
        "mov x20, x0", "bl #0x7e0c50", "cbz x0, #0x867508",
        "mov x1, x20", "mov x2, xzr", "b #0x7e23b8",
    ] + ["nop"] * 17)
    new = asm_block64(0x8674AC, [
        "mov x20, x0",                    # msg
        "ldr x0, [x19, #0x38]",           # fileNameText
        "mov x2, xzr",
        "cbz x0, #0x867508",
        "mov x1, xzr",
        "bl #0x17d3c10",                  # UnityEngine.Object bool (destroyed-check)
        "tbz w0, #0, #0x867508",
        "ldr x0, [x19, #0x38]",           # fileNameText (reload после вызова)
        "ldr x8, [x0]",                   # klass
        "ldr x3, [x8, #0x5e8]",           # Text.set_text (вирт. слот)
        "ldr x2, [x8, #0x5f0]",           # method info
        "mov x1, x20",                    # msg
        "blr x3",                         # fileNameText.text = msg
        "b #0x867508",                    # выход (эпилог)
    ] + ["nop"] * 9)
    patch(data, 0x8674AC, old, new, "Purchase: неверный размер -> fileNameText (без FadeText)")

    # --- 1b. «Не хватает денег»: ориг. tail FadeText -> fileNameText (0x86751C, 11 инструкций) ---
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
    # NOTE: old-блок — 10 инструкций (0x86751c..0x867540), 0x867544 (throw) не трогаем.
    new = asm_block64(0x86751C, [
        "adrp x8, #0x2246000",
        "ldr x8, [x8, #0x940]",           # обёртка литерала «не хватает денег»
        "ldr x20, [x8]",                  # msg
        "ldr x0, [x19, #0x38]",           # fileNameText
        "ldr x8, [x0]",                   # klass
        "ldr x3, [x8, #0x5e8]",           # set_text
        "ldr x2, [x8, #0x5f0]",
        "mov x1, x20",                    # msg
        "blr x3",                         # fileNameText.text = msg
        "b #0x867508",                    # выход (эпилог до блока)
    ])
    patch(data, 0x86751C, old, new, "Purchase: не хватает денег -> fileNameText (без FadeText)")

    # --- 2. Спавн: всегда this.bannerPrefab (0x867394, v3-блок 25 инструкций) ---
    old = asm_block64(0x867394, [
        "fmov w23, s9",
        "cmp w23, #0x46",
        "b.ne #0x8673a8",
        "ldr x23, [x19, #0x50]",
        "b #0x8673ac",
        "ldr x23, [x19, #0x30]",
        "mov x0, x23",
        "bl #0x17cd6b8",
        "mov x1, x0",
        "mov x0, x21",
        "mov x2, xzr",
        "bl #0x7e2a00",
        "cbz x0, #0x867544",
        "mov x23, x0",
        "adrp x8, #0x224a000",
        "ldr x8, [x8, #0x9b8]",
        "ldr x1, [x8]",
        "mov x0, x23",
        "bl #0x8ccd94",
        "mov x23, x0",
        "mov x0, x23",
        "mov x1, x20",
        "mov x2, x22",
        "mov x3, xzr",
        "bl #0x816ec8",
    ])
    new = asm_block64(0x867394, [
        "ldr x23, [x19, #0x30]",          # bannerPrefab — всегда (кнопка решает)
        "mov x0, x23",
        "bl #0x17cd6b8",                  # get_gameObject(prefab)
        "mov x1, x0",
        "mov x0, x21",                    # Main.Instance
        "mov x2, xzr",
        "bl #0x7e2a00",                   # InstantDelivery(prefabGO)
        "cbz x0, #0x867544",
        "mov x23, x0",                    # доставленный GO
        "adrp x8, #0x224a000",
        "ldr x8, [x8, #0x9b8]",
        "ldr x1, [x8]",                   # класс TextureLoader
        "mov x0, x23",
        "bl #0x8ccd94",                   # GetComponent<TextureLoader>
        "mov x23, x0",
        "mov x0, x23",
        "mov x1, x20",                    # tex
        "mov x2, x22",                    # png
        "mov x3, xzr",
        "bl #0x816ec8",                   # SetTexture(loader, tex, png, 0)
    ] + ["nop"] * 5)
    patch(data, 0x867394, old, new, "Purchase: спавн всегда bannerPrefab (по кнопке)")

    # --- 3. Универсальный Supports: кейв (w==sw || 2w==sw) && (h==sh || 2h==sh) ---
    cave(data, CAVE64_SUP, b"".join([
        asm64("ldr w8, [x19, #0x74]", CAVE64_SUP + 0x00),   # sw
        asm64("cmp w8, #1", CAVE64_SUP + 0x04),
        asm64("csinc w8, w8, wzr, gt", CAVE64_SUP + 0x08),  # max(sw,1)
        asm64("cmp w0, w8", CAVE64_SUP + 0x0C),
        asm64("b.eq #0x%x" % (CAVE64_SUP + 0x20), CAVE64_SUP + 0x10),   # -> LokW
        asm64("lsl w10, w0, #1", CAVE64_SUP + 0x14),
        asm64("cmp w10, w8", CAVE64_SUP + 0x18),
        asm64("b.ne #0x834f30", CAVE64_SUP + 0x1C),         # -> false
        # LokW:
        asm64("ldr x8, [x20]", CAVE64_SUP + 0x20),          # klass picture
        asm64("mov x0, x20", CAVE64_SUP + 0x24),
        asm64("ldp x9, x1, [x8, #0x198]", CAVE64_SUP + 0x28),  # get_height
        asm64("blr x9", CAVE64_SUP + 0x2C),
        asm64("ldr w8, [x19, #0x78]", CAVE64_SUP + 0x30),   # sh
        asm64("cmp w8, #1", CAVE64_SUP + 0x34),
        asm64("csinc w8, w8, wzr, gt", CAVE64_SUP + 0x38),
        asm64("cmp w0, w8", CAVE64_SUP + 0x3C),
        asm64("b.eq #0x%x" % (CAVE64_SUP + 0x50), CAVE64_SUP + 0x40),   # -> LokH
        asm64("lsl w10, w0, #1", CAVE64_SUP + 0x44),
        asm64("cmp w10, w8", CAVE64_SUP + 0x48),
        asm64("b.ne #0x834f30", CAVE64_SUP + 0x4C),
        # LokH:
        asm64("mov w0, #1", CAVE64_SUP + 0x50),
        asm64("b #0x834f34", CAVE64_SUP + 0x54),            # -> эпилог
    ]), "кейв sup64 (универсальный размер)")

    # точка входа: 0x834EF4 (w-блок ориг., 6 инструкций) -> b кейв
    old = asm_block64(0x834EF4, [
        "ldr w8, [x19, #0x74]",
        "cmp w8, #1",
        "csinc w8, w8, wzr, gt",
        "cmp w0, w8",
        "b.ne #0x834f30",
        "ldr x8, [x20]",
    ])
    new = asm_block64(0x834EF4, [
        "b #0x%x" % CAVE64_SUP, "nop", "nop", "nop", "nop", "nop",
    ])
    patch(data, 0x834EF4, old, new, "Printer.Supports -> кейв (w==sw||2w==sw)")

    # --- 4. selectedFile-слот: хук Purchase @0x8671f8 (tbnz) -> кейв ---

    # Оригинал (11239) при каждом Purchase кладёт свой selectedFile в слот;
    # клон (горизонтальный PrintExpert) при null берёт файл из слота.
    cave(data, CAVE64_FILE, b"".join([
        asm64("ldr x9, [x19, #0x60]", CAVE64_FILE + 0x00),      # selectedFile
        asm64("cbnz x9, #0x%x" % (CAVE64_FILE + 0x20), CAVE64_FILE + 0x04),  # -> Lhave
        asm64("adrp x10, #0x23ba000", CAVE64_FILE + 0x08),
        asm64("ldr x10, [x10, #0x34]", CAVE64_FILE + 0x0C),     # FILE_SLOT64
        asm64("cbz x10, #0x%x" % (CAVE64_FILE + 0x2C), CAVE64_FILE + 0x10),  # -> Ldone
        asm64("str x10, [x19, #0x60]", CAVE64_FILE + 0x14),     # клон: взять
        asm64("b #0x%x" % (CAVE64_FILE + 0x2C), CAVE64_FILE + 0x18),         # -> Ldone
        asm64("nop", CAVE64_FILE + 0x1C),
        # Lhave:
        asm64("adrp x10, #0x23ba000", CAVE64_FILE + 0x20),
        asm64("str x9, [x10, #0x34]", CAVE64_FILE + 0x24),      # оригинал: запомнить
        # Ldone (ориг. инструкция хук-точки):
        asm64("tbnz w8, #0, #0x867258", CAVE64_FILE + 0x2C),
        asm64("b #0x8671fc", CAVE64_FILE + 0x30),
    ]), "кейв file64 (selectedFile-слот)")
    old = asm_block64(0x8671F8, [
        "tbnz w8, #0, #0x867258",
    ])
    new = asm_block64(0x8671F8, [
        "b #0x%x" % CAVE64_FILE,
    ])
    patch(data, 0x8671F8, old, new, "Purchase -> selectedFile-слот (хук)")

    # --- 5. SelectFile: сохранить выбранный файл в слот (для клона) ---
    CAVE64_SEL = 0x85DB68
    cave(data, CAVE64_SEL, b"".join([
        asm64("stp x19, x30, [sp, #0x10]", CAVE64_SEL + 0x00),   # ориг @0x8670fc
        asm64("adrp x8, #0x23ba000", CAVE64_SEL + 0x04),
        asm64("str x1, [x8, #0x34]", CAVE64_SEL + 0x08),         # FILE_SLOT64 = file
        asm64("b #0x867100", CAVE64_SEL + 0x0C),
    ]), "кейв sel64 (SelectFile пишет слот)")
    old = asm_block64(0x8670FC, [
        "stp x19, x30, [sp, #0x10]",
    ])
    new = asm_block64(0x8670FC, [
        "b #0x%x" % CAVE64_SEL,
    ])
    patch(data, 0x8670FC, old, new, "SelectFile -> слот (хук)")



# ============================================================================
#  ARM32 (armeabi-v7a, режим ARM)
# ============================================================================
CAVE32        = 0x1C6A000  # v3: SZ 0x00, BTC 0x80, MON 0x100, GETCMP 0x140
CAVE32_SUP    = 0x1C6A180  # универсальный Supports
CAVE32_FILE   = 0x1C6A1E4  # selectedFile-слот
FILE_SLOT32_VA = 0x2024270 # RW vaddr (файл 0x2023270, 44 нулевых байта)

def patch_arm32(data):
    print("== armeabi-v7a ==")

    # --- 1a-32. «Неверный размер»: v3-блок FadeText → fileNameText (0x58bb48, 22 инструкции) ---
    old = asm_block32(0x58BB48, [
        "bl #0x4dbd78",                   # Main.get_Instance (v3)
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r5",                     # msg
        "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}",
        "b #0x4ddc14",                    # tail FadeText
    ] + ["nop"] * 15)
    new = asm_block32(0x58BB48, [
        "ldr r0, [r4, #0x1c]",            # fileNameText (arm32: 0x1C)
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, #0", "mov r2, #0",
        "bl #0x1881fd8",                  # bool-check
        "cmp r0, #0",
        "beq #0x58bba4",
        "ldr r0, [r4, #0x1c]",
        "ldr r3, [r0, #0x314]",           # Text.set_text (вирт. слот arm32)
        "ldr r2, [r0, #0x318]",           # method info
        "mov r1, r5",                     # msg
        "blx r3",                         # fileNameText.text = msg
        "b #0x58bba4",                    # pop {.., pc}
    ] + ["nop"] * 8)
    patch(data, 0x58BB48, old, new, "Purchase32: неверный размер -> fileNameText")

    # --- 1b-32. «Не хватает денег»: ориг. tail FadeText → fileNameText (0x58bba8, 11 инструкций) ---
    old = asm_block32(0x58BBA8, [
        "ldr r0, [pc, #0x54]",
        "cmp r6, #0",
        "ldr r0, [pc, r0]",
        "ldr r4, [r0]",
        "bne #0x58bbc0",
        "bl #0x3b54d0",
        "mov r0, r6",
        "mov r1, r4",
        "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}",
        "b #0x4ddc14",
    ])
    new = asm_block32(0x58BBA8, [
        "ldr r0, [pc, #0x54]",            # обёртка литерала «не хватает денег»
        "ldr r0, [pc, r0]",
        "ldr r1, [r0]",                   # msg
        "ldr r0, [r4, #0x1c]",            # fileNameText
        "ldr r3, [r0, #0x314]",           # set_text
        "ldr r2, [r0, #0x318]",
        "blx r3",                         # fileNameText.text = msg
        "pop {r4, r5, r6, r7, r8, sb, sl, pc}",
        "nop", "nop", "nop",
    ])
    patch(data, 0x58BBA8, old, new, "Purchase32: не хватает денег -> fileNameText")

    # --- 2-32. Спавн: всегда bannerPrefab (0x58b9b4, v3-блок 24 инструкции) ---
    old = asm_block32(0x58B9B4, [
        "vmov r0, s16",
        "cmp r0, #0x46",
        "ldreq sb, [r4, #0x28]",
        "ldrne sb, [r4, #0x18]",
        "cmp sb, #0",
        "beq #0x58bba4",
        "mov r0, sb", "mov r1, #0",
        "bl #0x1879ea4",
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r0",
        "mov r0, r6",
        "mov r2, #0",
        "bl #0x4de408",
        "cmp r0, #0",
        "beq #0x58bba4",
        "bl #0x1c6a140",                  # GetComponent<TextureLoader> кейв
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r5",
        "mov r2, r8",
        "mov r3, #0",
        "bl #0x522ad8",
    ])
    new = asm_block32(0x58B9B4, [
        "ldr sb, [r4, #0x18]",            # bannerPrefab — всегда (arm32: 0x18)
        "cmp sb, #0",
        "beq #0x58bba4",
        "mov r0, sb", "mov r1, #0",
        "bl #0x1879ea4",                  # get_gameObject
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r0",                     # префаб GO
        "mov r0, r6",                     # Main.Instance
        "mov r2, #0",
        "bl #0x4de408",                   # InstantDelivery
        "cmp r0, #0",
        "beq #0x58bba4",
        "bl #0x1c6a140",                  # GetComponent<TextureLoader>
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r5",                     # tex
        "mov r2, r8",                     # png
        "mov r3, #0",
        "bl #0x522ad8",                   # SetTexture(loader, tex, png, 0)
    ] + ["nop"] * 3)
    patch(data, 0x58B9B4, old, new, "Purchase32: спавн всегда bannerPrefab")

    # --- 3-32. Универсальный Supports (кейв) ---
    cave(data, CAVE32_SUP, b"".join([
        asm32("ldr r1, [r4, #0x4c]", CAVE32_SUP + 0x00),   # sw
        asm32("mov r7, #1", CAVE32_SUP + 0x04),
        asm32("cmp r1, #1", CAVE32_SUP + 0x08),
        asm32("movle r1, r7", CAVE32_SUP + 0x0C),
        asm32("cmp r0, r1", CAVE32_SUP + 0x10),
        asm32("beq #0x%x" % (CAVE32_SUP + 0x24), CAVE32_SUP + 0x14),    # -> LokW
        asm32("lsl r2, r0, #1", CAVE32_SUP + 0x18),
        asm32("cmp r2, r1", CAVE32_SUP + 0x1C),
        asm32("bne #0x54abec", CAVE32_SUP + 0x20),         # -> false (mov r0,r6=0)
        # LokW:
        asm32("ldr r0, [r5]", CAVE32_SUP + 0x24),
        asm32("ldr r2, [r0, #0xec]", CAVE32_SUP + 0x28),   # get_height
        asm32("ldr r1, [r0, #0xf0]", CAVE32_SUP + 0x2C),
        asm32("mov r0, r5", CAVE32_SUP + 0x30),
        asm32("blx r2", CAVE32_SUP + 0x34),
        asm32("ldr r1, [r4, #0x50]", CAVE32_SUP + 0x38),   # sh
        asm32("mov r7, #1", CAVE32_SUP + 0x3C),
        asm32("cmp r1, #1", CAVE32_SUP + 0x40),
        asm32("movle r1, r7", CAVE32_SUP + 0x44),
        asm32("cmp r0, r1", CAVE32_SUP + 0x48),
        asm32("beq #0x%x" % (CAVE32_SUP + 0x5C), CAVE32_SUP + 0x4C),    # -> LokH
        asm32("lsl r2, r0, #1", CAVE32_SUP + 0x50),
        asm32("cmp r2, r1", CAVE32_SUP + 0x54),
        asm32("bne #0x54abec", CAVE32_SUP + 0x58),
        # LokH:
        asm32("mov r0, #1", CAVE32_SUP + 0x5C),
        asm32("b #0x54abf0", CAVE32_SUP + 0x60),           # -> pop {..,pc}
    ]), "кейв sup32 (универсальный размер)")

    # точка входа: 0x54aba8 (w-блок) -> b кейв
    old = asm_block32(0x54ABA8, [
        "ldr r1, [r4, #0x4c]",
    ])
    new = asm_block32(0x54ABA8, [
        "b #0x%x" % CAVE32_SUP,
    ])
    patch(data, 0x54ABA8, old, new, "Printer.Supports32 -> кейв")

    # --- 4-32. selectedFile-слот: хук Purchase @0x58b7ec -> кейв ---
    # Ориг. 0x58b7e4: ldr r5,[pc,#0x3e8]; 0x58b7ec: add r5,pc,r5 (init-флаг).
    # В кейве повторяем пару с пересчитанным литералом.
    lit_addr = 0x58B7E4 + 8 + 0x3E8                 # пул литерала (0x58bbd4)
    lit_old = int.from_bytes(data[lit_addr:lit_addr + 4], "little")
    r5_target = lit_old + (0x58B7EC + 8)            # значение после add
    lit_new = (r5_target - (CAVE32_FILE + 0x2C + 8)) & 0xFFFFFFFF  # add @0x1c6a210
    cave(data, CAVE32_FILE, b"".join([
        asm32("ldr r0, [r4, #0x30]", CAVE32_FILE + 0x00),          # selectedFile (arm32: 0x30)
        asm32("cmp r0, #0", CAVE32_FILE + 0x04),
        asm32("ldr r1, [pc, #0x24]", CAVE32_FILE + 0x08),          # -> 0x1c6a218 SLOT
        asm32("bne #0x%x" % (CAVE32_FILE + 0x24), CAVE32_FILE + 0x0C),   # -> Lsave
        asm32("ldr r2, [r1]", CAVE32_FILE + 0x10),
        asm32("cmp r2, #0", CAVE32_FILE + 0x14),
        asm32("beq #0x%x" % (CAVE32_FILE + 0x28), CAVE32_FILE + 0x18),   # -> Ldone
        asm32("str r2, [r4, #0x30]", CAVE32_FILE + 0x1C),          # клон: взять
        asm32("b #0x%x" % (CAVE32_FILE + 0x28), CAVE32_FILE + 0x20),     # -> Ldone
        # Lsave:
        asm32("str r0, [r1]", CAVE32_FILE + 0x24),                 # оригинал: запомнить
        # Ldone (ориг. пара 0x58b7ec/0x58b7f0):
        asm32("ldr r5, [pc, #8]", CAVE32_FILE + 0x28),             # -> пул 0x1c6a21c
        asm32("add r5, pc, r5", CAVE32_FILE + 0x2C),
        asm32("b #0x58b7f0", CAVE32_FILE + 0x30),
        FILE_SLOT32_VA.to_bytes(4, "little"),                      # 0x1c6a218: &SLOT
        lit_new.to_bytes(4, "little"),                             # 0x1c6a21c: литерал r5
    ]), "кейв file32 (selectedFile-слот)")
    old = asm_block32(0x58B7EC, [
        "add r5, pc, r5",
    ])
    new = asm_block32(0x58B7EC, [
        "b #0x%x" % CAVE32_FILE,
    ])
    patch(data, 0x58B7EC, old, new, "Purchase32 -> selectedFile-слот (хук)")

    # --- 5-32. SelectFile (0x58b658): сохранить файл в слот ---
    CAVE32_SEL = 0x1C6A220
    cave(data, CAVE32_SEL, b"".join([
        asm32("mov r5, r0", CAVE32_SEL + 0x00),                  # ориг @0x58b660
        asm32("ldr r2, [pc, #8]", CAVE32_SEL + 0x04),            # пул 0x1c6a234
        asm32("str r1, [r2]", CAVE32_SEL + 0x08),                # SLOT32 = file
        asm32("b #0x58b664", CAVE32_SEL + 0x0C),
        asm32("nop", CAVE32_SEL + 0x10),
        FILE_SLOT32_VA.to_bytes(4, "little"),                    # 0x1c6a234: &SLOT
    ]), "кейв sel32 (SelectFile пишет слот)")
    old = asm_block32(0x58B660, [
        "mov r5, r0",
    ])
    new = asm_block32(0x58B660, [
        "b #0x%x" % CAVE32_SEL,
    ])
    patch(data, 0x58B660, old, new, "SelectFile32 -> слот (хук)")


# ============================================================================
if __name__ == "__main__":
    for path, fn in ((SO64, patch_arm64), (SO32, patch_arm32)):
        print(f"--- {path}")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
    print("Готово.")
