#!/usr/bin/env python3
"""Uranium PC Simulator — нативные патчи b13 (поверх b12).

Что чинит/делает (arm64-v8a + armeabi-v7a):

1. МИР/СОХРАНЕНИЕ НЕ ГРУЗЯТСЯ, ИГРА ЗАМИРАЕТ (главный баг b11/b12).
   Причина: head-хук `MainMenu.LoadScene(int)` (arm64 @0x7e50f8) уводил в кейв
   0x85e0e0, который при индексе сцены < 1 вызывал PlayerPrefs.GetInt/SetInt
   и НЕ СОХРАНЯЛ w1 — то есть портил САМ АРГУМЕНТ (номер сцены).
   Unity получал мусор («Scene with build index: 1543503875 couldn't be
   loaded»), корутина MainMenu.LoadAsync падала в NullReferenceException,
   экран загрузки оставался висеть → «замораживается игра».
   Кнопка [CH] в b12 как раз и была повешена на LoadScene(0) → каждый её
   нажим ломал меню, а любой последующий вход в мир/сохранение уже не работал.
   Фикс: хук СНЯТ ПОЛНОСТЬЮ, оригинальный пролог восстановлен, кейв обнулён.
   CH теперь вообще не трогает загрузку сцен (см. п.3).

2. ПАСХАЛКА BITCOIN SEARCHER ПЕРЕЕХАЛА НА ЗАГОЛОВОК МЕНЮ.
   Было: 10 кликов по строке Print Master в ачивках, 100–1000 BTC.
   Стало: 10 кликов по надписи «Uranium PC Simulator» в главном меню →
   случайно 100–10000 BTC, максимум 2 раза, достижение Bitcoin Searcher
   выдаётся при первом срабатывании.
   Клик ловится ШТАТНОЙ UI-системой: у заголовка теперь есть Button,
   который зажигает скрытый объект UraniumEggFlag, а кейв раз в кадр
   проверяет GameObject.Find("UraniumEggFlag") и гасит его обратно.
   Прежняя проверка RectangleContainsScreenPoint(rect, мышь, null) не могла
   работать в принципе: канвас меню — World Space (нарисован на мониторе
   в комнате), без камеры экранная точка в его плоскость не переводится.

3. КНОПКА [CH] РАБОТАЕТ И ВИДНА.
   Было: onClick → MainMenu.LoadScene(0) (краш, см. п.1), а сама кнопка
   стояла с якорем правого нижнего угла и смещением +160 по X, то есть
   ЗА ПРЕДЕЛАМИ ЭКРАНА (её просто не было видно). Позиция чинится в бандле
   (mod/patch_bundle_b13.py), onClick очищается.
   Стало: onClick кнопки зажигает скрытый объект UraniumCHFlag, кейв
   EventSystem.Update видит его, гасит и выполняет:
     UraniumNY = !UraniumNY;  UraniumCH = UraniumNY ? 1 : 2;
     Snow.SetActive(UraniumNY)  — снег и НГ-музыка включаются/выключаются
     СРАЗУ, без перезагрузки сцены.
   Смысл UraniumCH: 0 — авто (25.12–10.01 или 1% шанс), 1 — всегда НГ,
   2 — никогда НГ. Поэтому в сезон 25.12–10.01 кнопка теперь тоже работает
   (раньше CH умел только «включить», а в сезон и так было включено).

4. НГ-МУЗЫКА в меню: AudioSource висит на объекте Snow (см. бандл), поэтому
   включается тем же SetActive, что и снег — отдельного кода не нужно.

Запуск: python3 mod/patch_b13.py [дерево_apktool]   (по умолчанию текущее)
Идемпотентен: повторный запуск ничего не меняет.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asmlib import Asm64, Asm32, a64, a32          # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
SO64 = os.path.join(BASE, "lib/arm64-v8a/libil2cpp.so")
SO32 = os.path.join(BASE, "lib/armeabi-v7a/libil2cpp.so")

# ───────────────────────── адреса arm64 ──────────────────────────
K64 = dict(
    NEWSTR=0x6FBCA8,          # il2cpp::vm::String::New(char*)
    GETINT=0x17C8614,         # PlayerPrefs.GetInt(string,int)
    SETINT=0x17C8580,         # PlayerPrefs.SetInt(string,int)
    FIND=0x17D00C0,           # GameObject.Find(string)
    SETACTIVE=0x17CFD04,      # GameObject.SetActive(bool)
    GO_TR=0x17CFC48,          # GameObject.get_transform
    COMP_TR=0x17CD67C,        # Component.get_transform
    MBD=0x180294C,            # Input.GetMouseButtonDown(int)
    MPOS=0x1803E54,           # Input.get_mousePosition(&out)
    RCSP=0x196A1E4,           # RectTransformUtility.RectangleContainsScreenPoint
    RAND=0x17B8238,           # Random.Range(int,int)
    BTC_GET=0x7B2D14, FS2F=0x816874, F2FS=0x816884,
    BTC_SET=0x7B2D6C, BTC_UPD=0x7B3030,
    CO_INST=0x7B48CC, CO_ACH=0x7B4BA0, ACHIEVE=0x81C064,
)
S64 = dict(CH=0x85DD0C, NY=0x85DD18, SNOW=0x85DD24,
           EGGCLICKS=0x85DFB4, EGGUSES=0x85DFC8, SEARCHER=0x85DFD8,
           CHFLAG=0x85E300, EGGFLAG=0x85E310)

LS64_HOOK = 0x7E50F8          # head-хук MainMenu.LoadScene(int)
LS64_CAVE = 0x85E0E0          # его кейв (обнуляем)
EGG64 = 0x85DE44              # начало переписываемого блока в кейве es64
EGG64_END = 0x85DF84          # дальше — `add sp,#0x10` и эпилог 0x85df88
ES64_EPI = 0x85DF88
CH64 = 0x85E180               # новый кейв: обработка кнопки CH
NY64_EXT = 0x85E2A0           # новый кейв: 3 состояния UraniumCH
NY64_PATCH = 0x85DC44         # `cbnz w0,#0x85dcc4` -> `b NY64_EXT`
NY64_ON = 0x85DCC4            # ветка «НГ включён»
NY64_OFF = 0x85DCAC           # ветка «НГ выключен»
NY64_AUTO = 0x85DC48          # ветка «по дате/рандому»

# ───────────────────────── адреса arm32 ──────────────────────────
K32 = dict(
    NEWSTR=0x415F04, GETINT=0x1873B50, SETINT=0x1873AA0,
    FIND=0x187D118, SETACTIVE=0x187CC88, GO_TR=0x187CB9C, COMP_TR=0x1879E58,
    MBD=0x18C9068, MPOS=0x18CAD44, RCSP=0x1AAE6A0, RAND=0x185F1B0,
    MM_INST=0x4DFBB8,
    BTC_GET=0x4A26DC, FS2F=0x5222BC, F2FS=0x5222C4,
    BTC_SET=0x4A2750, BTC_UPD=0x4A2AD4,
    CO_INST=0x4A48B0, CO_ACH=0x4A4BFC, ACHIEVE=0x5295E8,
)
S32 = dict(CH=0x1C6A38C, NY=0x1C6A398, SNOW=0x1C6A3A4,
           EGGCLICKS=0x1C80C40, EGGUSES=0x1C80C54, SEARCHER=0x1C80C64,
           CHFLAG=0x1C80E00, EGGFLAG=0x1C80E10)

EGG32 = 0x1C80A8C             # переписываемый блок в кейве es32
EGG32_END = 0x1C80C14         # эпилог кейва es32
POOL32 = 0x1C80C90            # литеральный пул (0x1c80c78..0x1c80c8c заняты)
CH32 = 0x1C80D00
CH32_POOL = 0x1C80DE0
NY32_EXT = 0x1C6A3B8
NY32_PATCH = 0x1C6A2CC        # `bne #0x1c6a348` -> `b NY32_EXT`
NY32_ON = 0x1C6A348
NY32_OFF = 0x1C6A338
NY32_AUTO = 0x1C6A2D0


def put(data, va, blob, what, expect=None):
    if data[va:va + len(blob)] == blob:
        print(f"  [skip] {what} @0x{va:x}")
        return
    if expect is not None and data[va:va + len(expect)] != expect:
        raise RuntimeError(f"{what} @0x{va:x}: ожидалось "
                           f"{expect.hex(' ')}, найдено "
                           f"{data[va:va + len(expect)].hex(' ')}")
    data[va:va + len(blob)] = blob
    print(f"  [ ok ] {what} @0x{va:x} ({len(blob)} Б)")


# ══════════════════════════════ arm64 ══════════════════════════════
def patch64(d):
    print("== arm64-v8a ==")
    K, S = K64, S64

    # ---- 1. снять хук LoadScene, восстановить пролог ----------------
    orig = d[LS64_CAVE + 0x40:LS64_CAVE + 0x48]        # 2 «протруженные» инстр.
    want = a64("str x22, [sp, #-0x30]!", 0) + a64("stp x21, x20, [sp, #0x10]", 0)
    if orig != want and d[LS64_HOOK:LS64_HOOK + 8] != want:
        raise RuntimeError("не нашёл оригинальный пролог LoadScene в кейве")
    put(d, LS64_HOOK, want, "LoadScene: хук снят, пролог восстановлен")
    put(d, LS64_CAVE, b"\x00" * 0x60, "кейв ls64 обнулён")

    # ---- 2. пасхалка на заголовке меню ------------------------------
    e = Asm64(EGG64)
    e(
        # Button на заголовке зажигает UraniumEggFlag -> значит, был клик
        f"LIT x0, 0x{S['EGGFLAG']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",             # Find видит только активные
        "cbz x0, #LCH",
        "mov w1, wzr",
        f"bl #0x{K['SETACTIVE']:x}",        # гасим флажок до следующего клика
        f"LIT x0, 0x{S['EGGCLICKS']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x20, x0",
        "mov w1, wzr",
        f"bl #0x{K['GETINT']:x}",
        "add w21, w0, #1",
        "mov w1, w21",
        "mov x0, x20",
        f"bl #0x{K['SETINT']:x}",           # clicks++
        "cmp w21, #0xa",
        "b.lt #LCH",
        "mov x0, x20",
        "mov w1, wzr",
        f"bl #0x{K['SETINT']:x}",           # clicks = 0
        f"LIT x0, 0x{S['EGGUSES']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x20, x0",
        "mov w1, wzr",
        f"bl #0x{K['GETINT']:x}",
        "cmp w0, #2",
        "b.ge #LCH",                        # больше 2 раз нельзя
        "mov w21, w0",
        "mov w0, #0x64",                    # 100
        "movz w1, #0x2711",                 # 10001 (Range — верхняя граница искл.)
        f"bl #0x{K['RAND']:x}",
        "mov w22, w0",
        "mov x0, xzr",
        f"bl #0x{K['BTC_GET']:x}",
        f"bl #0x{K['FS2F']:x}",
        "scvtf s1, w22",
        "fadd s0, s0, s1",
        f"bl #0x{K['F2FS']:x}",
        f"bl #0x{K['BTC_SET']:x}",
        "mov x0, xzr",
        f"bl #0x{K['BTC_UPD']:x}",
        "add w21, w21, #1",
        "mov w1, w21",
        "mov x0, x20",
        f"bl #0x{K['SETINT']:x}",           # uses++
        "cmp w21, #1",
        "b.ne #LCH",                        # достижение — при первом срабатывании
        f"bl #0x{K['CO_INST']:x}",
        "cbz x0, #LCH",
        "mov x21, x0",
        f"LIT x0, 0x{S['SEARCHER']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x1, x0",
        "mov x0, x21",
        "mov x2, xzr",
        f"bl #0x{K['CO_ACH']:x}",
        "cbz x0, #LCH",
        f"bl #0x{K['ACHIEVE']:x}",
        "LCH:",
        f"b #0x{CH64:x}",
    )
    blob = e.assemble()
    if len(blob) > EGG64_END - EGG64:
        raise RuntimeError(f"egg64 не влез: {len(blob)} > {EGG64_END - EGG64}")
    blob += a64("nop", 0) * ((EGG64_END - EGG64 - len(blob)) // 4)
    blob += a64(f"b #0x{ES64_EPI:x}", EGG64_END)       # затираем `add sp,#0x10`
    put(d, EGG64, blob, "es64: пасхалка -> заголовок меню")

    # ---- 3. кейв кнопки CH ------------------------------------------
    c = Asm64(CH64)
    c(
        # CH_Btn.onClick зажигает UraniumCHFlag -> значит, кнопку нажали
        f"LIT x0, 0x{S['CHFLAG']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cbz x0, #Lend",
        "mov w1, wzr",
        f"bl #0x{K['SETACTIVE']:x}",        # гасим флажок
        f"LIT x0, 0x{S['NY']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov x20, x0",
        "mov w1, wzr",
        f"bl #0x{K['GETINT']:x}",
        "cmp w0, wzr",
        "cset w21, eq",                     # w21 = новое состояние НГ
        "mov w1, w21",
        "mov x0, x20",
        f"bl #0x{K['SETINT']:x}",
        f"LIT x0, 0x{S['CH']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov w8, #2",
        "cmp w21, #0",
        "mov w1, #1",
        "csel w1, w1, w8, ne",              # CH = НГ ? 1 : 2
        f"bl #0x{K['SETINT']:x}",
        f"LIT x0, 0x{S['SNOW']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cbz x0, #Lend",
        "mov w1, w21",
        f"bl #0x{K['SETACTIVE']:x}",        # снег + НГ-музыка сразу
        "Lend:",
        f"b #0x{ES64_EPI:x}",
    )
    put(d, CH64, c.assemble(), "кейв CH64 (клик по кнопке CH)")
    put(d, S64["CHFLAG"], b"UraniumCHFlag\x00\x00\x00", "строка UraniumCHFlag")
    put(d, S64["EGGFLAG"], b"UraniumEggFlag\x00\x00", "строка UraniumEggFlag")

    # ---- 4. три состояния UraniumCH в ny64 --------------------------
    n = Asm64(NY64_EXT)
    n(
        "cmp w0, #1",
        f"b.eq #0x{NY64_ON:x}",
        "cmp w0, #2",
        f"b.eq #0x{NY64_OFF:x}",
        f"b #0x{NY64_AUTO:x}",
    )
    put(d, NY64_EXT, n.assemble(), "кейв ny64-ext (CH: 0 авто / 1 вкл / 2 выкл)")
    put(d, NY64_PATCH, a64(f"b #0x{NY64_EXT:x}", NY64_PATCH),
        "ny64: cbnz -> ny64-ext",
        expect=a64(f"cbnz w0, #0x{NY64_ON:x}", NY64_PATCH))


# ══════════════════════════════ arm32 ══════════════════════════════
def patch32(d):
    print("== armeabi-v7a ==")
    K, S = K32, S32

    e = Asm32(EGG32, POOL32)
    e(
        f"LIT r0, 0x{S['EGGFLAG']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0", "beq #LCH",
        "mov r1, #0",
        f"bl #0x{K['SETACTIVE']:x}",
        f"LIT r0, 0x{S['EGGCLICKS']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r6, r0",
        "mov r1, #0",
        f"bl #0x{K['GETINT']:x}",
        "add r5, r0, #1",
        "mov r1, r5",
        "mov r0, r6",
        f"bl #0x{K['SETINT']:x}",
        "cmp r5, #0xa",
        "blt #LCH",
        "mov r0, r6",
        "mov r1, #0",
        f"bl #0x{K['SETINT']:x}",
        f"LIT r0, 0x{S['EGGUSES']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r6, r0",
        "mov r1, #0",
        f"bl #0x{K['GETINT']:x}",
        "cmp r0, #2",
        "bge #LCH",
        "mov r5, r0",
        "mov r0, #0x64",
        "IMM r1, 0x2711",
        f"bl #0x{K['RAND']:x}",
        "vmov s16, r0",
        "vcvt.f32.s32 s16, s16",
        "sub sp, sp, #8",
        "mov r0, sp",
        f"bl #0x{K['BTC_GET']:x}",
        "ldr r0, [sp]",
        "ldr r1, [sp, #4]",
        f"bl #0x{K['FS2F']:x}",
        "vmov s17, r0",
        "vadd.f32 s16, s17, s16",
        "vmov r1, s16",
        "mov r0, sp",
        f"bl #0x{K['F2FS']:x}",
        "ldr r0, [sp]",
        "ldr r1, [sp, #4]",
        f"bl #0x{K['BTC_SET']:x}",
        "add sp, sp, #8",
        f"bl #0x{K['BTC_UPD']:x}",
        "add r5, r5, #1",
        "mov r1, r5",
        "mov r0, r6",
        f"bl #0x{K['SETINT']:x}",
        "cmp r5, #1",
        "bne #LCH",
        f"bl #0x{K['CO_INST']:x}",
        "cmp r0, #0", "beq #LCH",
        "mov r5, r0",
        f"LIT r0, 0x{S['SEARCHER']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r1, r0",
        "mov r2, #0",
        "mov r0, r5",
        f"bl #0x{K['CO_ACH']:x}",
        "cmp r0, #0", "beq #LCH",
        f"bl #0x{K['ACHIEVE']:x}",
        "LCH:",
        f"b #0x{CH32:x}",
    )
    blob, pool = e.assemble()
    if len(blob) > EGG32_END - EGG32:
        raise RuntimeError(f"egg32 не влез: {len(blob)}")
    blob += a32("nop", 0) * ((EGG32_END - EGG32 - len(blob)) // 4)
    if EGG32 + len(blob) > POOL32:
        raise RuntimeError("es32: код наехал на литеральный пул")
    put(d, EGG32, blob, "es32: пасхалка -> заголовок меню")
    put(d, POOL32, pool, "литеральный пул es32")

    c = Asm32(CH32, CH32_POOL)
    c(
        f"LIT r0, 0x{S['CHFLAG']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0", "beq #Lend",
        "mov r1, #0",
        f"bl #0x{K['SETACTIVE']:x}",
        f"LIT r0, 0x{S['NY']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "mov r6, r0",
        "mov r1, #0",
        f"bl #0x{K['GETINT']:x}",
        "cmp r0, #0",
        "moveq r5, #1",
        "movne r5, #0",
        "mov r1, r5",
        "mov r0, r6",
        f"bl #0x{K['SETINT']:x}",
        f"LIT r0, 0x{S['CH']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        "cmp r5, #0",
        "movne r1, #1",
        "moveq r1, #2",
        f"bl #0x{K['SETINT']:x}",
        f"LIT r0, 0x{S['SNOW']:x}",
        f"bl #0x{K['NEWSTR']:x}",
        f"bl #0x{K['FIND']:x}",
        "cmp r0, #0", "beq #Lend",
        "mov r1, r5",
        f"bl #0x{K['SETACTIVE']:x}",
        "Lend:",
        f"b #0x{EGG32_END:x}",
    )
    blob, pool = c.assemble()
    if CH32 + len(blob) > CH32_POOL:
        raise RuntimeError("CH32: код наехал на литеральный пул")
    put(d, CH32, blob, "кейв CH32 (клик по кнопке CH)")
    put(d, CH32_POOL, pool, "литеральный пул CH32")
    put(d, S32["CHFLAG"], b"UraniumCHFlag\x00\x00\x00", "строка UraniumCHFlag (arm32)")
    put(d, S32["EGGFLAG"], b"UraniumEggFlag\x00\x00", "строка UraniumEggFlag (arm32)")

    n = Asm32(NY32_EXT, NY32_EXT + 0x40)
    n(
        "cmp r0, #1",
        f"beq #0x{NY32_ON:x}",
        "cmp r0, #2",
        f"beq #0x{NY32_OFF:x}",
        f"b #0x{NY32_AUTO:x}",
    )
    blob, _ = n.assemble()
    put(d, NY32_EXT, blob, "кейв ny32-ext (CH: 0 авто / 1 вкл / 2 выкл)")
    put(d, NY32_PATCH, a32(f"b #0x{NY32_EXT:x}", NY32_PATCH),
        "ny32: bne -> ny32-ext",
        expect=a32(f"bne #0x{NY32_ON:x}", NY32_PATCH))


def main():
    for path, fn in ((SO64, patch64), (SO32, patch32)):
        print(f"--- {path}")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        fn(data)
        with open(path, "wb") as f:
            f.write(bytes(data))
    print("Готово.")


if __name__ == "__main__":
    main()
