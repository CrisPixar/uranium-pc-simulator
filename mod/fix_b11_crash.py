#!/usr/bin/env python3
"""b12 hotfix: краш при заходе в меню (SIGSEGV в libunity, fault 0x49).

Корень: кейв es64/es32 (хук EventSystem.Update) вызывал
Component$$get_transform с GAMEOBJECT от GameObject.Find("Start") —
это разные icall (Component::get_transform vs GameObject::get_transform),
нативный код читал поля GO как будто это Component -> garbage (0x41) -> краш.
Второй баг того же класса: прямоугольник для клик-теста пасхалки читался как
[GO+0x40] (arm64) / [GO+0x20] (arm32) — у GameObject нет таких полей,
RCSP получал мусор (фича мёртвая, при мусоре != 0 — второй краш).

Фикс (не урезает функции, только чинит):
  arm64 @0x85dde4 : bl Component$$get_transform -> bl GameObject$$get_transform
                    (пульс кнопки Start остаётся)
  arm64 @0x85de74..0x85de8c : вместо ldr x21,[x19,#0x40] -> честный
                    GameObject$$get_transform(PM GO) как rect для RCSP
  arm32 @0x1c80a38 : bl -> GameObject$$get_transform (аналог arm64)
  arm32 @0x1c80ac0..0x1c80ac8 : вместо ldr r5,[r4,#0x20] -> вызов
                    GameObject$$get_transform

Идемпотентен: при повторном запуске пропускает уже исправленные сайты.
Запуск: python3 mod/fix_b11_crash.py [дерево]   (по умолчанию /tmp/ups)
"""
import sys, os

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ups"

import capstone
import keystone

ks64 = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
ks32 = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_ARM)
md64 = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
md32 = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)

GO_GETTR64 = 0x17CFC48      # UnityEngine.GameObject$$get_transform (arm64)
RCSP64     = 0x196A1E4      # RectTransformUtility$$RectangleContainsScreenPoint
GO_GETTR32 = 0x187CB9C      # UnityEngine.GameObject$$get_transform (arm32)


def asm64(src, addr):
    enc, _ = ks64.asm(src, addr)
    return bytes(enc)


def asm32(src, addr):
    enc, _ = ks32.asm(src, addr)
    return bytes(enc)


def patch(so, va, old, new, name, log):
    cur = so[va:va + len(new)]
    if cur == new:
        log.append(f"[skip] {name} (уже исправлен)")
        return False
    assert so[va:va + len(old)] == old, (
        f"{name}: неожиданные байты @0x{va:x}: {so[va:va+len(old)].hex()} "
        f"(ожидалось {old.hex()}) — дерево не от b11?")
    so[va:va + len(new)] = new
    log.append(f"[ ok ] {name}: {old.hex()} -> {new.hex()} @0x{va:x}")
    return True


def main():
    p64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
    p32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

    # ---------- arm64 ----------
    so = bytearray(open(p64, "rb").read())
    log = []

    # 1) Start-пульс: Component->GameObject get_transform
    old = asm64("bl #%d" % 0x17CD67C, 0x85DDE4)
    new = asm64("bl #%d" % GO_GETTR64, 0x85DDE4)
    patch(so, 0x85DDE4, old, new, "arm64 Start-пульс GO.get_transform", log)

    # 2) PM-блок: rect = GO.get_transform(PM)
    block_src = [
        "mov x0, x19",
        "bl #%d" % GO_GETTR64,
        "ldr s0, [sp]",
        "ldr s1, [sp, #4]",
        "mov x1, xzr",
        "nop",
        "bl #%d" % RCSP64,
    ]
    new = b"".join(asm64(s, 0x85DE74 + 4 * i) for i, s in enumerate(block_src))
    old = bytes.fromhex(
        "752240f9"   # ldr x21, [x19, #0x40]
        "750800b4"   # cbz x21, #0x85df84
        "e00340bd"   # ldr s0, [sp]
        "e10740bd"   # ldr s1, [sp, #4]
        "e1031faa"   # mov x1, xzr
        "e00315aa"   # mov x0, x21
    ) + asm64("bl #%d" % RCSP64, 0x85DE8C)
    patch(so, 0x85DE74, old, new, "arm64 пасхалка rect через GO.get_transform", log)

    open(p64, "wb").write(bytes(so))
    print("== arm64-v8a ==")
    for l in log:
        print(" ", l)

    # ---------- arm32 ----------
    so = bytearray(open(p32, "rb").read())
    log = []

    # 3) Start-пульс arm32
    old = asm32("bl #%d" % 0x1879E58, 0x1C80A38)
    new = asm32("bl #%d" % GO_GETTR32, 0x1C80A38)
    patch(so, 0x1C80A38, old, new, "arm32 Start-пульс GO.get_transform", log)

    # 4) PM-блок arm32: rect = GO.get_transform(PM)
    new = (asm32("mov r0, r4", 0x1C80AC0)
           + asm32("bl #%d" % GO_GETTR32, 0x1C80AC4)
           + asm32("mov r5, r0", 0x1C80AC8))
    old = bytes.fromhex(
        "205094e5"   # ldr r5, [r4, #0x20]
        "000055e3"   # cmp r5, #0
    ) + asm32("beq #%d" % 0x1C80C14, 0x1C80AC8)
    patch(so, 0x1C80AC0, old, new, "arm32 пасхалка rect через GO.get_transform", log)

    open(p32, "wb").write(bytes(so))
    print("== armeabi-v7a ==")
    for l in log:
        print(" ", l)

    # ---------- верификация ----------
    print("\n== верификация (capstone) ==")
    ok = True
    so64 = open(p64, "rb").read()
    so32 = open(p32, "rb").read()

    def dis64(va, n):
        return list(md64.disasm(so64[va:va + 4 * n], va))

    def dis32(va, n):
        return list(md32.disasm(so32[va:va + 4 * n], va))

    i1 = dis64(0x85DDE4, 1)[0]
    c = (i1.mnemonic == "bl" and i1.op_str == "#0x%x" % GO_GETTR64)
    print(("OK   " if c else "FAIL ") + "arm64 0x85dde4 bl GO.get_transform"); ok = ok and c
    seq = dis64(0x85DE74, 7)
    txt = "; ".join(f"{i.mnemonic} {i.op_str}" for i in seq)
    c = (seq[0].mnemonic == "mov" and seq[1].op_str == "#0x%x" % GO_GETTR64
         and seq[6].op_str == "#0x%x" % RCSP64)
    print(("OK   " if c else "FAIL ") + f"arm64 PM-блок: {txt}"); ok = ok and c
    i3 = dis32(0x1C80A38, 1)[0]
    c = (i3.mnemonic == "bl" and i3.op_str == "#0x%x" % GO_GETTR32)
    print(("OK   " if c else "FAIL ") + "arm32 0x1c80a38 bl GO.get_transform"); ok = ok and c
    seq = dis32(0x1C80AC0, 3)
    txt = "; ".join(f"{i.mnemonic} {i.op_str}" for i in seq)
    c = (seq[0].mnemonic == "mov" and seq[1].op_str == "#0x%x" % GO_GETTR32
         and seq[2].mnemonic == "mov")
    print(("OK   " if c else "FAIL ") + f"arm32 PM-блок: {txt}"); ok = ok and c

    # соседние инструкции не тронуты
    c = dis64(0x85DE90, 1)[0].mnemonic == "cbz"
    print(("OK   " if c else "FAIL ") + "arm64 0x85de90 cbz цел"); ok = ok and c
    c = dis32(0x1C80ACC, 1)[0].mnemonic == "ldr"
    print(("OK   " if c else "FAIL ") + "arm32 0x1c80acc ldr цел"); ok = ok and c

    print("\nИТОГ:", "ВСЁ ОК" if ok else "ЕСТЬ ОШИБКИ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
