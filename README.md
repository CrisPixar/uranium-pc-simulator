# Uranium PC Simulator

Мод игры **Blue PC Simulator v1.9.1.11** (Unity 2021.3.45f1, IL2CPP).

| | |
|---|---|
| Название | Uranium PC Simulator |
| Пакет | `com.UraniumPCS.UraniumPCSimulator` |
| Иконка | не изменена (как в оригинале) |
| Разрешения | не изменены (как в оригинале) |

## Что изменено

1. **Имя игры и пакет** — приложение называется «Uranium PC Simulator», пакет `com.UraniumPCS.UraniumPCSimulator` (иконка и разрешения не тронуты).
2. **Принтеры Apson A3 512×512 (15 000 монет) и 1024×1024 (30 000 монет)** — новые товары в Маркете, разблокировка как у остального (5 BTC).
3. **Горизонтальный баннер** — новый товар в Маркете (100 монет). На него можно **бросить распечатанную картинку** — она повесится на полотно (компонент PaperFrame, как у рамок для картин). Вертикальные баннеры у PrintExpert не тронуты.
4. **Нормальная физика** — SolverIterations 6→10, VelocityIterations 1→4, BounceThreshold 2→1, SleepThreshold 0.005→0.003 (гравитация -9.81 не тронута).
5. **Термодинамика/кондиционер** — компьютеры остывают до температуры кондиционера **в 2 раза быстрее**; вместо снега кондиционер испускает **радужную гирлянду** (мерцающие огоньки всех цветов, материал ParticleFlare).
6. **Убрана чёрная сетка LCD-экранов** — текстура Grid переведена в полностью белую RGBA32 (шейдер Merge при белой сетке не изменяет картинку).
7. **Песочница бесплатна** — переключатель Sandbox больше не требует и не списывает 5 BTC.
8. **Без искажения цветов при печати** — печать использует нужное количество краски по каждому каналу CMYK вместо обрезания по остатку.
9. **Краски в 3 раза больше** — один картридж = 3 заправки (Printer..ctor: totalInk/remainingInk 1.0 → 3.0, патч и arm64, и arm32).
10. **Paint: максимальный холст 1024×1024** (было 256×256).
11. **Уровни красок в ПК** — уже есть в игре: в диалоге печати кнопка **Supply** показывает 4 индикатора CMYK.

## Сборка (GitHub Actions)

Пуш в `main` (или Manual run) запускает workflow `.github/workflows/build.yml`:
apktool b → zipalign → apksigner → артефакт + релиз **v1.9.1.11-uranium**.

Готовый APK: **Releases → v1.9.1.11-uranium → UraniumPCSimulator.apk**.

Подпись: `uranium.jks` (alias `uranium`, пароль `***REMOVED-KEYSTORE-PASS***`) — лежит в репозитории,
чтобы все сборки подписывались одинаково и ставились поверх друг друга.

## Как сделано (правки)

- `mod/patch_so.py` — патчи `libil2cpp.so` (arm64-v8a + armeabi-v7a):
  песочница (SceneSettings.SetSandbox: сравнение цены с 0 / отмена списания),
  краски ×3 (Printer..ctor), точная печать (Printer.PrintAvailableArea: клампы →
  needed), охлаждение ×2 (CPU.FixedUpdate: -10 → -5).
- `mod/patch_bundle.py` — правки `assets/bin/Data/data.unity3d` (UnityPy):
  Grid → белая, Paint 1024, PhysicsManager, productName, гирлянды в
  level1/3/4/5/6, клоны префабов принтеров 512/1024 и горизонтального баннера
  (+PaperFrame), новые ShopItem'ы, регистрация в Market, строка локализации
  «Horizontal Banner».
- `AndroidManifest.xml` — пакет `com.UraniumPCS.UraniumPCSimulator`.
- `res/values/strings.xml` — `app_name` = Uranium PC Simulator.

Исходное APK: Blue PC Simulator v1.9.1.11 (декомпиляция с разрешения создателя мода).

## Установка

Снести оригинал (другая подпись и другой пакет — впрочем, пакет другой, так что
можно ставить рядом), с-enable «Установка из неизвестных источников», поставить
`UraniumPCSimulator.apk`.
