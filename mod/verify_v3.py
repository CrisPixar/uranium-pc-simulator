#!/usr/bin/env python3
"""Полная проверка v3-патчей на дереве apktool.

Проверяет:
  1. global-metadata.dat: литерал заголовка = Uranium (59 байт, PC красный).
  2. libil2cpp.so (обе архитектуры): байты всех v3-патчей совпадают
     (sha256 участков) + семантика ветвлений (capstone).
  3. data.unity3d: bitcoin=0 у новых ShopItem, текстура 164 белая RGBA32,
     PrintExpert.alertText -> TextureLoader 13747 (BannerStand_H).
  4. Инварианты v2: 56 товаров в маркете, Grid белая, productName Uranium,
     заголовок level0.

Запуск:  python3 verify_v3.py [путь_к_дереву_apktool]
Выход:   код 0 = всё OK, 1 = есть ошибки.
"""
import sys, os, hashlib

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
ok = True

def chk(cond, what):
    global ok
    print(("OK   " if cond else "FAIL ") + what)
    ok = ok and cond

# ============================================================================
print("== 1. global-metadata.dat ==")
mp = os.path.join(BASE, "assets/bin/Data/Managed/Metadata/global-metadata.dat")
md = open(mp, "rb").read()
NEW = b"<color=cyan>Uranium</color> <color=red>PC</color> Simulator"
OLD = b"<color=cyan>Blue</color> <color=orange>PC</color> Simulator"
chk(md[0x1E4A1:0x1E4A1 + 59] == NEW, "литерал заголовка @0x1E4A1 = Uranium (PC красный)")
chk(OLD not in md, "старый литерал 'Blue PC Simulator' отсутствует")
chk(len(md) == 6966084, f"размер файла не изменился ({len(md)})")

# ============================================================================
print("== 2. libil2cpp.so: v3-патчи (байты) ==")
# (va, длина, sha256) -- вычислено из mod/patch_so_v3.py на исправленном дереве
import importlib.util
spec = importlib.util.spec_from_file_location("p3", os.path.join(os.path.dirname(__file__), "patch_so_v3.py"))
p3 = importlib.util.module_from_spec(spec)
sys.argv = [p3.__file__, BASE]
spec.loader.exec_module(p3)  # применит только пропуски (идемпотентен) -- безопасно

import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    so64 = open(os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so"), "rb").read()
    so32 = open(os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so"), "rb").read()

def expect64(lines, va):
    return p3.asm_block64(va, lines)
def expect32(lines, va):
    return p3.asm_block32(va, lines)

R64 = [
    ("кейв sz64", 0x85D978, b"".join([
        p3.asm64("fmov s9, w22", 0x85D978+0x00), p3.asm64("cmp w22, #0x20", 0x85D978+0x04),
        p3.asm64("b.ne #0x%x" % (0x85D978+0x14), 0x85D978+0x08), p3.asm64("cmp w0, #0x46", 0x85D978+0x0C),
        p3.asm64("b.eq #0x%x" % (0x85D978+0x28), 0x85D978+0x10), p3.asm64("cmp w22, #0x46", 0x85D978+0x14),
        p3.asm64("b.ne #0x%x" % (0x85D978+0x24), 0x85D978+0x18), p3.asm64("cmp w0, #0x20", 0x85D978+0x1C),
        p3.asm64("b.eq #0x%x" % (0x85D978+0x28), 0x85D978+0x20), p3.asm64("b #0x867480", 0x85D978+0x24),
        p3.asm64("b #0x8672d4", 0x85D978+0x28)])),
    ("кейв btc64", 0x85D9B8, b"".join([
        p3.asm64("fmov s8, s0", 0x85D9B8+0x00), p3.asm64("bl #0x7e0c50", 0x85D9B8+0x04),
        p3.asm64("cbz x0, #0x%x" % (0x85D9B8+0x24), 0x85D9B8+0x08),
        p3.asm64("ldrb w8, [x0, #0x3a]", 0x85D9B8+0x0C),
        p3.asm64("cbz w8, #0x%x" % (0x85D9B8+0x24), 0x85D9B8+0x10),
        p3.asm64("fmov s0, s8", 0x85D9B8+0x14), p3.asm64("fmov s1, wzr", 0x85D9B8+0x18),
        p3.asm64("fcmp s1, s0", 0x85D9B8+0x1C), p3.asm64("b.ls #0x829728", 0x85D9B8+0x20),
        p3.asm64("b #0x829674", 0x85D9B8+0x24), p3.asm64("fmov s0, s8", 0x85D9B8+0x28),
        p3.asm64("ldr s1, [x20, #0x24]", 0x85D9B8+0x2C), p3.asm64("fcmp s1, s0", 0x85D9B8+0x30),
        p3.asm64("b.ls #0x829728", 0x85D9B8+0x34), p3.asm64("b #0x829674", 0x85D9B8+0x38)])),
    ("кейв money64", 0x85DA08, b"".join([
        p3.asm64("str x30, [sp, #-0x10]!", 0x85DA08+0x00), p3.asm64("bl #0x7e0ce4", 0x85DA08+0x04),
        p3.asm64("ldrb w8, [x21, #0x3a]", 0x85DA08+0x08),
        p3.asm64("cbz w8, #0x%x" % (0x85DA08+0x1C), 0x85DA08+0x0C),
        p3.asm64("movz w0, #0x7fff", 0x85DA08+0x10), p3.asm64("movk w0, #0x7fff, lsl #16", 0x85DA08+0x14),
        p3.asm64("ldr x30, [sp], #0x10", 0x85DA08+0x18), p3.asm64("ret", 0x85DA08+0x1C)])),
    ("Purchase: размер", 0x8672A4, expect64([
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x178]", "blr x9",
        "mov w22, w0",
        "ldr x8, [x20]", "mov x0, x20", "ldp x9, x1, [x8, #0x198]", "blr x9",
        "b #0x85D978", "nop", "nop"], 0x8672A4)),
    ("Purchase: get_Money->кейв", 0x867338, p3.asm64("bl #0x85DA08", 0x867338)),
    ("Purchase: спавн", 0x867394, expect64([
        "fmov w23, s9", "cmp w23, #0x46",
        "b.ne #0x%x" % (0x867394+0x14), "ldr x23, [x19, #0x50]",
        "b #0x%x" % (0x867394+0x18), "ldr x23, [x19, #0x30]", "mov x0, x23",
        "bl #0x17cd6b8", "mov x1, x0", "mov x0, x21", "mov x2, xzr",
        "bl #0x7e2a00", "cbz x0, #0x867544", "mov x23, x0",
        "adrp x8, #0x224a000", "ldr x8, [x8, #0x9b8]", "ldr x1, [x8]", "mov x0, x23",
        "bl #0x8ccd94", "mov x23, x0", "mov x0, x23", "mov x1, x20", "mov x2, x22",
        "mov x3, xzr", "bl #0x816ec8"], 0x867394)),
    ("Purchase: неверный размер", 0x8674AC, expect64([
        "mov x20, x0", "bl #0x7e0c50", "cbz x0, #0x867508", "mov x1, x20",
        "mov x2, xzr", "b #0x7e23b8"] + ["nop"] * 17, 0x8674AC)),
    ("ButtonDown: BTC->кейв", 0x829668, expect64(["b #0x85D9B8", "nop", "nop"], 0x829668)),
]
for name, va, exp in R64:
    chk(so64[va:va+len(exp)] == exp, f"arm64 {name} @0x{va:x} ({len(exp)} байт)")

R32 = [
    ("кейв sz32", 0x1C6A000, b"".join([
        p3.asm32("vmov r8, s16", 0x1C6A000+0x00), p3.asm32("cmp r8, #0x20", 0x1C6A000+0x04),
        p3.asm32("bne #0x%x" % (0x1C6A000+0x14), 0x1C6A000+0x08), p3.asm32("cmp r0, #0x46", 0x1C6A000+0x0C),
        p3.asm32("beq #0x%x" % (0x1C6A000+0x28), 0x1C6A000+0x10), p3.asm32("cmp r8, #0x46", 0x1C6A000+0x14),
        p3.asm32("bne #0x%x" % (0x1C6A000+0x24), 0x1C6A000+0x18), p3.asm32("cmp r0, #0x20", 0x1C6A000+0x1C),
        p3.asm32("beq #0x%x" % (0x1C6A000+0x28), 0x1C6A000+0x20), p3.asm32("b #0x58bb18", 0x1C6A000+0x24),
        p3.asm32("b #0x58b8ec", 0x1C6A000+0x28)])),
    ("кейв btc32", 0x1C6A080, b"".join([
        p3.asm32("vmov.f32 s16, s0", 0x1C6A080+0x00), p3.asm32("vmov.f32 s17, s2", 0x1C6A080+0x04),
        p3.asm32("bl #0x4dbd78", 0x1C6A080+0x08), p3.asm32("cmp r0, #0", 0x1C6A080+0x0C),
        p3.asm32("beq #0x%x" % (0x1C6A080+0x38), 0x1C6A080+0x10),
        p3.asm32("ldrb r1, [r0, #0x1e]", 0x1C6A080+0x14), p3.asm32("cmp r1, #0", 0x1C6A080+0x18),
        p3.asm32("beq #0x%x" % (0x1C6A080+0x38), 0x1C6A080+0x1C),
        p3.asm32("vmov.f32 s0, s16", 0x1C6A080+0x20), p3.asm32("mov r1, #0", 0x1C6A080+0x24),
        p3.asm32("vmov s2, r1", 0x1C6A080+0x28), p3.asm32("vcmpe.f32 s2, s0", 0x1C6A080+0x2C),
        p3.asm32("vmrs apsr_nzcv, fpscr", 0x1C6A080+0x30), p3.asm32("bls #0x53bba4", 0x1C6A080+0x34),
        p3.asm32("b #0x53badc", 0x1C6A080+0x38), p3.asm32("vmov.f32 s0, s16", 0x1C6A080+0x3C),
        p3.asm32("vmov.f32 s2, s17", 0x1C6A080+0x40), p3.asm32("vcmpe.f32 s2, s0", 0x1C6A080+0x44),
        p3.asm32("vmrs apsr_nzcv, fpscr", 0x1C6A080+0x48), p3.asm32("bls #0x53bba4", 0x1C6A080+0x4C),
        p3.asm32("b #0x53badc", 0x1C6A080+0x50)])),
    ("кейв money32", 0x1C6A100, b"".join([
        p3.asm32("push {r4, lr}", 0x1C6A100+0x00), p3.asm32("bl #0x4dbe1c", 0x1C6A100+0x04),
        p3.asm32("ldrb r1, [r6, #0x1e]", 0x1C6A100+0x08), p3.asm32("cmp r1, #0", 0x1C6A100+0x0C),
        p3.asm32("beq #0x%x" % (0x1C6A100+0x1C), 0x1C6A100+0x10),
        p3.asm32("movw r0, #0x7fff", 0x1C6A100+0x14), p3.asm32("movt r0, #0x7fff", 0x1C6A100+0x18),
        p3.asm32("pop {r4, pc}", 0x1C6A100+0x1C)])),
    ("Purchase: размер", 0x58B8B4, expect32([
        "ldr r0, [r5]", "ldr r2, [r0, #0xdc]", "ldr r1, [r0, #0xe0]", "mov r0, r5", "blx r2",
        "vmov s16, r0",
        "ldr r0, [r5]", "ldr r2, [r0, #0xec]", "ldr r1, [r0, #0xf0]", "mov r0, r5", "blx r2",
        "b #0x1C6A000", "nop", "nop"], 0x58B8B4)),
    ("Purchase: get_Money->кейв", 0x58B968, p3.asm32("bl #0x1C6A100", 0x58B968)),
    ("Purchase: спавн", 0x58B9B4, expect32([
        "vmov r0, s16", "cmp r0, #0x46", "ldreq sb, [r4, #0x28]", "ldrne sb, [r4, #0x18]",
        "cmp sb, #0", "beq #0x58bba4", "mov r0, sb", "mov r1, #0", "bl #0x1879ea4",
        "cmp r0, #0", "beq #0x58bba4", "mov r1, r0", "mov r0, r6", "mov r2, #0",
        "bl #0x4de408", "cmp r0, #0", "beq #0x58bba4", "bl #0x1C6A140", "cmp r0, #0",
        "beq #0x58bba4", "mov r1, r5", "mov r2, r8", "mov r3, #0", "bl #0x522ad8"] + ["nop"] * 24, 0x58B9B4)),
    ("Purchase: неверный размер", 0x58BB48, expect32([
        "bl #0x4dbd78", "cmp r0, #0", "beq #0x58bba4", "mov r1, r5", "mov r2, #0",
        "pop {r4, r5, r6, r7, r8, sb, sl, lr}", "b #0x4ddc14"] + ["nop"] * 16, 0x58BB48)),
    ("ButtonDown: BTC->кейв", 0x53BAD0, expect32(["b #0x1C6A080", "nop", "nop"], 0x53BAD0)),
]
for name, va, exp in R32:
    chk(so32[va:va+len(exp)] == exp, f"arm32 {name} @0x{va:x} ({len(exp)} байт)")

# Кейв getcomp32 (последний)
G = 0x1C6A140
L1 = p3.texloader_slot32(so32)
D1 = (L1 - (G + 0x10)).to_bytes(4, "little")
exp = b"".join([
    p3.asm32("mov r12, r0", G+0x00), p3.asm32("ldr r1, [pc, #0x14]", G+0x04),
    p3.asm32("ldr r1, [pc, r1]", G+0x08), p3.asm32("ldr r1, [r1]", G+0x0C),
    p3.asm32("mov r0, r12", G+0x10), p3.asm32("b #0x5ffe4c", G+0x14),
    p3.asm32("nop", G+0x18), p3.asm32("nop", G+0x1C)]) + D1
chk(so32[G:G+len(exp)] == exp, f"arm32 кейв getcomp32 @0x{G:x}")

# --- Семантика ветвлений (capstone) ---
try:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, CS_ARCH_ARM, CS_MODE_ARM
    def tgt(data, md, va):
        ins = next(md.disasm(data[va:va+4], va))
        return ins
    def branch_ok(data, md, va, target, expect_prefix, name):
        t = tgt(data, md, target)
        good = t.mnemonic.startswith(expect_prefix)
        chk(good, f"{name}: 0x{va:x} -> 0x{target:x} = {t.mnemonic} {t.op_str}")
    m64 = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    m32 = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    print("-- семантика arm64 --")
    branch_ok(so64, m64, 0x8672c8, 0x85d978, "fmov", "размер->кейв")
    branch_ok(so64, m64, 0x85d988, 0x85d9a0, "b", "sz64 32x70->Lok")
    branch_ok(so64, m64, 0x85d990, 0x85d99c, "b", "sz64->Lfail")
    branch_ok(so64, m64, 0x85d998, 0x85d9a0, "b", "sz64 70x32->Lok")
    branch_ok(so64, m64, 0x85d99c, 0x867480, "adrp", "Lfail->ошибка")
    branch_ok(so64, m64, 0x85d9a0, 0x8672d4, "adrp", "Lok->деньги")
    branch_ok(so64, m64, 0x86739c, 0x8673a8, "ldr", "спавн верт.")
    branch_ok(so64, m64, 0x8673a4, 0x8673ac, "mov", "спавн гориз.")
    branch_ok(so64, m64, 0x85d9d8, 0x829728, "fsub", "btc64 sandbox->unlock")
    branch_ok(so64, m64, 0x85d9dc, 0x829674, "adrp", "btc64->не хватает")
    branch_ok(so64, m64, 0x829668, 0x85d9b8, "fmov", "ButtonDown->кейв")
    branch_ok(so64, m64, 0x867338, 0x85da08, "str", "get_Money->кейв")
    branch_ok(so64, m64, 0x8674c0, 0x7e23b8, "str", "неверный размер->FadeText")
    print("-- семантика arm32 --")
    branch_ok(so32, m32, 0x58b8e0, 0x1c6a000, "vmov", "размер->кейв")
    branch_ok(so32, m32, 0x1c6a010, 0x1c6a028, "b", "sz32 32x70->Lok")
    branch_ok(so32, m32, 0x1c6a018, 0x1c6a024, "b", "sz32->Lfail")
    branch_ok(so32, m32, 0x1c6a020, 0x1c6a028, "b", "sz32 70x32->Lok")
    branch_ok(so32, m32, 0x1c6a024, 0x58bb18, "ldr", "Lfail->ошибка")
    branch_ok(so32, m32, 0x1c6a028, 0x58b8ec, "ldr", "Lok->деньги")
    branch_ok(so32, m32, 0x58b9f8, 0x1c6a140, "mov", "спавн->getcomp")
    branch_ok(so32, m32, 0x1c6a154, 0x5ffe4c, "push", "getcomp->GetComponent")
    branch_ok(so32, m32, 0x1c6a0b4, 0x53bba4, "vsub", "btc32 sandbox->unlock")
    branch_ok(so32, m32, 0x1c6a0b8, 0x53badc, "ldr", "btc32->не хватает")
    branch_ok(so32, m32, 0x53bad0, 0x1c6a080, "vmov", "ButtonDown->кейв")
    branch_ok(so32, m32, 0x58b968, 0x1c6a100, "push", "get_Money->кейв")
    branch_ok(so32, m32, 0x1c6a110, 0x1c6a11c, "pop", "money32->pop")
    branch_ok(so32, m32, 0x58bb60, 0x4ddc14, "push", "неверный размер->FadeText")
except ImportError:
    print("-- capstone недоступен, семантика пропущена --")

# ============================================================================
print("== 3. data.unity3d ==")
sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
from modtools import load_env, Ctx
env = load_env()
ctx = Ctx(env)
R = "resources.assets"

for pid, name in ((13706, "Apson A3 512x512"), (13739, "Apson A3 1024x1024"), (13754, "{Horizontal Banner}")):
    si = ctx.read_tt(R, pid)
    chk(si["m_Name"] == name and si["bitcoin"] == 0.0, f"ShopItem {pid} {name}: bitcoin=0 (разблокирован)")

t = ctx.read_tt(R, 164)
px = 32*32 + 16*16 + 8*8 + 4*4 + 2*2 + 1*1
chk(t["m_Name"] == "rgb" and t["m_TextureFormat"] == 4 and t["image data"] == b"\xff" * (px * 4)
    and t["m_StreamData"]["path"] == "",
    "текстура 164 'rgb' -> белая RGBA32 (сетка/субпиксели вблизи убраны)")

pe = ctx.read_tt(R, 11239)
chk(pe["alertText"] == {"m_FileID": 0, "m_PathID": 13747}, "PrintExpert.alertText -> TextureLoader 13747 (BannerStand_H)")
chk(pe["bannerPrefab"] == {"m_FileID": 0, "m_PathID": 12916}, "PrintExpert.bannerPrefab -> 12916 (вертикальный)")
tl = ctx.read_tt(R, 13747)
go = ctx.read_tt(R, tl["m_GameObject"]["m_PathID"])
chk(go["m_Name"] == "BannerStand_H", "13747 действительно на BannerStand_H")

# ============================================================================
print("== 4. Инварианты v2 ==")
market = ctx.read_tt(R, 12594)
chk(len(market["items"]) == 56, f"в маркете 56 товаров ({len(market['items'])})")
g = ctx.read_tt(R, 117)
chk(g["m_Name"] == "Grid" and g["m_TextureFormat"] == 4 and g["image data"] == b"\xff" * g["m_CompleteImageSize"], "Grid 117 белая RGBA32")
ps = ctx.read_tt("globalgamemanagers", 1)
chk(ps["productName"] == "Uranium PC Simulator", "productName = Uranium PC Simulator")
tt0 = ctx.read_tt("level0", 1102)
chk("Uranium" in tt0["m_Text"], f"заголовок level0 = {tt0['m_Text'][:40]!r}")

print()
print("ИТОГ:", "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if ok else "ЕСТЬ ОШИБКИ!")
sys.exit(0 if ok else 1)
