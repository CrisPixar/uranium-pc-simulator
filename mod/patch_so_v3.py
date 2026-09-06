#!/usr/bin/env python3
"""Патчи libil2cpp.so v3 для мода Uranium PC Simulator (arm64-v8a + armeabi-v7a).

Требования v3:
  A. Бесплатные покупки в песочнице:
     - BTC-разблокировки товаров (ShopUI.ButtonDown): в sandbox цена считается 0,
       кошелёк BTC не меняется (вычитается 0), предмет разблокируется.
     - Сайт PrintExpert: проверка "Money <= 199" в sandbox всегда проходит
       (cave-обёртка над get_Money возвращает INT_MAX), а Main.Spend в sandbox
       и так не списывает (штатное поведение игры).
  B. Сайт PrintExpert:
     - Принимает картинки 32x70 (вертикальный баннер) И 70x32 (горизонтальный).
     - Горизонтальная картинка -> префаб из поля alertText (переназначен в
       данных бандла на TextureLoader префаба BannerStand_H), вертикальная ->
       bannerPrefab.
     - Исправлен двойной спавн: раньше Instantiate(копия#1) + InstantDelivery
       (копия#2, БЕЛАЯ) + SetTexture(копия#1). Теперь InstantDelivery(prefab)
       -> единственная копия, SetTexture на ней.
     - Сообщение о неверном размере выводится через Main.FadeText (alertText
       больше не используется как Text).
  C. Код-кейвы: arm64 0x85D978.., arm32 0x1C6A000.. (выровнено, нулевой паддинг).

Каждый патч проверяет оригинальные байты (защита от двойного применения:
если байты уже равны новым -- пропуск).
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
    """Собрать блок: каждая строка -- инструкция на своём адресе (важно для PC-относительных)."""
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
CAVE64     = 0x85D978   # нулевой паддинг 0x85d978..0x85e96c (0xff4)
CAVE64_SZ  = CAVE64          # проверка размера картинки
CAVE64_BTC = CAVE64 + 0x40   # BTC-разблокировка в sandbox
CAVE64_MON = CAVE64 + 0x90   # get_Money-обёртка для сайта

def patch_arm64(data):
    print("== arm64-v8a ==")

    # --- A1. Кейв: проверка размера (32x70 или 70x32), сохранить ширину в s9 ---
    cave(data, CAVE64_SZ, b"".join([
        asm64("fmov s9, w22", CAVE64_SZ + 0x00),
        asm64("cmp w22, #0x20", CAVE64_SZ + 0x04),
        asm64("b.ne #0x%x" % (CAVE64_SZ + 0x14), CAVE64_SZ + 0x08),
        asm64("cmp w0, #0x46", CAVE64_SZ + 0x0C),
        asm64("b.eq #0x%x" % (CAVE64_SZ + 0x28), CAVE64_SZ + 0x10),  # -> Lok
        asm64("cmp w22, #0x46", CAVE64_SZ + 0x14),          # Lw:
        asm64("b.ne #0x%x" % (CAVE64_SZ + 0x24), CAVE64_SZ + 0x18),  # -> Lfail
        asm64("cmp w0, #0x20", CAVE64_SZ + 0x1C),
        asm64("b.eq #0x%x" % (CAVE64_SZ + 0x28), CAVE64_SZ + 0x20),  # -> Lok
        asm64("b #0x867480", CAVE64_SZ + 0x24),             # Lfail: неверный размер
        asm64("b #0x8672d4", CAVE64_SZ + 0x28),             # Lok: дальше (деньги)
    ]), "кейв sz64 (32x70 | 70x32)")

    # --- B1. Purchase: блок проверки размера (0x8672a4, 12 инструкций) ---
    old = asm_block64(0x8672A4, [
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x178]", "blr x9",
        "cmp w0, #0x20", "b.ne #0x867480",
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x198]", "blr x9",
        "cmp w0, #0x46", "b.ne #0x867480",
    ])
    new = asm_block64(0x8672A4, [
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x178]", "blr x9",
        "mov w22, w0",                                   # w22 = ширина
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x198]", "blr x9",
        "b #0x%x" % CAVE64_SZ, "nop", "nop",
    ])
    patch(data, 0x8672A4, old, new, "Purchase: проверка размера -> кейв")

    # --- B2. Purchase: блок спавна (0x867394, 25 инструкций) ---
    old = asm_block64(0x867394, [
        "ldr x1, [x25]", "mov x0, x23", "bl #0x8fb81c", "cbz x0, #0x867544",
        "adrp x8, #0x224a000", "ldr x8, [x8, #0x9b8]", "ldr x1, [x8]",
        "bl #0x8ccd94", "cbz x0, #0x867544",
        "mov x1, xzr", "mov x23, x0", "bl #0x17cd6b8", "mov x1, x0",
        "mov x0, x21", "mov x2, xzr", "bl #0x7e2a00",
        "mov x1, xzr", "mov x2, xzr", "bl #0x17d2cbc", "tbnz w0, #0, #0x867508",
        "mov x0, x23", "mov x1, x20", "mov x2, x22", "mov x3, xzr", "bl #0x816ec8",
    ])
    new = asm_block64(0x867394, [
        "fmov w23, s9",                   # w23 = ширина
        "cmp w23, #0x46",
        "b.ne #0x%x" % (0x867394 + 0x14), # -> вертикальный (ldr на +0x14)
        "ldr x23, [x19, #0x50]",          # alertText -> горизонтальный TextureLoader
        "b #0x%x" % (0x867394 + 0x18),    # -> mov x0, x23 (+0x18)
        "ldr x23, [x19, #0x30]",          # bannerPrefab -> вертикальный TextureLoader
        "mov x0, x23",
        "bl #0x17cd6b8",                  # get_gameObject(prefab) -> x0
        "mov x1, x0",
        "mov x0, x21",                    # Main.Instance
        "mov x2, xzr",
        "bl #0x7e2a00",                   # InstantDelivery(prefabGO) -> x0 (единственная копия)
        "cbz x0, #0x867544",
        "mov x23, x0",                    # доставленный GO
        "adrp x8, #0x224a000",
        "ldr x8, [x8, #0x9b8]",
        "ldr x1, [x8]",                   # класс TextureLoader
        "mov x0, x23",
        "bl #0x8ccd94",                   # GetComponent -> x0
        "mov x23, x0",
        "mov x0, x23",
        "mov x1, x20",                    # tex
        "mov x2, x22",                    # png
        "mov x3, xzr",
        "bl #0x816ec8",                   # SetTexture(loader, tex, png, 0)
    ])
    patch(data, 0x867394, old, new, "Purchase: спавн (один баннер, выбор по ширине)")

    # --- B3. Purchase: путь неверного размера -> Main.FadeText (0x8674ac, 23 инструкции) ---
    old = asm_block64(0x8674AC, [
        "ldr x8, [x24]", "ldr x21, [x19, #0x50]", "mov x20, x0",
        "ldr w9, [x8, #0xe0]", "cbnz w9, #0x8674c8", "mov x0, x8", "bl #0x6b27d8",
        "mov x0, x21", "mov x1, xzr", "mov x2, xzr", "bl #0x17d3c10",
        "tbz w0, #0, #0x867508",
        "ldr x0, [x19, #0x50]", "cbz x0, #0x867544", "ldr x8, [x0]", "mov x1, x20",
        "ldp x19, x30, [sp, #0x30]", "ldp x21, x20, [sp, #0x20]",
        "ldr x3, [x8, #0x5e8]", "ldr x2, [x8, #0x5f0]",
        "ldp x23, x22, [sp, #0x10]", "ldp x25, x24, [sp], #0x40", "br x3",
    ])
    new = asm_block64(0x8674AC, [
        "mov x20, x0",                    # msg
        "bl #0x7e0c50",                   # Main.get_Instance
        "cbz x0, #0x867508",
        "mov x1, x20", "mov x2, xzr",
        "b #0x7e23b8",                    # tail: Main.FadeText(msg)
    ] + ["nop"] * 17)
    patch(data, 0x8674AC, old, new, "Purchase: неверный размер -> Main.FadeText")

    # --- A2. Кейв BTC-разблокировки (sandbox: цена 0) ---
    cave(data, CAVE64_BTC, b"".join([
        asm64("fmov s8, s0", CAVE64_BTC + 0x00),           # сохранить текущий BTC
        asm64("bl #0x7e0c50", CAVE64_BTC + 0x04),          # Main.get_Instance
        asm64("cbz x0, #0x%x" % (CAVE64_BTC + 0x24), CAVE64_BTC + 0x08),
        asm64("ldrb w8, [x0, #0x3a]", CAVE64_BTC + 0x0C),  # Main.sandbox
        asm64("cbz w8, #0x%x" % (CAVE64_BTC + 0x24), CAVE64_BTC + 0x10),
        asm64("fmov s0, s8", CAVE64_BTC + 0x14),
        asm64("fmov s1, wzr", CAVE64_BTC + 0x18),          # цена = 0
        asm64("fcmp s1, s0", CAVE64_BTC + 0x1C),
        asm64("b.ls #0x829728", CAVE64_BTC + 0x20),        # -> разблокировка
        asm64("b #0x829674", CAVE64_BTC + 0x24),           # -> "не хватает"
        asm64("fmov s0, s8", CAVE64_BTC + 0x28),           # Lorig:
        asm64("ldr s1, [x20, #0x24]", CAVE64_BTC + 0x2C),
        asm64("fcmp s1, s0", CAVE64_BTC + 0x30),
        asm64("b.ls #0x829728", CAVE64_BTC + 0x34),
        asm64("b #0x829674", CAVE64_BTC + 0x38),
    ]), "кейв btc64 (sandbox: BTC-цена 0)")

    # --- A3. ButtonDown: проверка BTC через кейв (0x829668, 3 инструкции) ---
    old = asm_block64(0x829668, [
        "ldr s1, [x20, #0x24]", "fcmp s1, s0", "b.ls #0x829728",
    ])
    new = asm_block64(0x829668, [
        "b #0x%x" % CAVE64_BTC, "nop", "nop",
    ])
    patch(data, 0x829668, old, new, "ButtonDown: BTC-проверка -> кейв")

    # --- A4. Кейв get_Money для сайта (sandbox: INT_MAX) ---
    # Вызывается через bl -- сохраняем LR (внутри есть вызов get_Money).
    cave(data, CAVE64_MON, b"".join([
        asm64("str x30, [sp, #-0x10]!", CAVE64_MON + 0x00),
        asm64("bl #0x7e0ce4", CAVE64_MON + 0x04),          # get_Money(x0=x21)
        asm64("ldrb w8, [x21, #0x3a]", CAVE64_MON + 0x08), # Main.sandbox (x21 сохранён)
        asm64("cbz w8, #0x%x" % (CAVE64_MON + 0x1C), CAVE64_MON + 0x0C),
        asm64("movz w0, #0x7fff", CAVE64_MON + 0x10),
        asm64("movk w0, #0x7fff, lsl #16", CAVE64_MON + 0x14),
        asm64("ldr x30, [sp], #0x10", CAVE64_MON + 0x18),
        asm64("ret", CAVE64_MON + 0x1C),                   # Lret
    ]), "кейв money64 (sandbox: денег хватает)")

    # --- A5. Purchase: вызов get_Money -> кейв (0x867338) ---
    old = asm64("bl #0x7e0ce4", 0x867338)
    new = asm64("bl #0x%x" % CAVE64_MON, 0x867338)
    patch(data, 0x867338, old, new, "Purchase: get_Money -> кейв (sandbox)")

# ============================================================================
#  ARM32 (armeabi-v7a, режим ARM)
# ============================================================================
CAVE32        = 0x1C6A000  # выровнено внутри нулевого паддинга 0x1c69ffd..0x1c6a62c
CAVE32_SZ     = CAVE32
CAVE32_BTC    = CAVE32 + 0x80
CAVE32_MON    = CAVE32 + 0x100
CAVE32_GETCMP = CAVE32 + 0x140

# Цепочка класса TextureLoader в arm32 Purchase (разыменовывается из оригинала):
# 0x58b9f0: ldr r0,[pc,#0x214] -> lit@0x58bc0c = V1; L1 = 0x58b9f4+8+V1; [L1] -> &(кэш класса)
def texloader_slot32(data):
    import struct
    V1 = struct.unpack_from("<I", data, 0x58BC0C)[0]
    L1 = 0x58B9F4 + 8 + V1
    return L1

def patch_arm32(data):
    print("== armeabi-v7a ==")
    L1 = texloader_slot32(data)

    # --- A1. Кейв: проверка размера ---
    cave(data, CAVE32_SZ, b"".join([
        asm32("vmov r8, s16", CAVE32_SZ + 0x00),           # r8 = ширина
        asm32("cmp r8, #0x20", CAVE32_SZ + 0x04),
        asm32("bne #0x%x" % (CAVE32_SZ + 0x14), CAVE32_SZ + 0x08),
        asm32("cmp r0, #0x46", CAVE32_SZ + 0x0C),
        asm32("beq #0x%x" % (CAVE32_SZ + 0x28), CAVE32_SZ + 0x10),   # -> Lok
        asm32("cmp r8, #0x46", CAVE32_SZ + 0x14),          # Lw:
        asm32("bne #0x%x" % (CAVE32_SZ + 0x24), CAVE32_SZ + 0x18),   # -> Lfail
        asm32("cmp r0, #0x20", CAVE32_SZ + 0x1C),
        asm32("beq #0x%x" % (CAVE32_SZ + 0x28), CAVE32_SZ + 0x20),   # -> Lok
        asm32("b #0x58bb18", CAVE32_SZ + 0x24),            # Lfail
        asm32("b #0x58b8ec", CAVE32_SZ + 0x28),            # Lok
    ]), "кейв sz32 (32x70 | 70x32)")

    # --- B1. Purchase: блок проверки размера (0x58b8b4, 15 инструкций) ---
    old = asm_block32(0x58B8B4, [
        "ldr r0, [r5]", "ldr r2, [r0, #0xdc]", "ldr r1, [r0, #0xe0]",
        "mov r0, r5", "blx r2", "cmp r0, #0x20", "bne #0x58bb18",
        "ldr r0, [r5]", "ldr r2, [r0, #0xec]", "ldr r1, [r0, #0xf0]",
        "mov r0, r5", "blx r2", "cmp r0, #0x46", "bne #0x58bb18",
    ])
    new = asm_block32(0x58B8B4, [
        "ldr r0, [r5]", "ldr r2, [r0, #0xdc]", "ldr r1, [r0, #0xe0]",
        "mov r0, r5", "blx r2",
        "vmov s16, r0",                                   # s16 = ширина (сохранится через вызовы)
        "ldr r0, [r5]", "ldr r2, [r0, #0xec]", "ldr r1, [r0, #0xf0]",
        "mov r0, r5", "blx r2",
        "b #0x%x" % CAVE32_SZ, "nop", "nop",
    ])
    patch(data, 0x58B8B4, old, new, "Purchase: проверка размера -> кейв")

    # --- B2. Purchase: блок спавна (0x58b9b4, 48 инструкций) ---
    old = asm_block32(0x58B9B4, [
        "ldr r0, [r7]", "ldr sb, [r4, #0x18]",
        "ldr r1, [r0, #0x74]", "cmp r1, #0", "bne #0x58b9cc", "bl #0x3b54b0",
        "ldr r0, [pc, #0x234]", "ldr r0, [pc, r0]", "ldr r1, [r0]",
        "mov r0, sb", "bl #0x636a74",
        "mov sb, r0", "cmp r0, #0", "bne #0x58b9f0", "bl #0x3b54d0",
        "ldr r0, [pc, #0x214]", "ldr r0, [pc, r0]", "ldr r1, [r0]",
        "mov r0, sb", "bl #0x5ffe4c",
        "mov sb, r0", "cmp r0, #0", "bne #0x58ba14", "bl #0x3b54d0",
        "mov r0, sb", "mov r1, #0", "bl #0x1879ea4", "mov sl, r0",
        "cmp r6, #0", "bne #0x58ba30", "bl #0x3b54d0",
        "mov r0, r6", "mov r1, sl", "mov r2, #0", "bl #0x4de408",
        "mov r1, #0", "mov r2, #0", "bl #0x1880938",
        "cmp r0, #0", "bne #0x58bba4",
        "cmp sb, #0", "bne #0x58ba60", "bl #0x3b54d0",
        "mov r0, sb", "mov r1, r5", "mov r2, r8", "mov r3, #0", "bl #0x522ad8",
    ])
    new = asm_block32(0x58B9B4, [
        "vmov r0, s16",                   # r0 = ширина
        "cmp r0, #0x46",
        "ldreq sb, [r4, #0x28]",          # alertText -> горизонтальный TextureLoader
        "ldrne sb, [r4, #0x18]",          # bannerPrefab -> вертикальный TextureLoader
        "cmp sb, #0",
        "beq #0x58bba4",
        "mov r0, sb", "mov r1, #0",
        "bl #0x1879ea4",                  # get_gameObject(prefab) -> r0
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r0",                     # префаб GO
        "mov r0, r6",                     # Main.Instance
        "mov r2, #0",
        "bl #0x4de408",                   # InstantDelivery -> r0 (единственная копия)
        "cmp r0, #0",
        "beq #0x58bba4",
        "bl #0x%x" % CAVE32_GETCMP,       # GetComponent<TextureLoader>(delivered) -> r0
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r5",                     # tex
        "mov r2, r8",                     # png
        "mov r3, #0",
        "bl #0x522ad8",                   # SetTexture(loader, tex, png, 0)
    ] + ["nop"] * 24)
    patch(data, 0x58B9B4, old, new, "Purchase: спавн (один баннер, выбор по ширине)")

    # --- B3. Purchase: путь неверного размера -> Main.FadeText (0x58bb48, 22 инструкции) ---
    old = asm_block32(0x58BB48, [
        "ldr r0, [r7]", "ldr r6, [r4, #0x28]",
        "ldr r1, [r0, #0x74]", "cmp r1, #0", "bne #0x58bb60", "bl #0x3b54b0",
        "mov r0, r6", "mov r1, #0", "mov r2, #0", "bl #0x1881fd8",
        "cmp r0, #0", "beq #0x58bba4",
        "ldr r4, [r4, #0x28]", "cmp r4, #0", "bne #0x58bb88", "bl #0x3b54d0",
        "ldr r0, [r4]", "mov r1, r5",
        "ldr r3, [r0, #0x314]", "ldr r2, [r0, #0x318]", "mov r0, r4",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}", "bx r3",
    ])
    new = asm_block32(0x58BB48, [
        "bl #0x4dbd78",                   # Main.get_Instance
        "cmp r0, #0",
        "beq #0x58bba4",
        "mov r1, r5",                     # msg
        "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}",
        "b #0x4ddc14",                    # tail: Main.FadeText(msg)
    ] + ["nop"] * 16)
    patch(data, 0x58BB48, old, new, "Purchase: неверный размер -> Main.FadeText")

    # --- A2. Кейв BTC-разблокировки ---
    cave(data, CAVE32_BTC, b"".join([
        asm32("vmov.f32 s16, s0", CAVE32_BTC + 0x00),
        asm32("vmov.f32 s17, s2", CAVE32_BTC + 0x04),
        asm32("bl #0x4dbd78", CAVE32_BTC + 0x08),          # Main.get_Instance
        asm32("cmp r0, #0", CAVE32_BTC + 0x0C),
        asm32("beq #0x%x" % (CAVE32_BTC + 0x38), CAVE32_BTC + 0x10),
        asm32("ldrb r1, [r0, #0x1e]", CAVE32_BTC + 0x14),  # Main.sandbox
        asm32("cmp r1, #0", CAVE32_BTC + 0x18),
        asm32("beq #0x%x" % (CAVE32_BTC + 0x38), CAVE32_BTC + 0x1C),
        asm32("vmov.f32 s0, s16", CAVE32_BTC + 0x20),
        asm32("mov r1, #0", CAVE32_BTC + 0x24),
        asm32("vmov s2, r1", CAVE32_BTC + 0x28),           # цена = 0
        asm32("vcmpe.f32 s2, s0", CAVE32_BTC + 0x2C),
        asm32("vmrs apsr_nzcv, fpscr", CAVE32_BTC + 0x30),
        asm32("bls #0x53bba4", CAVE32_BTC + 0x34),         # -> разблокировка
        asm32("b #0x53badc", CAVE32_BTC + 0x38),           # -> "не хватает"
        asm32("vmov.f32 s0, s16", CAVE32_BTC + 0x3C),      # Lorig:
        asm32("vmov.f32 s2, s17", CAVE32_BTC + 0x40),
        asm32("vcmpe.f32 s2, s0", CAVE32_BTC + 0x44),
        asm32("vmrs apsr_nzcv, fpscr", CAVE32_BTC + 0x48),
        asm32("bls #0x53bba4", CAVE32_BTC + 0x4C),
        asm32("b #0x53badc", CAVE32_BTC + 0x50),
    ]), "кейв btc32 (sandbox: BTC-цена 0)")

    # --- A3. ButtonDown: проверка BTC через кейв (0x53bad0, 3 инструкции) ---
    old = asm_block32(0x53BAD0, [
        "vcmpe.f32 s2, s0", "vmrs apsr_nzcv, fpscr", "bls #0x53bba4",
    ])
    new = asm_block32(0x53BAD0, [
        "b #0x%x" % CAVE32_BTC, "nop", "nop",
    ])
    patch(data, 0x53BAD0, old, new, "ButtonDown: BTC-проверка -> кейв")

    # --- A4. Кейв get_Money для сайта ---
    # Вызывается через bl -- сохраняем LR (внутри есть вызов get_Money).
    cave(data, CAVE32_MON, b"".join([
        asm32("push {r4, lr}", CAVE32_MON + 0x00),
        asm32("bl #0x4dbe1c", CAVE32_MON + 0x04),          # get_Money(r6)
        asm32("ldrb r1, [r6, #0x1e]", CAVE32_MON + 0x08),  # Main.sandbox
        asm32("cmp r1, #0", CAVE32_MON + 0x0C),
        asm32("beq #0x%x" % (CAVE32_MON + 0x1C), CAVE32_MON + 0x10),
        asm32("movw r0, #0x7fff", CAVE32_MON + 0x14),
        asm32("movt r0, #0x7fff", CAVE32_MON + 0x18),
        asm32("pop {r4, pc}", CAVE32_MON + 0x1C),          # Lret
    ]), "кейв money32 (sandbox: денег хватает)")

    # --- A5. Purchase: вызов get_Money -> кейв (0x58b968) ---
    old = asm32("bl #0x4dbe1c", 0x58B968)
    new = asm32("bl #0x%x" % CAVE32_MON, 0x58B968)
    patch(data, 0x58B968, old, new, "Purchase: get_Money -> кейв (sandbox)")

    # --- B4. Кейв GetComponent<TextureLoader> (класс из цепочки оригинала) ---
    G = CAVE32_GETCMP
    D1 = L1 - (G + 0x10)
    lit = D1.to_bytes(4, "little")
    cave(data, G, b"".join([
        asm32("mov r12, r0", G + 0x00),
        asm32("ldr r1, [pc, #0x14]", G + 0x04),            # литерал D1 @ G+0x20
        asm32("ldr r1, [pc, r1]", G + 0x08),               # r1 = [L1] = &(кэш класса)
        asm32("ldr r1, [r1]", G + 0x0C),                   # r1 = класс TextureLoader
        asm32("mov r0, r12", G + 0x10),
        asm32("b #0x5ffe4c", G + 0x14),                    # tail GetComponent(obj, class)
        asm32("nop", G + 0x18),
        asm32("nop", G + 0x1C),
    ]) + lit, "кейв getcomp32 (класс TextureLoader)")

# ============================================================================
if __name__ == "__main__":
    for path, fn in ((SO64, patch_arm64), (SO32, patch_arm32)):
        data = bytearray(open(path, "rb").read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
        print(f"  записано: {path} ({len(data):,} байт)")
    print("ПАТЧИ v3 ПРИМЕНЕНЫ.")
