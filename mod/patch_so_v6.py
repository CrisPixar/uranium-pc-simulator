#!/usr/bin/env python3
"""Патчи libil2cpp.so v6 (b9) — поверх v5 (b8).

1. КРАШ-ФИКС (главное): мод-B2 (v4, «спавн через InstantDelivery + GetComponent
   на мусорном поле +0x54») в PrintExpert.Purchase ЗАМЕНЁН на ОРИГИНАЛЬНЫЙ
   авторский блок 1:1 (arm64 0x867394..0x8673f8, arm32 0x58b9b4..0x58ba74),
   байты взяты из оригинального .so. Оригинал:
     Instantiate(bannerPrefab, mi) -> GetComponent<TextureLoader> ->
     Main.InstantDelivery(go) -> TextureLoader.SetTexture(tex, png).
2. cave2 (выбор рамки по ширине, БЕЗ изменения B2):
   arm64 0x867384 (ldr x23,[x19,#0x30]) -> кейв 0x85DC00:
     s9==70 -> x23=[x19,#0x50] (горизонтальная рамка), иначе [x19,#0x30].
   arm32 0x58b9b8 (ldr sb,[r4,#0x18]) -> кейв 0x1C6A280 (s16==70 -> +0x28).
3. Supports-кейв ПЕРЕПИСАН: кратность в ОБЕ стороны —
     w==sw || 2w==sw || 4w==sw || 8w==sw || 2sw==w || 4sw==w || 8sw==w
   (и для h). Прежний кейв проверял только w*k==sw (картинка МЕНЬШЕ),
   поэтому 512 на 128-принтере отвергался. Теперь 128-принтер печатает
   16..128..1024 (кратные стороны).
   arm64 кейв 0x85DAE0 (216 Б), arm32 кейв 0x1C6A180 (228 Б).
"""
import sys, os
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KS_ARCH_ARM, KS_MODE_ARM

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")
ORIG64 = "/tmp/orig64.so"
ORIG32 = "/tmp/orig32.so"

ks64 = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
ks32 = Ks(KS_ARCH_ARM, KS_MODE_ARM)

def asm64(code, addr):
    enc, _ = ks64.asm(code, addr); return bytes(enc)
def asm32(code, addr):
    enc, _ = ks32.asm(code, addr); return bytes(enc)

def patch(data, va, old, new, what):
    cur = data[va:va + len(old)]
    if cur == new:
        print(f"  [skip] {what} @0x{va:x}"); return
    if cur != old:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось {old.hex(' ')}, найдено {cur.hex(' ')}")
    assert len(new) == len(old)
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x}")

def cave(data, va, old_expect, new, what):
    """Запись кейва: old_expect=None -> только нули; иначе сверка со старым кейвом."""
    cur = data[va:va + len(new)]
    if cur == new:
        print(f"  [skip] {what} @0x{va:x}"); return
    if old_expect is not None:
        if cur == old_expect:
            data[va:va + len(new)] = new
            print(f"  [ ok ] {what} @0x{va:x} ({len(new)}Б, замена старого кейва)")
            return
        raise RuntimeError(f"{what} @0x{va:x}: кейв не старый и не новый: {cur[:16].hex(' ')}...")
    if cur != b"\x00" * len(new):
        raise RuntimeError(f"{what} @0x{va:x}: место не пусто: {cur[:16].hex(' ')}...")
    data[va:va + len(new)] = new
    print(f"  [ ok ] {what} @0x{va:x} ({len(new)}Б)")

def asm_blob(instrs, base, asm, arm32=False):
    labels = {}
    addr = base
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
        blob += asm(ln, a)
    return blob

# ============================================================================
CAVE64_SUP = 0x85DAE0   # старый sup64 (144Б) -> новый (216Б), дальше нули до 0x85e96c
CAVE64_C2  = 0x85DC00   # чистые нули
CAVE32_SUP = 0x1C6A180  # старый sup32 (160Б) -> новый (228Б), дальше нули до 0x1c6a62c
CAVE32_C2  = 0x1C6A280  # чистые нули (после нового sup32, до 0x1c6a62c)

# --- оригинальные B2-блоки (из оригинального .so) ---
with open(ORIG64, "rb") as f:
    ORIG_B2_64 = f.read()[0x867394:0x8673F8]      # 100 Б
with open(ORIG32, "rb") as f:
    ORIG_B2_32 = f.read()[0x58B9B4:0x58BA74]      # 192 Б

def patch_arm64(data):
    print("== arm64-v8a ==")
    # 1. B2 -> оригинал 1:1
    with open(SO64, "rb") as f:
        cur = f.read()[0x867394:0x8673F8]
    patch(data, 0x867394, cur, ORIG_B2_64, "Purchase B2 -> оригинальный авторский блок")

    # 2. cave2: выбор рамки по ширине (s9 = width, сохранён кейвом sz)
    old = asm64("ldr x23, [x19, #0x30]", 0x867384)
    new = asm64("b #0x%x" % CAVE64_C2, 0x867384)
    patch(data, 0x867384, old, new, "Purchase: выбор префаба -> cave2")

    c2 = asm_blob([
        "fmov w8, s9",              # w8 = ширина
        "cmp w8, #0x46",            # 70?
        "b.eq #Lhor",
        "ldr x23, [x19, #0x30]",    # bannerPrefab (вертикальная)
        "b #0x867388",
        "Lhor:",
        "ldr x23, [x19, #0x50]",    # alertText-слот = горизонтальная рамка
        "b #0x867388",
    ], CAVE64_C2, asm64)
    cave(data, CAVE64_C2, None, c2, "кейв cave2-64 (рамка по ширине)")

    # 3. sup-кейв: кратность в обе стороны
    sup = asm_blob([
        "ldr w8, [x19, #0x74]", "cmp w8, #1", "csinc w8, w8, wzr, gt",   # sw
        "cmp w0, w8", "b.eq #LokW",
        "lsl w10, w0, #1", "cmp w10, w8", "b.eq #LokW",    # 2w==sw
        "lsl w10, w0, #2", "cmp w10, w8", "b.eq #LokW",    # 4w==sw
        "lsl w10, w0, #3", "cmp w10, w8", "b.eq #LokW",    # 8w==sw
        "lsl w10, w8, #1", "cmp w10, w0", "b.eq #LokW",    # 2sw==w
        "lsl w10, w8, #2", "cmp w10, w0", "b.eq #LokW",    # 4sw==w
        "lsl w10, w8, #3", "cmp w10, w0", "b.ne #Lfalse",  # 8sw==w
        "LokW:",
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x198]", "blr x9",   # get_height
        "ldr w8, [x19, #0x78]", "cmp w8, #1", "csinc w8, w8, wzr, gt",          # sh
        "cmp w0, w8", "b.eq #LokH",
        "lsl w10, w0, #1", "cmp w10, w8", "b.eq #LokH",
        "lsl w10, w0, #2", "cmp w10, w8", "b.eq #LokH",
        "lsl w10, w0, #3", "cmp w10, w8", "b.eq #LokH",
        "lsl w10, w8, #1", "cmp w10, w0", "b.eq #LokH",
        "lsl w10, w8, #2", "cmp w10, w0", "b.eq #LokH",
        "lsl w10, w8, #3", "cmp w10, w0", "b.ne #Lfalse",
        "LokH:", "mov w0, #1", "b #Lend",
        "Lfalse:", "mov w0, wzr",
        "Lend:", "b #0x834f34",
    ], CAVE64_SUP, asm64)
    # старый sup64 = текущий кейв v5 (первые байты ldr w8,[x19,#0x74])
    with open(SO64, "rb") as f:
        old_sup = f.read()[CAVE64_SUP:CAVE64_SUP + len(sup)]
    cave(data, CAVE64_SUP, old_sup, sup, "кейв sup64 (кратность в обе стороны)")

def patch_arm32(data):
    print("== armeabi-v7a ==")
    # 1. B2 -> оригинал 1:1
    with open(SO32, "rb") as f:
        cur = f.read()[0x58B9B4:0x58BA74]
    patch(data, 0x58B9B4, cur, ORIG_B2_32, "Purchase32 B2 -> оригинальный авторский блок")

    # 2. cave2-32 (ПОСЛЕ восстановления B2: 0x58b9b8 = ldr sb,[r4,#0x18])
    old = asm32("ldr sb, [r4, #0x18]", 0x58B9B8)
    new = asm32("b #0x%x" % CAVE32_C2, 0x58B9B8)
    patch(data, 0x58B9B8, old, new, "Purchase32: выбор префаба -> cave2")

    c2 = asm_blob([
        "vmov r0, s16",             # ширина
        "cmp r0, #0x46",            # 70?
        "ldreq sb, [r4, #0x28]",    # alertText-слот = горизонтальная рамка
        "ldrne sb, [r4, #0x18]",    # bannerPrefab (вертикальная)
        "b #0x58b9bc",
    ], CAVE32_C2, asm32)
    cave(data, CAVE32_C2, None, c2, "кейв cave2-32 (рамка по ширине)")

    # 3. sup-кейв 32
    sup = asm_blob([
        "ldr r1, [r4, #0x4c]", "mov r7, #1", "cmp r1, #1", "movle r1, r7",   # sw
        "cmp r0, r1", "beq #LokW",
        "lsl r2, r0, #1", "cmp r2, r1", "beq #LokW",
        "lsl r2, r0, #2", "cmp r2, r1", "beq #LokW",
        "lsl r2, r0, #3", "cmp r2, r1", "beq #LokW",
        "lsl r2, r1, #1", "cmp r2, r0", "beq #LokW",
        "lsl r2, r1, #2", "cmp r2, r0", "beq #LokW",
        "lsl r2, r1, #3", "cmp r2, r0", "bne #Lfalse",
        "LokW:",
        "ldr r0, [r5]", "ldr r2, [r0, #0xec]", "ldr r1, [r0, #0xf0]",
        "mov r0, r5", "blx r2",                                            # get_height
        "ldr r1, [r4, #0x50]", "mov r7, #1", "cmp r1, #1", "movle r1, r7", # sh
        "cmp r0, r1", "beq #LokH",
        "lsl r2, r0, #1", "cmp r2, r1", "beq #LokH",
        "lsl r2, r0, #2", "cmp r2, r1", "beq #LokH",
        "lsl r2, r0, #3", "cmp r2, r1", "beq #LokH",
        "lsl r2, r1, #1", "cmp r2, r0", "beq #LokH",
        "lsl r2, r1, #2", "cmp r2, r0", "beq #LokH",
        "lsl r2, r1, #3", "cmp r2, r0", "bne #Lfalse",
        "LokH:", "mov r0, #1", "b #Lend",
        "Lfalse:", "mov r0, #0",
        "Lend:", "b #0x54abf0",
    ], CAVE32_SUP, asm32)
    with open(SO32, "rb") as f:
        old_sup = f.read()[CAVE32_SUP:CAVE32_SUP + len(sup)]
    cave(data, CAVE32_SUP, old_sup, sup, "кейв sup32 (кратность в обе стороны)")

if __name__ == "__main__":
    for path, fn in ((SO64, patch_arm64), (SO32, patch_arm32)):
        print(f"--- {path}")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
    print("Готово.")
