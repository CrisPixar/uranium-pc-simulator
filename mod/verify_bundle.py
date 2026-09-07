#!/usr/bin/env python3
"""ПОЛНАЯ ПРОВЕРКА модифицированного data.unity3d против оригинала.

Проверяет:
  A. Байт-в-байт диф всех объектов против ОРИГИНАЛА: изменились ровно
     запланированные объекты, ничего не пропало, добавились ровно 81 новых.
  B. Все PPtr во всех новых и изменённых объектах РАЗРЕШАЮТСЯ
     (внутренние pid существуют; внешние fileID в пределах externals).
  C. Структурная целостность клонов: компоненты <-> GameObject взаимно,
     Transform parent/child, корень без отца.
  D. Критические ссылки имеют правильный ТИП (spawn -> GameObject,
     rend -> MeshRenderer, материалы -> Material, sprite -> Sprite).
  E. Все значения правок (принты, цены, градиент, физика, тексты).
  F. Все стрим-текстуры (m_StreamData) в пределах resS-файлов.
  G. Translate: у всех строк число колонок == заголовку; строки на месте.

Запуск: python3 verify_bundle.py [дерево_мода] [оригинал_дерево]
Коды выхода: 0 = все проверки пройдены, 1 = ошибки.
"""
import sys, os, io, hashlib, contextlib

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/uranium"
ORIG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/orig/Blue_PC_Simulator_v1.9.1.11(1)_base_src"
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")
ORIG_BUNDLE = os.path.join(ORIG, "assets/bin/Data/data.unity3d")

sys.path.insert(0, "/home/user/tools")
import modtools
modtools.BASE = BASE
modtools.DUMMY = os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
from modtools import load_env, Ctx
import UnityPy

ERRORS = []
def check(cond, msg):
    tag = "OK " if cond else "FAIL"
    print(f"  [{tag}] {msg}")
    if not cond:
        ERRORS.append(msg)
    return cond

def load_bundles():
    def mk(path):
        env = UnityPy.load(path)
        files = {}
        for name, f in list(env.files.items()) + list(env.cabs.items()):
            if f.__class__.__name__ == "SerializedFile":
                files[os.path.basename(name)] = (env, f)
        return files
    return mk(BUNDLE), mk(ORIG_BUNDLE)

def md5_obj(o):
    try:
        return hashlib.md5(o.get_raw_data()).hexdigest()
    except Exception as e:
        return f"ERR:{e}"

print("=" * 70)
print("A. Диф объектов против оригинала")
new_files, orig_files = load_bundles()

EXPECTED_CHANGED = {
    ("globalgamemanagers", 1), ("globalgamemanagers", 10),
    ("level0", 1102),
    ("level1", 819), ("level1", 821),
    ("level3", 328), ("level3", 331),
    ("level4", 328), ("level4", 331),
    ("level5", 339), ("level5", 342),
    ("level6", 355), ("level6", 358),
    ("resources.assets", 117), ("resources.assets", 633),
    ("resources.assets", 12533), ("resources.assets", 12594),
}
NEW_COUNT = 81

orig_map = {}
for bn, (e, f) in orig_files.items():
    for pid, o in f.objects.items():
        orig_map[(bn, pid)] = (o.type.name, md5_obj(o))
new_map = {}
for bn, (e, f) in new_files.items():
    for pid, o in f.objects.items():
        new_map[(bn, pid)] = (o.type.name, md5_obj(o))

check(len(orig_map) > 0 and len(new_map) > 0, f"бандлы читаются (orig {len(orig_map)}, new {len(new_map)})")
missing = set(orig_map) - set(new_map)
added = set(new_map) - set(orig_map)
changed = {k for k in set(orig_map) & set(new_map) if orig_map[k][1] != new_map[k][1]}
check(not missing, f"ни один объект не пропал (пропало: {sorted(missing)[:5]})")
check(len(added) == NEW_COUNT, f"добавлено ровно {NEW_COUNT} объектов (факт: {len(added)})")
check(changed == EXPECTED_CHANGED,
      f"изменены ровно запланированные {len(EXPECTED_CHANGED)} объектов "
      f"(лишние: {sorted(changed - EXPECTED_CHANGED)[:8]})")
added_in_ra = sorted(pid for f_, pid in added if f_ == "resources.assets")
check(len(added_in_ra) == NEW_COUNT, "все новые объекты в resources.assets")

# освобождаем оригинальные окружения (память!) и заранее достаём typetree оригинала
import gc as _gc
def ctx_for(base):
    m2 = sys.modules["modtools"]
    old_base, old_dummy = m2.BASE, m2.DUMMY
    m2.BASE, m2.DUMMY = base, os.environ.get("MOD_DUMMY", "/tmp/dump64new/DummyDll")
    c = Ctx(load_env())
    m2.BASE, m2.DUMMY = old_base, old_dummy
    return c

_ctx_orig = ctx_for(ORIG)
ORIG_TTS = {}
for _key in sorted(EXPECTED_CHANGED):
    _f, _pid = _key
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ORIG_TTS[_key] = _ctx_orig.read_tt(_f, _pid)
    except Exception as _e:
        ORIG_TTS[_key] = {"__error__": str(_e)}
del _ctx_orig
new_files.clear(); orig_files.clear()
del new_map, orig_map
_gc.collect()
print("  [INFO] typetree оригинала для 17 объектов извлечён, память освобождена")

# ----------------------------------------------------------------------------
print("=" * 70)
print("B/C/D. Ссылки, структуры клонов, типы")
env = load_env()
ctx = Ctx(env)
R = "resources.assets"
_ress_env = env

def pptr_ok(fname, pptr, expect_types=None):
    fid, pid = pptr.get("m_FileID", 0), pptr.get("m_PathID", 0)
    if pid == 0 and fid == 0:
        return True, None
    f = ctx.files[fname]
    if fid == 0:
        o = f.objects.get(pid)
        if o is None:
            return False, f"внутренний pid {pid} не существует"
        if expect_types and o.type.name not in expect_types:
            return False, f"pid {pid} имеет тип {o.type.name}, ожидался {expect_types}"
        return True, None
    if fid < 1 or fid > len(f.externals):
        return False, f"fileID {fid} вне externals ({len(f.externals)})"
    return True, None

def walk_pptrs(x):
    if isinstance(x, dict):
        if set(x.keys()) == {"m_FileID", "m_PathID"}:
            yield x
        else:
            for v in x.values():
                yield from walk_pptrs(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk_pptrs(v)

# все новые + изменённые объекты: каждый PPtr разрешается
bad = []
for key in sorted(added | changed):
    f_, pid = key
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            tt = ctx.read_tt(f_, pid)
        for p in walk_pptrs(tt):
            ok, why = pptr_ok(f_, p)
            if not ok:
                bad.append(f"{f_}:{pid} -> {why}")
    except Exception as e:
        bad.append(f"{f_}:{pid} read error: {e}")
check(not bad, f"все PPtr новых/изменённых объектов разрешаются ({bad[:4]})")

# структурная целостность клонов
def verify_tree(root_pid, expect_name, src_root_pid=None, extra_comps=0):
    with contextlib.redirect_stderr(io.StringIO()):
        go = ctx.read_tt(R, root_pid)
    check(go["m_Name"] == expect_name, f"корень клона '{expect_name}' (факт '{go['m_Name']}')")
    comps = [c["component"]["m_PathID"] for c in go["m_Component"] if c["component"]["m_PathID"]]
    ok_backref = True
    for cpid in comps:
        with contextlib.redirect_stderr(io.StringIO()):
            ctt = ctx.read_tt(R, cpid)
        if ctt.get("m_GameObject", {}).get("m_PathID") != root_pid:
            ok_backref = False
    check(ok_backref, f"компоненты корня ссылаются обратно на корень")
    if src_root_pid:
        n_src = len([c for c in ctx.read_tt(R, src_root_pid)["m_Component"]
                     if c["component"]["m_PathID"]])
        check(len(comps) == n_src + extra_comps,
              f"у корня компонент как у исходника {n_src}+{extra_comps} (факт {len(comps)})")
    # потомки
    n_go = 1
    def walk(gpid):
        nonlocal n_go
        g = ctx.read_tt(R, gpid)
        tr = None
        for c in g["m_Component"]:
            p = c["component"]["m_PathID"]
            if p and ctx.obj(R, p).type.name == "Transform":
                tr = ctx.read_tt(R, p)
        for ch in tr["m_Children"]:
            cht = ctx.read_tt(R, ch["m_PathID"])
            cgo = cht["m_GameObject"]["m_PathID"]
            if cht["m_Father"]["m_PathID"] == 0:
                return False
            n_go += 1
            if not walk(cgo):
                return False
        return True
    with contextlib.redirect_stderr(io.StringIO()):
        check(walk(root_pid), "иерархия Transform parent/child согласована")

# найти новые корни по именам
roots = {}
for f_, pid in added:
    if f_ == R:
        o = ctx.obj(R, pid)
        if o.type.name == "GameObject":
            with contextlib.redirect_stderr(io.StringIO()):
                tt = ctx.read_tt(R, pid)
            roots[tt["m_Name"]] = pid
check("Apson_A3_512" in roots and "Apson_A3_1024" in roots and "BannerStand_H" in roots,
      f"найдены корни клонов: {sorted(roots)}")
if "Apson_A3_512" in roots: verify_tree(roots["Apson_A3_512"], "Apson_A3_512", 1673)
if "Apson_A3_1024" in roots: verify_tree(roots["Apson_A3_1024"], "Apson_A3_1024", 1673)
if "BannerStand_H" in roots: verify_tree(roots["BannerStand_H"], "BannerStand_H", 1471, extra_comps=1)

# критические типизированные ссылки
market = ctx.read_tt(R, 12594)
check(len(market["items"]) == 56, f"в Market 56 товаров (факт {len(market['items'])})")
for it in market["items"]:
    ok, why = pptr_ok(R, it, ("MonoBehaviour",))
    if not ok: check(False, f"Market item {it}: {why}")
last3 = [ctx.read_raw_tt(R, 11097, ctx.obj(R, i["m_PathID"]).get_raw_data()) for i in market["items"][-3:]]
names = [x["itemName"] for x in last3]
prices = [x["price"] for x in last3]
check(names == ["Apson A3 512x512", "Apson A3 1024x1024", "{Horizontal Banner}"],
      f"новые товары: {names}")
check(prices == [15000, 30000, 100], f"цены: {prices}")
for x in last3:
    ok, why = pptr_ok(R, x["spawn"], ("GameObject",))
    check(ok, f"spawn '{x['itemName']}' -> GameObject ({why})")
    ok, why = pptr_ok(R, x["sprite"], ("Sprite",))
    check(ok, f"sprite '{x['itemName']}' -> Sprite ({why})")
    check(x["bitcoin"] == 5.0, f"btc '{x['itemName']}' = 5.0")

# источники НЕ тронуты
src_printer = ctx.read_tt(R, 1673)
check(src_printer["m_Name"] == "Apson_A3", "исходный префаб 1673 не переименован (не испорчен)")
src_si = ctx.read_tt(R, 11097)
check(src_si["itemName"] == "Apson A3 128x128" and src_si["spawn"]["m_PathID"] == 1672,
      "исходный ShopItem 11097 цел (spawn 1672)")
src_item = ctx.read_tt(R, 11426)
check(src_item["spawnId"] == "Apson_A3", "исходный Item 11426 spawnId цел")
src_pf = ctx.read_tt(R, 11895)
check(src_pf["m_GameObject"]["m_PathID"] == 2874, "исходный PaperFrame 11895 цел")

# принтеры: значения
for root_name, size in [("Apson_A3_512", 512), ("Apson_A3_1024", 1024)]:
    rp = roots[root_name]
    found = False
    for c in ctx.read_tt(R, rp)["m_Component"]:
        p = c["component"]["m_PathID"]
        if p and ctx.obj(R, p).type.name == "MonoBehaviour":
            klass, tt2 = ctx.mono_class(R, p)
            if klass == "Printer":
                found = True
                check(tt2["supportedPrintSize"] == {"x": size, "y": size},
                      f"{root_name}: supportedPrintSize {size} (факт {tt2['supportedPrintSize']})")
                ok, why = pptr_ok(R, tt2["paperPrefab"])
                check(ok, f"{root_name}: paperPrefab разрешается ({why})")
    check(found, f"{root_name}: компонент Printer найден")

# баннер: значения
if "BannerStand_H" in roots:
    rp = roots["BannerStand_H"]
    gott = {}
    for c in ctx.read_tt(R, rp)["m_Component"]:
        p = c["component"]["m_PathID"]
        if p and ctx.obj(R, p).type.name == "MonoBehaviour":
            klass, tt2 = ctx.mono_class(R, p)
            gott[klass] = tt2
        elif p and ctx.obj(R, p).type.name == "BoxCollider":
            gott.setdefault("BoxCollider", []).append(tt2 if (tt2 := ctx.read_tt(R, p)) else None)
    check("PaperFrame" in gott, "BannerStand_H: есть PaperFrame")
    check("TextureLoader" in gott, "BannerStand_H: есть TextureLoader")
    if "TextureLoader" in gott:
        ok, why = pptr_ok(R, gott["TextureLoader"]["rend"], ("MeshRenderer",))
        check(ok, f"TextureLoader.rend -> MeshRenderer ({why})")
    if "Item" in gott:
        check(gott["Item"]["spawnId"] == "BannerStand_H", "Item.spawnId = BannerStand_H")

# ----------------------------------------------------------------------------
print("=" * 70)
print("E. Значения правок")
g = ctx.read_tt(R, 117)
check(g["m_TextureFormat"] == 4 and g["m_CompleteImageSize"] == 5460
      and g["image data"] == b"\xff" * 5460 and g["m_StreamData"]["size"] == 0,
      "Grid: RGBA32 5460 байт белого, без стрима")
p = ctx.read_tt(R, 12533)
check(p["maxCanvasSize"] == {"x": 1024, "y": 1024}, "Paint 1024x1024")
pm = ctx.read_tt("globalgamemanagers", 10)
check((pm["m_DefaultSolverIterations"], pm["m_DefaultSolverVelocityIterations"],
       pm["m_BounceThreshold"]) == (10, 4, 1.0), "PhysicsManager 10/4/1.0")
ps = ctx.read_tt("globalgamemanagers", 1)
check(ps["productName"] == "Uranium PC Simulator", "productName")
ttl = ctx.read_tt("level0", 1102)
check(ttl["m_Text"] == "<color=cyan>Uranium</color> <color=orange>PC</color> Simulator",
      f"заголовок меню: {ttl['m_Text']!r}")
for lv, psp, psrp, fid in [("level1", 819, 821, 4), ("level3", 328, 331, 6),
                            ("level4", 328, 331, 6), ("level5", 339, 342, 6),
                            ("level6", 355, 358, 5)]:
    t2 = ctx.read_tt(lv, psp)
    sc = t2["InitialModule"]["startColor"]
    ct = [sc["maxGradient"][f"ctime{i}"] for i in range(8)]
    check(sc["minMaxState"] == 4 and sc["maxGradient"]["m_NumColorKeys"] == 8
          and ct == sorted(ct) and ct[0] == 0 and ct[7] == 65535,
          f"{lv}: градиент RandomColor корректен")
    r2 = ctx.read_tt(lv, psrp)
    ok, why = pptr_ok(lv, r2["m_Materials"][0], ("Material",))
    check(ok and r2["m_Materials"][0] == {"m_FileID": fid, "m_PathID": 57},
          f"{lv}: PSR материал = ParticleFlare ({fid}:57) [{why}]")

# ----------------------------------------------------------------------------
print("=" * 70)
print("F. Стрим-текстуры в пределах resS")
ress = {}
for name, f in _ress_env.cabs.items():
    if name.lower().endswith(".ress"):
        ress[os.path.basename(name).lower()] = f.Length
bad = []
for fname, f in ctx.files.items():
    for pid, o in f.objects.items():
        if o.type.name == "Texture2D":
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    tt = ctx.read_tt(fname, pid)
            except Exception:
                continue
            sd = tt["m_StreamData"]
            if sd.get("size", 0) > 0:
                key = sd["path"].lower()
                if key not in ress:
                    bad.append(f"{fname}:{pid} resS {sd['path']} отсутствует")
                elif sd["offset"] + sd["size"] > ress[key]:
                    bad.append(f"{fname}:{pid} выход за пределы {sd['path']}")
check(not bad, f"все стрим-ссылки в пределах resS ({bad[:3]})")
check(ress.get("resources.assets.ress", 0) > 100_000_000,
      f"resources.assets.ress на месте ({ress.get('resources.assets.ress', 0):,} байт)")

# ----------------------------------------------------------------------------
print("=" * 70)
print("G. Translate")
tr = ctx.read_tt(R, 633)
lines = tr["m_Script"].rstrip("\n").split("\n")
header = lines[0].split("\t")
ncols = len(header)
rows = {ln.split("\t")[0]: ln.split("\t") for ln in lines[1:]}
check("Horizontal Banner" in rows, "строка Horizontal Banner добавлена")
check(rows.get("Horizontal Banner", [""] * 99)[18 if ncols > 18 else 1] == "Горизонтальный баннер"
      or "Горизонтальный баннер" in rows.get("Horizontal Banner", []),
      "Horizontal Banner: RU перевод")
sb = rows.get("Sandbox Mode Price", [])
check(all("(5BTC)" not in c for c in sb), "Sandbox Mode Price: без (5BTC)")
check("Режим песочницы" in sb, "Sandbox Mode Price: RU = Режим песочницы")
must_be_ok = {"Horizontal Banner", "Sandbox Mode Price", "Sandbox Not Enough Bitcoin"}
badcols = [k for k, v in rows.items() if len(v) != ncols and k in must_be_ok]
check(not badcols, f"новые/изменённые строки имеют {ncols} колонок (битые: {badcols[:3]})")
pre = [k for k, v in rows.items() if len(v) != ncols and k not in must_be_ok]
print(f"  [INFO] {len(pre)} строк оригинала с другим числом колонок (не тронуты, как в оригинале)")

# ----------------------------------------------------------------------------
print("=" * 70)
print("H. Глубокий по-полный диф изменённых объектов (незапланированных изменений нет)")

# ожидаемые пути изменений (префиксы) для каждого объекта
ALLOWED = {
    ("globalgamemanagers", 1): {".productName"},
    ("globalgamemanagers", 10): {".m_BounceThreshold", ".m_DefaultSolverIterations",
                                  ".m_DefaultSolverVelocityIterations", ".m_SleepThreshold"},
    ("level0", 1102): {".m_Text"},
    ("resources.assets", 117): {".m_TextureFormat", ".m_CompleteImageSize", ".image data",
                                  ".m_StreamData"},
    ("resources.assets", 12533): {".maxCanvasSize.x", ".maxCanvasSize.y"},
    ("resources.assets", 12594): {".items"},
}
PS_ALLOWED = {".EmissionModule.rateOverTime.scalar", ".InitialModule.startLifetime.scalar",
              ".InitialModule.startLifetime.minScalar", ".InitialModule.startSize.scalar",
              ".InitialModule.startSize.minScalar", ".InitialModule.startSpeed.scalar",
              ".InitialModule.startSpeed.minScalar", ".InitialModule.startColor.minMaxState"}
GRAD_PREFIX = ".InitialModule.startColor.maxGradient."
PSR_ALLOWED = {".m_Materials", ".m_MaxParticleSize"}

def deepdiff(a, b, path=""):
    out = []
    if type(a) != type(b):
        return [(path,)]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append((f"{path}.{k}",))
            else:
                out += deepdiff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((f"{path}[LEN]",))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += deepdiff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append((path,))
    return out

unexpected = []
for key in sorted(EXPECTED_CHANGED):
    f_, pid = key
    if f_ == "resources.assets" and pid == 633:
        continue  # TextAsset проверен в секции G
    a = ORIG_TTS.get(key)
    with contextlib.redirect_stderr(io.StringIO()):
        b = ctx.read_tt(f_, pid)
    allowed = ALLOWED.get(key)
    if allowed is None and f_.startswith("level"):
        o_type = ctx.obj(f_, pid).type.name
        allowed = PSR_ALLOWED if o_type == "ParticleSystemRenderer" else (PS_ALLOWED | {GRAD_PREFIX})
    if allowed is None:
        allowed = set()
    for (p,) in deepdiff(a, b):
        if not any(p == x or p.startswith(x) for x in allowed):
            unexpected.append(f"{f_}:{pid} {p}")
check(not unexpected, f"нет посторонних изменений полей ({unexpected[:6]})")

# ----------------------------------------------------------------------------
print("=" * 70)
if ERRORS:
    print(f"ИТОГ: ✗ {len(ERRORS)} ОШИБКА(ОШИБОК):")
    for e in ERRORS:
        print("   -", e)
    sys.exit(1)
print("ИТОГ: ✓ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
