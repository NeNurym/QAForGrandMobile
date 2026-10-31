# Публичное демо Qazaq Loc QA

Файлы написаны специально для репозитория. Это вымышленный тренировочный интерфейс OrbitLab, без строк и ключей из материалов организатора. Казахский файл содержит намеренные дефекты и не является обучающим эталоном.

Все команды выполняются **из корня репозитория**.

## Создать отчёт

```bash
python locqa.py check --source examples/demo/intl_ru.arb --target examples/demo/intl_kk.arb --glossary examples/demo/glossary.csv --suspect-phrases examples/demo/suspect_kk.txt --out reports/demo.json
```

Вход: 14 русских ключей и 13 казахских. Выход: `reports/demo.json` и `reports/demo.html`, **11 находок**:

| Ключ | Тип | Что намеренно внесено |
|---|---|---|
| `demoGreeting` | `placeholder_mismatch` | У переменной `pilot` убраны фигурные скобки. |
| `demoWelcome` | `same_as_source` | Целая русская фраза оставлена в переводе. |
| `demoMissing` | `untranslated` | Ключ отсутствует в целевом файле. |
| `demoCount` | `plural_mismatch` | Пропущена ICU-ветка `other`. |
| `demoGift` | `suffix_harmony` | К динамическому имени присоединён фиксированный аффикс. |
| `demoMenuButton` | `length_overflow` | Короткая кнопка превратилась в длинную фразу. |
| `demoNews` | `wrong_language` | Вместо казахского дан английский. |
| `demoConfirm` | `orthography` | В `Рaстау` использована латинская `a`, U+0061. |
| `demoAwkward` | `machine_translation_suspect` | Добавлена фраза из демонстрационного списка подозрений. |
| `demoToken` | `glossary_violation` | Перевод не содержит основы из демонстрационного глоссария. |
| `demoExitThree` | `inconsistent_term` | Третий перевод «Выход» резко отличается по длине от двух других. |

`demoBrand` показывает контрольный случай: совпадение имени OrbitLab не создаёт находку. Преднамеренные примеры демонстрируют срабатывание правил, а не доказывают precision или recall на новых данных.

## Показать защиту от применения черновиков

```bash
python locqa.py apply --source examples/demo/intl_ru.arb --target examples/demo/intl_kk.arb --corrections examples/demo/corrections.csv --only-reviewed --out reports/demo_reviewed_only.arb
```

Ожидается `Applied 0 corrections`: обе строки в демонстрационном CSV имеют `reviewed_by_human=false`. Для обучения они тоже не годятся. Не меняйте флаг на `true` ради красивого результата демонстрации.

Для показа чернового режима можно выполнить команду без `--only-reviewed`, используя отдельный выходной файл:

```bash
python locqa.py apply --source examples/demo/intl_ru.arb --target examples/demo/intl_kk.arb --corrections examples/demo/corrections.csv --out reports/demo_draft.arb
python locqa.py audit --source examples/demo/intl_ru.arb --baseline examples/demo/intl_kk.arb --target reports/demo_draft.arb --out reports/demo_draft_audit.json
```

Применятся две черновые правки. Аудит **ожидаемо вернёт код 1**: один ключ всё ещё отсутствует и два изменения не подтверждены человеком. Найти проблему, предложить исправление и принять его — разные действия.

## Показать отчёт

Откройте `reports/demo.html` через файловый менеджер. В PowerShell можно выполнить `Invoke-Item reports/demo.html`. Найдите `placeholder_mismatch` в фильтре и покажите оригинал, перевод, причину и флаг проверки.
