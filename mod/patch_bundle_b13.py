#!/usr/bin/env python3
"""Uranium PC Simulator — правки ассетов b13.

1. КНОПКА [CH] СТАНОВИТСЯ ВИДИМОЙ.
   В b11/b12 CH_Btn (level0, GO 1344) клонировали с кнопки Return, у которой
   якорь m_AnchorMin=m_AnchorMax=(1,0) — правый нижний угол. У клона просто
   сменили знак X (+160 вместо -160), из-за чего кнопка уезжала на 160 px
   ЗА ПРАВЫЙ КРАЙ канваса (840x500) — её физически не было видно.
   Чиним: якорь (0,0) — левый нижний угол, позиция (160,40): зеркало Return.
   Текст «[CH]» -> «CH» (LocalizationTextBracket на объекте нет, скобки
   выводились как есть).

2. КЛИКИ ЛОВЯТСЯ ШТАТНОЙ UI-СИСТЕМОЙ, А НЕ RectangleContainsScreenPoint.
   Канвас меню — WORLD SPACE (он нарисован на мониторе внутри комнаты,
   Canvas.m_RenderMode = 2, камера = Camera 363). Поэтому проверка
   RectTransformUtility.RectangleContainsScreenPoint(rect, mouse, null),
   которую делали кейвы b11/b12, в принципе не могла работать: без камеры
   экранная точка не переводится в мировую плоскость канваса.
   Новая схема — без камеры и без гаданий:
     • CH_Btn.onClick        -> UraniumCHFlag.SetActive(true)  (+ клик-звук)
     • у заголовка меню (GO 125 «Title») появляется Button,
       его onClick        -> UraniumEggFlag.SetActive(true)
     • нативный код (mod/patch_b13.py) раз в кадр проверяет
       GameObject.Find(«UraniumCHFlag»/«UraniumEggFlag»); объект найден ==
       по кнопке кликнули (Find видит только активные объекты) -> флаг
       гасится и выполняется действие.
   Формат persistent call скопирован 1:1 с рабочих кнопок игры
   (level0 MonoBehaviour 957: SetActive(bool) + MenuManager.PlayClickSound).
   У кнопки заголовка m_Transition = None, чтобы надпись не меняла цвет.

3. НОВОГОДНЯЯ МУЗЫКА В МЕНЮ.
   Трек кодируется в PCM16 22 050 Гц моно, заворачивается в FSB5 и
   дописывается в assets/bin/Data/sharedassets0.resource; в
   sharedassets0.assets добавляется AudioClip, в level0 — AudioSource
   (loop + playOnAwake) НА ОБЪЕКТЕ «Snow». Snow включается/выключается
   нативным НГ-кодом, поэтому музыка играет ровно тогда, когда включено
   новогоднее меню, и глушится кнопкой CH — отдельного кода не нужно.

Запуск: python3 mod/patch_bundle_b13.py [дерево] [аудиофайл]
Идемпотентен: уже применённые шаги пропускаются.
"""
import os
import struct
import subprocess
import sys

import UnityPy
from UnityPy.files.ObjectReader import ObjectReader

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
AUDIO = sys.argv[2] if len(sys.argv) > 2 else None
BUNDLE = os.path.join(BASE, "assets/bin/Data/data.unity3d")
RESOURCE = os.path.join(BASE, "assets/bin/Data/sharedassets0.resource")

CLIP_NAME = "Uranium_NY_Menu"
FREQ = 22050
CHANNELS = 1
VOLUME = 0.55

CH_BTN_GO, CH_BTN_RT, CH_BTN_TEXT, CH_BTN_BUTTON = 1344, 1345, 1347, 1348
TITLE_GO, TITLE_RT, TITLE_TEXT = 125, 783, 1102
MENU_MANAGER = 1158            # MonoBehaviour MenuManager (PlayClickSound)
SNOW_GO = 141
SRC_AUDIOSOURCE = 475
SRC_AUDIOCLIP = 142
CH_FLAG_NAME = "UraniumCHFlag"
EGG_FLAG_NAME = "UraniumEggFlag"

FSB_FREQ = {8000: 1, 11000: 2, 11025: 3, 16000: 4, 22050: 5,
            24000: 6, 32000: 7, 44100: 8, 48000: 9, 96000: 10}


# ───────────────────────── FSB5 (PCM16) ─────────────────────────
def build_fsb5(pcm: bytes, freq: int, channels: int):
    """Однопотоковый FSB5 v1, mode=2 (PCM16), данные с 96-го байта."""
    nsamples = len(pcm) // (2 * channels)
    data = pcm + b"\x00" * (-len(pcm) % 32)
    sample = ((FSB_FREQ[freq] << 1) | ((channels - 1) << 5) | (nsamples << 34))
    shdr = struct.pack("<Q", sample)
    shdr += b"\x00" * (36 - len(shdr))
    head = b"FSB5" + struct.pack("<IIIIII", 1, 1, len(shdr), 0, len(data), 2)
    head += b"\x00" * 32
    assert len(head) == 60, len(head)
    return head + shdr + data, nsamples


def decode_audio(path):
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-i", path,
           "-ac", str(CHANNELS), "-ar", str(FREQ),
           "-af", "loudnorm=I=-19:TP=-2:LRA=11",
           "-f", "s16le", "-acodec", "pcm_s16le", "-"]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


# ───────────────────────── UnityPy-хелперы ─────────────────────────
def new_object(sf, src_pid, pid, tree=None, raw=None):
    src = sf.objects[src_pid]
    obj = ObjectReader(sf, src.reader, pid, src.type_id, src.serialized_type,
                       src.class_id, src.type, src.byte_start, src.byte_size,
                       src.is_destroyed, src.is_stripped)
    if raw is not None:
        obj.set_raw_data(raw)
    else:
        obj.save_typetree(tree)
    sf.objects[pid] = obj
    return obj


def find_go(sf, name):
    for pid, o in sf.objects.items():
        if o.type.name == "GameObject" and o.read_typetree()["m_Name"] == name:
            return pid
    return None


def find_clip(sf, name):
    for pid, o in sf.objects.items():
        if o.type.name == "AudioClip":
            try:
                if o.read_typetree()["m_Name"] == name:
                    return pid
            except Exception:
                pass
    return None


def ustr(s: bytes) -> bytes:
    return struct.pack("<i", len(s)) + s + b"\x00" * (-len(s) % 4)


def pptr(pid, file_id=0) -> bytes:
    return struct.pack("<iq", file_id, pid)


def call_setactive(target_go, value=True) -> bytes:
    """persistent call: <GameObject>.SetActive(bool) — формат как у игры."""
    return (pptr(target_go)
            + ustr(b"")                                   # m_TargetAssemblyTypeName
            + ustr(b"SetActive")
            + struct.pack("<i", 6)                        # PersistentListenerMode.Bool
            + pptr(0)                                     # m_ObjectArgument
            + ustr(b"UnityEngine.Object, UnityEngine")
            + struct.pack("<if", 0, 0.0)                   # m_IntArgument, m_FloatArgument
            + ustr(b"")                                   # m_StringArgument
            + struct.pack("<i", 1 if value else 0)        # m_BoolArgument
            + struct.pack("<i", 2))                       # m_CallState = RuntimeOnly


def call_clicksound() -> bytes:
    return (pptr(MENU_MANAGER)
            + ustr(b"MenuManager, Assembly-CSharp")
            + ustr(b"PlayClickSound")
            + struct.pack("<i", 0)                        # EventDefined
            + pptr(0) + ustr(b"")
            + struct.pack("<ii", 0, 0)
            + ustr(b"") + struct.pack("<ii", 0, 2))


def button_raw(src_raw: bytes, go_pid: int, graphic_pid: int,
               calls: list, transition=None) -> bytes:
    """Пересобирает Button: шапка от образца + свой список onClick."""
    head_end = src_raw.find(b"Disabled") + len(b"Disabled")
    prefix = bytearray(src_raw[:head_end + 4 + 12])       # + m_Interactable + m_TargetGraphic
    struct.pack_into("<iq", prefix, 0, 0, go_pid)         # m_GameObject
    struct.pack_into("<iq", prefix, head_end + 4, 0, graphic_pid)
    if transition is not None:
        struct.pack_into("<i", prefix, 88, transition)    # m_Transition
    return bytes(prefix) + struct.pack("<i", len(calls)) + b"".join(calls)


def make_flag(level0, name, parent_rt, go_src, rt_src):
    """Скрытый объект-флажок: GameObject(неактивный) + RectTransform."""
    pid = max(level0.objects)
    go_pid, rt_pid = pid + 1, pid + 2
    rt = level0.objects[rt_src].read_typetree()
    rt.update({
        "m_GameObject": {"m_FileID": 0, "m_PathID": go_pid},
        "m_Children": [],
        "m_Father": {"m_FileID": 0, "m_PathID": parent_rt},
        "m_AnchorMin": {"x": 0.0, "y": 0.0},
        "m_AnchorMax": {"x": 0.0, "y": 0.0},
        "m_AnchoredPosition": {"x": 0.0, "y": 0.0},
        "m_SizeDelta": {"x": 0.0, "y": 0.0},
        "m_LocalPosition": {"x": 0.0, "y": 0.0, "z": 0.0},
    })
    go = level0.objects[go_src].read_typetree()
    go.update({
        "m_Component": [{"component": {"m_FileID": 0, "m_PathID": rt_pid}}],
        "m_Layer": 5,
        "m_Name": name,
        "m_Tag": 0,
        "m_IsActive": False,
    })
    new_object(level0, go_src, go_pid, go)
    new_object(level0, rt_src, rt_pid, rt)
    parent = level0.objects[parent_rt].read_typetree()
    parent["m_Children"].append({"m_FileID": 0, "m_PathID": rt_pid})
    level0.objects[parent_rt].save_typetree(parent)
    return go_pid


def main():
    env = UnityPy.load(BUNDLE)
    bf = list(env.files.values())[0]
    level0 = bf.files["level0"]
    sa0 = bf.files["sharedassets0.assets"]

    # ── 1. CH_Btn: якорь и позиция ───────────────────────────────
    rt = level0.objects[CH_BTN_RT].read_typetree()
    if rt["m_AnchorMin"]["x"] != 0.0:
        rt["m_AnchorMin"] = {"x": 0.0, "y": 0.0}
        rt["m_AnchorMax"] = {"x": 0.0, "y": 0.0}
        rt["m_AnchoredPosition"] = {"x": 160.0, "y": 40.0}
        level0.objects[CH_BTN_RT].save_typetree(rt)
        print("[1] CH_Btn: якорь (1,0)->(0,0), позиция (160,40) — кнопка "
              "больше не за краем экрана")
    else:
        print("[1] CH_Btn: позиция уже исправлена")

    o = level0.objects[CH_BTN_TEXT]
    raw = bytearray(o.get_raw_data())
    if raw.endswith(b"\x04\x00\x00\x00[CH]"):
        raw[-8:] = b"\x02\x00\x00\x00CH\x00\x00"
        o.set_raw_data(bytes(raw))
        print("[2] Текст кнопки: «[CH]» -> «CH»")
    else:
        print("[2] Текст кнопки уже «CH»")

    # ── 3. флажки + перепрошивка onClick ─────────────────────────
    ch_flag = find_go(level0, CH_FLAG_NAME)
    if ch_flag is None:
        ch_flag = make_flag(level0, CH_FLAG_NAME, CH_BTN_RT,
                            go_src=CH_BTN_GO, rt_src=CH_BTN_RT)
        src = level0.objects[CH_BTN_BUTTON].get_raw_data()
        level0.objects[CH_BTN_BUTTON].set_raw_data(
            button_raw(src, CH_BTN_GO, CH_BTN_TEXT,
                       [call_setactive(ch_flag), call_clicksound()]))
        print(f"[3] CH_Btn.onClick -> {CH_FLAG_NAME}({ch_flag}).SetActive(true)"
              " + клик-звук (было MainMenu.LoadScene(0), из-за которого "
              "ломалось меню)")
    else:
        print(f"[3] {CH_FLAG_NAME} уже есть ({ch_flag})")

    egg_flag = find_go(level0, EGG_FLAG_NAME)
    if egg_flag is None:
        egg_flag = make_flag(level0, EGG_FLAG_NAME, TITLE_RT,
                             go_src=CH_BTN_GO, rt_src=CH_BTN_RT)
        btn_pid = max(level0.objects) + 1
        raw = button_raw(level0.objects[CH_BTN_BUTTON].get_raw_data(),
                         TITLE_GO, TITLE_TEXT, [call_setactive(egg_flag)],
                         transition=0)
        new_object(level0, CH_BTN_BUTTON, btn_pid, raw=raw)
        go = level0.objects[TITLE_GO].read_typetree()
        go["m_Component"].append({"component": {"m_FileID": 0,
                                                "m_PathID": btn_pid}})
        level0.objects[TITLE_GO].save_typetree(go)
        print(f"[4] На заголовок меню повешен Button {btn_pid} -> "
              f"{EGG_FLAG_NAME}({egg_flag}).SetActive(true) — 10 кликов по "
              f"«Uranium PC Simulator» = пасхалка")
    else:
        print(f"[4] {EGG_FLAG_NAME} уже есть ({egg_flag})")

    # ── 5. музыка ────────────────────────────────────────────────
    clip_pid = find_clip(sa0, CLIP_NAME)
    if clip_pid is None:
        if not AUDIO:
            print("[5] аудиофайл не передан — музыка пропущена")
        else:
            pcm = decode_audio(AUDIO)
            fsb, nsamples = build_fsb5(pcm, FREQ, CHANNELS)
            offset = os.path.getsize(RESOURCE)
            assert offset % 32 == 0, offset
            with open(RESOURCE, "ab") as f:
                f.write(fsb)
            print(f"[5] sharedassets0.resource: +{len(fsb):,} Б FSB5 "
                  f"(PCM16 {FREQ} Гц моно, {nsamples / FREQ:.1f} с) "
                  f"со смещения {offset}")
            tree = sa0.objects[SRC_AUDIOCLIP].read_typetree()
            tree.update({
                "m_Name": CLIP_NAME, "m_LoadType": 0, "m_Channels": CHANNELS,
                "m_Frequency": FREQ, "m_BitsPerSample": 16,
                "m_Length": nsamples / FREQ, "m_IsTrackerFormat": False,
                "m_Ambisonic": False, "m_SubsoundIndex": 0,
                "m_PreloadAudioData": True, "m_LoadInBackground": False,
                "m_Legacy3D": False, "m_CompressionFormat": 0,
                "m_Resource": {"m_Source": "sharedassets0.resource",
                               "m_Offset": offset, "m_Size": len(fsb)},
            })
            clip_pid = max(sa0.objects) + 1
            new_object(sa0, SRC_AUDIOCLIP, clip_pid, tree)
            print(f"    AudioClip «{CLIP_NAME}» = sharedassets0:{clip_pid}")
    else:
        print(f"[5] AudioClip «{CLIP_NAME}» уже есть ({clip_pid})")

    # ── 6. AudioSource на Snow ───────────────────────────────────
    go = level0.objects[SNOW_GO].read_typetree()
    have = any(level0.objects[c["component"]["m_PathID"]].type.name
               == "AudioSource" for c in go["m_Component"]
               if c["component"]["m_PathID"] in level0.objects)
    if clip_pid is not None and not have:
        src = level0.objects[SRC_AUDIOSOURCE].read_typetree()
        src.update({
            "m_GameObject": {"m_FileID": 0, "m_PathID": SNOW_GO},
            "m_Enabled": 1,
            "m_audioClip": {"m_FileID": 2, "m_PathID": clip_pid},
            "m_PlayOnAwake": True, "Loop": True,
            "m_Volume": VOLUME, "Priority": 200,
        })
        as_pid = max(level0.objects) + 1
        new_object(level0, SRC_AUDIOSOURCE, as_pid, src)
        go["m_Component"].append({"component": {"m_FileID": 0,
                                                "m_PathID": as_pid}})
        level0.objects[SNOW_GO].save_typetree(go)
        print(f"[6] AudioSource {as_pid} на «Snow» (loop, playOnAwake, "
              f"volume {VOLUME})")
    elif have:
        print("[6] AudioSource на «Snow» уже есть")

    out = env.file.save(packer="original")
    with open(BUNDLE, "wb") as f:
        f.write(out)
    print(f"[7] data.unity3d записан: {len(out):,} Б")


if __name__ == "__main__":
    main()
