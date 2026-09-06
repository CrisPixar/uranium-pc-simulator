# v4: результаты реконструкции (2026-09-06)

## Ключевые открытия

### 1. Краш PrintExpert (b5) — диагноз подтверждён
- Ориг. ветка «неверный размер»: 0x867480 → String.Format(литералы 0x2244000+0x520 / 0x2224000+0x230 / 0x224a000+0x860) bl 0xfd57bc → msg=x20 → alertText.text (вирт. 0x5e8) → ret 0x867508.
- v3-патч 0x8674AC затирал это и делал tail `b 0x7E23B8` (Main.FadeText) → StopCoroutine("Fade") → SEGV. Плюс stale-LR цикл.
- **v4-фикс:** в блоке 0x8674AC восстановить ОРИГИНАЛЬНУЮ логику, но писать в **fileNameText [x19+0x38]** (Text 11583, валиден в v3-бандле), НЕ alertText (он теперь TextureLoader 13747!). Паттерн: x0=[x19+0x38]; null-check (0x17d3c10); klass=[x0]; x3=[klass+0x5e8]; x2=[klass+0x5f0]; blr x3.
- Также нейтрализовать ориг. «не хватает денег» 0x86751C (adrp 0x2246000+0x940 литерал; mov x0,x21; … b 0x7E23B8 FadeText!) → тот же fileNameText-путь.
- arm32: аналогичные адреса в dump32 (найти при реализации).

### 2. Заголовок меню (Blue PC Simulator)
- Литерал заголовка В ПРИНЦИПЕ ОДИН: `<color=cyan>Blue</color> <color=orange>PC</color> Simulator` @metadata 0x1E4A1 (заменён в v3 на Uranium). Проверено: в оригинале только 1 вхождение `<color=cyan>`.
- MainMenu.Start НЕ ставит title. **MainMenu.Blinking (0x7E4BDC)** — InvokeRepeating(Start 0x7e42a8..0x7e42bc bl 0x17d2194, delay 0.5) — ставит title.text = литерал из слота-обёртки **0x2259000+0x218** (init bl 0x6b26fc + ldr x1,[x9]). Слот ≠ stringliteral.json-адресу 0x22D2028 (там один слот на литерал, а usage-слотов много) — почти наверняка это ТОТ ЖЕ литерал ⇒ на b5 Blinking уже пишет Uranium.
- **Вывод: жалоба «заголовок откатывается» скорее всего с предыдущего релиза (v1.9.1.11-uranium = v2-коммит a376331, где литерл ещё не был патчен — патч литерала появился только в v3/b5).** Уточнить у юзера версию. Запасной фикс: Blinking-обёртку 0x2259218 → 0x22D2028 (наш литерал) — безопасно в любом случае.
- Main.FadeText трогать НЕЛЬЗЯ (мина). title-поле MainMenu @0x18.

### 3. Принтеры в маркете
- Market (App «Daily Market», окно: Image/Scroll View/Title«Daily Market»/Close): Market.Start 0x853AA8 — цикл items[] БЕЗ УСЛОВИЙ (Instantiate(selectionPrefab 11257, page=Content 10899) → ShopUI.Init(item) → add_OnBuy). Фильтра НЕТ. randomItems-цикл по random.inStock (List<int>.Contains 0xc42c94), у нас randomItems=0 → skip.
- Content (GO 875, RT 10899): **HorizontalLayoutGroup (12421, spacing 20) + ContentSizeFitter (12411, H-fit Min)**; ScrollRect (11820): horizontal=1, vertical=0. Горизонтальная лента, скролл вбок.
- **b5-APK data.unity3d ПОБАЙТОВО == репо v3** (включая карточки 13706/13739/13754 в items[]). v2-бандл тоже имел карточки (btc=5.0). Оригинал: items=53, randomItems=0.
- items[] (56): [0..2] Apson 32/64/128, [3..52] остальное, [53] Lamp1, [54] Lamp2, [55-57] НАШИ: Apson512(13706, price 15000, btc 0), Apson1024(13739, 30000, 0), {Horizontal Banner}(13754, 100, 0).
- ShopUI.Init 0x826F70: не скрывает карточки; bitcoinText показывает item.bitcoin (float→ToString). UpdateButton 0x828E9C — только interactable.
- **Гипотеза: наши карточки В КОНЦЕ ленты — юзер не дошёл (или жалоба с v2, где btc=5). v4: перенести наши карточки в НАЧАЛО items[] (индексы 3,4 — сразу после Apson 128×128).**
- ShopItem (SO): itemName/price/bitcoin/sprite/spawn/large/translateDescription/description/isService/serviceType/isInfoCard. IsUnlocked 0x826198 (static List<string> unlockedItem).

### 4. Универсальный принтер (замена 512+1024 одним)
- **Printer.Supports (0x834E80): СТРОГОЕ РАВЕНСТВО** `w==max(sw,1) && h==max(sh,1)` (sw=[this+0x74], sh=[this+0x78]).
- PrintPicture 0x834FA0: sourceColors=GetPixels; width/height = РАЗМЕР КАРТИНКИ ([this+0xb8/0xbc]); бумага = TextureLoader paperPrefab, грузит PNG → размер = размер картинки ⇒ печать 512 на «1024»-принтере безопасна.
- **v4-план: патч Supports (обе арки): `(w==sw || w*2==sw) && (h==sh || h*2==sh)`. Клон Apson_A3_512 (GO 13674, Printer MB 13681: paperPrefab=11511, supportedPrintSize={512,512}) → supportedPrintSize={1024,1024}, имя «Apson A3 Universal», price 20000, btc 0. Карточки 512+1024 удалить, universal в начало (после Apson 128). Side-effect: ориг. 128-принтер начнёт принимать 64×64 (допустимо).**
- Печать 100 листов → print_master (incremental) — не трогаем.

### 5. Достижения (easter egg + Bitcoin Searcher)
- AchievementList SO: **sharedassets0.assets pid 256**; Entries[9] = Print Master ('Print 100 sheets of paper in total', Icon 174, Type=0 Incremental, ID='print_master', Hidden=0). UI → 283 (AchievementsElement префаб).
- **Bitcoin-иконки УЖЕ в sharedassets0: Sprite 152 Bitcoin_100, 153 Bitcoin_200, 154 Bitcoin_50** (без externals — просто m_FileID=0) ✓ для Bitcoin Searcher.
- AchievementsUI.Refresh 0x81B550: CloudOnceManager.Instance (слот 0x223a000+0xec8 → [+0xb8] → [0]) → поле 0x18 = AchievementList → Entries (x26); list.UI [instance+0x20] = 283; цикл: entry=x23; **GetAchievementFromId(instance, entry.ID) 0x7b4ba0** → ach=x22; Instantiate(UI, canvas[x19+0x20]) → x21 (AchievementsElement); title.text=entry.Title [entry+0x10] (0x81b7d4-0x81b7ec: [x21+0x20] set_text); desc [entry+0x18]; image.texture=Icon [entry+0x20] (0x17d7300 sprite.texture + 0x197fd90 RawImage.set_texture); locked.SetActive(!ach.achieved [ach+0x24]); progressable [x21+0x40] (RectTransform!); info [x21+0x30].
- **Точка хука: 0x81b7f0 (после title.text): if (w27==INDEX_PrintMaster) сохранить x21 (элемент) в RW-слот.** w27 = индекс цикла ( callee-saved). INDEX узнать при добавлении Entry (если добавим Bitcoin Searcher в конец — Print Master останется 9).
- Achievement.Achieve() 0x81C064: achieved=1, PlayerPrefs (SetInt 0x17c8580, SetString 0x17c87c0), Manager.AchievementUnlocked (событие → AchievementsUI.OnAchievementChanged). **Выдача: CloudOnceManager.GetAchievementFromId(Instance, "bitcoin_searcher") → Achieve().**
- Easter egg клики: AchievementsElement НЕ кликабелен (нет Button). **План G: хук Main.Update 0x7e1284:** если сохранён элемент Print Master: Input.GetMouseButtonDown(0) 0x180294c + mousePosition 0x1802900 + RectTransformUtility.RectangleContainsScreenPoint (0x196a1e4/0x196a2b8 — уточнить перегрузку без camera) на progressable-RectTransform → counter (PlayerPrefs 'UraniumEggClicks') → при 10 и uses<2: Random.Range(int,int) (0x17b81f8 или 0x17b8238 — уточнить) 100..1000 BTC; BitcoinManager.get_Bitcoin 0x7b2d14 → FloatShadow; выдача по образцу btc64 (op_Implicit 0x816884/0x816874 — сверить с patch_so_v3.py); uses++ ('UraniumEggUses'); при uses==2 → выдать bitcoin_searcher.
- НУЖНА RW-область в .so для указателя (элемент) — найти нулевой padding в RW-сегменте (vaddr 0x2121c28..0x23BBF80) при реализации.
- Кейв arm64: 0x85D978..0x85E96C (занято ~0xb0 v3; свободно с 0x85da28 ≈3.9KB). arm32: 0x1C6A000+ (BTC 0x80, MON 0x100, GETCMP 0x140).

### 6. Сайт PrintExpert — переключатель баннера
- PrintExpert MB 11239: icon=818, websiteName='Print Expert', bannerPrefab=12916 (ВЕРТ), fileNameText=11583 (Text), home=997, thankYou=1312, alertText=13747 (гориз. TextureLoader, v3), purchaseButton=11581, selectedFile.
- purchaseButton 11581: onClick persistent → m_Target=11239, m_MethodName='Purchase', Mode=1. **Вторую кнопку делать в бандле: клон кнопки + persistent m_Target=клонMB.**
- **v4-план: клон PrintExpert MB (bannerPrefab=13747 гориз.), 2 кнопки на home (997): «Вертикальный» (target 11239) и «Горизонтальный» (target клон). Патч Purchase (обе арки): sz-кейв принимает 32x70 И 70x32; спавнит ВСЕГДА this.bannerPrefab [x19+0x30] (убрать выбор по ширине и alertText-использование).**
- B1-блок 0x8672A4 (проверка размера) + B2-блок 0x867394 (спавн) — переделать.

### 7. НГ-подарки (п.9)
- **ГОТОВЫЕ АССЕТЫ: GameObject «Gift» (resources.assets 1631), Mesh Gift 426, Texture2D Gift 175 / Gift_0 245, Sprite Gift 746.**
- План: инстансы Gift в сцене комнаты (+ на кондиционере Cooler) + legacy AnimationClip (scale 0↔1, loop) + Animation-компонент PlayAutomatically — без кода. Сцены: level0=меню; level1..6 = комнаты (уточнить, где живёт кондиционер юзера).

### 8. Анимации главного меню (п.10)
- level0: заголовок (Text 1102, наш Uranium) + кнопки. План: legacy AnimationClip (bob/пульс/слайд) + Animation PlayAutomatically на объекты level0. AnimationClip писать бинарно по typetree (m_Legacy=1, m_ScaleCurves/…, m_SampleRate, m_WrapMode=Loop(2?)).

## Прочее
- Shop SO (sharedassets1 4175) — магазин комплектующих (страницы Accessory/Processor/Memory/Cooler/GPU/PSU/Storage/Motherboards/Monitor/Prebuilt/Services/Case) — НЕ трогаем.
- Downloader (resources.assets 12325) — App Store, apps=23 (включая Market MB 12594).
- «Daily Market» Title GO: LocalizationText — если юзер говорил про «Title остался», это заголовок окна маркета (перевод ключа) — НЕ карточка.
- Второй лог log_2026_09_06_18_30_30.txt: краш при старте (uptime 0s), весь бэктрейс libunity+JNI (art_jni_trampoline), fault 0x40 — разовый краш первого запуска b5, не наш патч. Второй раз не воспроизводился (потом играл до 21:35).
- Адреса: Main.get_Instance 0x7e0c50, Main.Update 0x7e1284, GameObject.SetActive 0x17cfd04, String.IsNullOrEmpty 0xfd4500, Text вирт.слоты 0x5e8/0x5f0, PlayerPrefs GetInt 0x17c8614/0x17c8658, SetInt 0x17c8580, GetString 0x17c8854/0x17c8898, SetString 0x17c87c0, DateTime.UtcNow 0x111fd88 (в Achieve: 0x1122c34 → 0x112478c/0x1124854 — long).
- so_v2.bin в /tmp — доВ3 .so (эталон оригинала для сверки Purchase). /tmp/orig_data.unity3d — оригинальный бандл. /tmp/v2_data.unity3d — v2-бандл.

## Вопросы юзеру (задать перед реализацией)
1. Версия, где видел «Blue PC Simulator» в меню + видит ли «Lamp 1/Lamp 2» в конце ленты маркета (проверка прокрутки/версии).
2. Описание достижения Bitcoin Searcher + скрытое или видимое.
3. П.8 «картинка на стекло» — уточнить механику (куда вставлять, на какой ПК).
4. Подарки — в каких местах/комнате, размер, постоянная анимация?
