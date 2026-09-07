#!/usr/bin/env python3
"""Мини-ассемблер поверх keystone: метки, adrp/add (arm64), литеральный пул (arm32).

Используется патчами Uranium PC Simulator (mod/patch_b13.py).
"""
import struct
from keystone import (Ks, KS_ARCH_ARM64, KS_ARCH_ARM,
                      KS_MODE_LITTLE_ENDIAN, KS_MODE_ARM)

_ks64 = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
_ks32 = Ks(KS_ARCH_ARM, KS_MODE_ARM)


def a64(src, addr):
    enc, cnt = _ks64.asm(src, addr)
    if enc is None or cnt != 1:
        raise ValueError(f"asm64 {src!r} @0x{addr:x}")
    return bytes(enc)


def a32(src, addr):
    enc, cnt = _ks32.asm(src, addr)
    if enc is None or cnt != 1:
        raise ValueError(f"asm32 {src!r} @0x{addr:x}")
    return bytes(enc)


class Asm64:
    """Инструкции + метки.

      "Lname:"              — метка
      "LIT x0, 0x85dd0c"    — adrp+add на абсолютный адрес (2 инструкции)
      ссылка на метку       — "#Lname"
    """

    def __init__(self, base):
        self.base = base
        self.items = []

    def __call__(self, *lines):
        for ln in lines:
            self.items.append(ln.strip())
        return self

    def _expand(self):
        out = []
        for ln in self.items:
            if ln.endswith(":"):
                out.append(ln)
            elif ln.startswith("LIT "):
                reg, addr = ln[4:].split(",")
                out.append(("LITa", reg.strip(), int(addr, 0)))
                out.append(("LITb", reg.strip(), int(addr, 0)))
            else:
                out.append(ln)
        return out

    def assemble(self):
        items = self._expand()
        labels, addr = {}, self.base
        for it in items:
            if isinstance(it, str) and it.endswith(":"):
                labels[it[:-1]] = addr
            else:
                addr += 4
        blob, addr = b"", self.base
        for it in items:
            if isinstance(it, str) and it.endswith(":"):
                continue
            if isinstance(it, tuple):
                kind, reg, target = it
                if kind == "LITa":
                    blob += a64(f"adrp {reg}, #0x{target & ~0xFFF:x}", addr)
                else:
                    blob += a64(f"add {reg}, {reg}, #0x{target & 0xFFF:x}", addr)
            else:
                ln = it
                for name, la in sorted(labels.items(), key=lambda kv: -len(kv[0])):
                    ln = ln.replace("#" + name, "#0x%x" % la)
                blob += a64(ln, addr)
            addr += 4
        self.labels = labels
        self.end = addr
        return blob


class Asm32:
    """arm32 + литеральный пул (по слоту на каждое использование).

      "Lname:"               — метка
      "LIT r0, 0x1c6a38c"    — ldr r0,[pc,#k]; add r0,pc,r0  (адрес данных)
      "IMM r1, 0x2711"       — ldr r1,[pc,#k]                (константа)
    """

    def __init__(self, base, pool_at):
        self.base = base
        self.pool_at = pool_at
        self.items = []

    def __call__(self, *lines):
        for ln in lines:
            self.items.append(ln.strip())
        return self

    def _expand(self):
        out = []
        for ln in self.items:
            if ln.endswith(":"):
                out.append(ln)
            elif ln.startswith("LIT "):
                reg, addr = ln[4:].split(",")
                out.append(("LIT", reg.strip(), int(addr, 0)))
                out.append(("LIT2", reg.strip(), int(addr, 0)))
            elif ln.startswith("IMM "):
                reg, val = ln[4:].split(",")
                out.append(("IMM", reg.strip(), int(val, 0)))
            else:
                out.append(ln)
        return out

    def assemble(self):
        items = self._expand()
        labels, addr = {}, self.base
        for it in items:
            if isinstance(it, str) and it.endswith(":"):
                labels[it[:-1]] = addr
            else:
                addr += 4
        code_end = addr
        # слот пула на каждое LIT/IMM
        slot_of, pool_vals, pool_addr = {}, [], self.pool_at
        addr = self.base
        for i, it in enumerate(items):
            if isinstance(it, str) and it.endswith(":"):
                continue
            if isinstance(it, tuple) and it[0] in ("LIT", "IMM"):
                slot_of[i] = pool_addr
                if it[0] == "LIT":
                    # значение = target - (адрес add + 8) = target - (addr_ldr + 4 + 8)
                    pool_vals.append(("s", it[2] - (addr + 12)))
                else:
                    pool_vals.append(("u", it[2]))
                pool_addr += 4
            addr += 4
        blob, addr = b"", self.base
        for i, it in enumerate(items):
            if isinstance(it, str) and it.endswith(":"):
                continue
            if isinstance(it, tuple):
                kind, reg, val = it
                if kind == "LIT2":
                    blob += a32(f"add {reg}, pc, {reg}", addr)
                else:
                    off = slot_of[i] - (addr + 8)
                    if not 0 <= off < 4096:
                        raise ValueError(f"пул вне досягаемости: {off} @0x{addr:x}")
                    blob += a32(f"ldr {reg}, [pc, #{off}]", addr)
            else:
                ln = it
                for name, la in sorted(labels.items(), key=lambda kv: -len(kv[0])):
                    ln = ln.replace("#" + name, "#0x%x" % la)
                blob += a32(ln, addr)
            addr += 4
        pool = b"".join(struct.pack("<i" if k == "s" else "<I", v)
                        for k, v in pool_vals)
        self.labels = labels
        self.code_end = code_end
        self.pool_end = pool_addr
        return blob, pool
