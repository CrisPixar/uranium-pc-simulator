#!/usr/bin/env python3
"""Патч global-metadata.dat: рантайм-литерал заголовка главного меню.

Литерал лежит в пуле строк @0x1E4A1 (60 байт, UTF-8, литералы подряд без
разделителей, длины хранятся в индекс-таблице -> допустима только замена
той же длины). Именно этот литерал игра подставляет в Text заголовка меню
после старта (поэтому в v2 заголовок на 1-2 секунды возвращался к "Blue").

  <color=cyan>Blue</color> <color=orange>PC</color> Simulator
  <color=cyan>Uranium</color> <color=red>PC</color> Simulator
  (обе строки ровно 59 байт)

Запуск:  python3 patch_metadata.py [путь_к_дереву_apktool]
"""
import sys, os

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
PATH = os.path.join(BASE, "assets/bin/Data/Managed/Metadata/global-metadata.dat")

OLD = b"<color=cyan>Blue</color> <color=orange>PC</color> Simulator"
NEW = b"<color=cyan>Uranium</color> <color=red>PC</color> Simulator"
OFF = 0x1E4A1
assert len(OLD) == len(NEW) == 59, (len(OLD), len(NEW))

data = open(PATH, "rb").read()
cur = data[OFF:OFF + 59]
if cur == NEW:
    print(f"[skip] {PATH}: литерал уже Uranium")
elif cur == OLD:
    data = data[:OFF] + NEW + data[OFF + 59:]
    with open(PATH, "wb") as f:
        f.write(data)
    print(f"[ ok ] {PATH}: заголовок -> Uranium (PC теперь красный)")
else:
    raise RuntimeError(f"неожиданные байты @0x{OFF:x}: {cur!r}")

# Контроль: старый литерал не должен больше встречаться целиком
assert OLD not in open(PATH, "rb").read(), "старый литерал всё ещё присутствует!"
print("ПАТЧ МЕТАДАННЫХ ПРИМЕНЕН.")
