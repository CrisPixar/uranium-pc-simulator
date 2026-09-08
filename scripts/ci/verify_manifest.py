#!/usr/bin/env python3
"""Verify the package name in the built APK's BINARY AndroidManifest.xml.

The old CI check ('пакет') only searched for the UTF-16LE bytes of the
package string anywhere in the binary manifest — that passes even when the
<manifest android:package> attribute itself is broken (e.g. "None"), because
the string also sits in the string pool as activity/permission names.

This script parses the AXML chunks and reads the actual `package` attribute
of the root <manifest> element. Exit 1 -> CI stops before upload/release.
Guards against: "Failed to parse APK: Invalid manifest package: must have at
least one '.' separator" on the device.
"""
import struct
import sys
import zipfile

EXPECTED = "com.UraniumPCS.UraniumPCSimulator"


def parse_strings(data):
    stype, shs, ssize, scount, sstyle, sflags, sstart, sstyles = struct.unpack(
        "<HHIIIIII", data[8:36])
    offs = struct.unpack(f"<{scount}I", data[8 + shs:8 + shs + 4 * scount])
    out = []
    base = 8 + sstart
    for o in offs:
        p = base + o
        if sflags & (1 << 8):  # UTF-8 pool
            l1 = data[p]; p += 1
            if l1 & 0x80:
                l1 = ((l1 & 0x7F) << 8) | data[p]; p += 1
            l2 = data[p]; p += 1
            if l2 & 0x80:
                l2 = ((l2 & 0x7F) << 8) | data[p]; p += 1
            out.append(data[p:p + l2].decode("utf-8", "replace"))
        else:  # UTF-16 pool
            l = struct.unpack("<H", data[p:p + 2])[0]; p += 2
            if l & 0x8000:
                l = ((l & 0x7FFF) << 16) | struct.unpack("<H", data[p:p + 2])[0]
                p += 2
            out.append(data[p:p + 2 * l].decode("utf-16-le", "replace"))
    return out


def manifest_package(data):
    strings = parse_strings(data)
    pos = 8 + struct.unpack("<I", data[12:16])[0]  # skip string pool chunk
    while pos + 8 <= len(data):
        ctype, chs, csize = struct.unpack("<HHI", data[pos:pos + 8])
        if csize == 0:
            break
        if ctype == 0x0102:  # START_ELEMENT
            _, name = struct.unpack("<II", data[pos + chs:pos + chs + 8])
            if strings[name] == "manifest":
                attr_start, _, attr_count = struct.unpack(
                    "<HHH", data[pos + chs + 8:pos + chs + 14])
                ap = pos + chs + attr_start
                for _ in range(attr_count):
                    ans, aname, araw, atsr, adata = struct.unpack(
                        "<IIIII", data[ap:ap + 20])
                    ap += 20
                    if aname != 0xFFFFFFFF and strings[aname] == "package":
                        if araw != 0xFFFFFFFF:
                            return strings[araw]
                        return None
                return None
        pos += csize
    return None


def main():
    apk_path = sys.argv[1] if len(sys.argv) > 1 else "UraniumPCSimulator.apk"
    z = zipfile.ZipFile(apk_path)
    pkg = manifest_package(z.read("AndroidManifest.xml"))
    print(f"manifest package attr: {pkg!r} (expected {EXPECTED!r})")
    if not pkg:
        print("FAIL: package attribute missing or not a string")
        sys.exit(1)
    if "." not in pkg:
        print("FAIL: package has no '.' separator -> device will reject: "
              "Invalid manifest package")
        sys.exit(1)
    if pkg != EXPECTED:
        print("FAIL: unexpected package")
        sys.exit(1)
    print(f"OK: package {pkg}, {len(z.namelist())} entries in APK")


if __name__ == "__main__":
    main()
