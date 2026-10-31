# Qazaq Loc QA — MVP

Автономный инструмент для поиска ошибок в ARB-файлах Flutter. Работает на Python 3.10+ без внешних библиотек и доступа к игре. Исходные данные Grand Mobile не входят в публичную часть решения. Это CLI, а не сайт: команды запускаются в терминале, HTML-отчёт открывается в браузере.

## Запуск

Из корня проекта (в Windows можно заменить `python locqa.py` на `.\locqa.cmd`, в macOS/Linux — на `./locqa` после `chmod +x locqa`):

```powershell
python locqa.py check --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --target "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_kk.arb" --glossary glossary.csv --suspect-phrases private/suspect_kk.txt --out reports/report.json
```

Команда создаёт `reports/report.json` и `reports/report.html`. HTML можно открыть в браузере и фильтровать по ключу, типу ошибки или тексту. Поля каждой находки: `key`, `issue_type`, `severity`, `source`, `target`, `evidence`, `suggestion`, `confidence`, `reviewed_by_human`.

Для трёх носителей подготовлены отдельные файлы: `review_queue_ai_part1.xlsx` (47 строк), `review_queue_ai_part2.xlsx` (46) и `review_queue_ai_part3.xlsx` (46), все в `outputs/locqa_review_20261030/`. Каждому проверяющему нужен только свой файл. Общий `review_queue_ai.xlsx` служит исходным списком для проверки полноты; в него правки вносить не нужно.

На листе `Проверка` есть оригинал, текущий перевод, причина и до трёх **черновых** вариантов. В столбец H впишите итоговый казахский текст; в столбце I выберите `Да` только после личной проверки. Если текущий текст уже верен, скопируйте его из D в H и тоже отметьте `Да`: такие правильные примеры нужны для обучения детектора. Если пустой перевод намерен, оставьте H пустым, выберите `Да` в I и объясните причину в J. Непроверенные строки оставьте с `Нет`. На листе `Термины` **проверяющий 1** проверяет игровой глоссарий; исправляет итоговый вариант в F и разрешённые основы в C, затем отмечает G = `Да`. Остальные лист `Термины` не редактируют. После сохранения всех трёх `.xlsx` объедините их:

```powershell
python merge_reviews.py --full "outputs/locqa_review_20261030/review_queue_ai.xlsx" --parts "outputs/locqa_review_20261030/review_queue_ai_part1.xlsx" "outputs/locqa_review_20261030/review_queue_ai_part2.xlsx" "outputs/locqa_review_20261030/review_queue_ai_part3.xlsx" --out private/merged_reviews.csv
```

Команда проверит, что все 139 ключей на месте и нет повторов. Затем запустите:

```powershell
python locqa.py apply --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --target "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_kk.arb" --corrections private/merged_reviews.csv --only-reviewed --out intl_kk_fixed.arb
python locqa.py glossary-apply --glossary glossary.csv --review "outputs/locqa_review_20261030/review_queue_ai_part1.xlsx" --out glossary.csv
python locqa.py check --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --target intl_kk_fixed.arb --glossary glossary.csv --suspect-phrases private/suspect_kk.txt --out reports/report_fixed.json
python locqa.py audit --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --baseline "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_kk.arb" --target intl_kk_fixed.arb --out reports/audit.json
```

`apply` принимает `.xlsx` или `private/merged_reviews.csv`. Флаг `--only-reviewed` пропускает все строки без человеческого подтверждения. Команда сохраняет порядок, повторяющиеся `@@comment` и остальной текст исходного ARB. Изменённые значения получают соседний `@key` с меткой `QA: reviewed_by_human=true/false` в `description`. Предыдущие описания и метаданные плейсхолдеров сохраняются. Отсутствующие ключи можно добавить через таблицу; `--source` защищает от опечаток в новых ключах. `audit` возвращает ненулевой код, пока есть пропущенные строки, сломанные плейсхолдеры или непроверенные правки.

## Методика и границы

Инструмент сравнивает ключи, плейсхолдеры, ICU-формы, полное совпадение с русским, фиксированные аффиксы после переменных, длину коротких UI-строк и вероятный текст на другом языке. Он также ищет смешанные латинские и кириллические буквы в одном слове и сильные расхождения при переводе одинаковой русской строки. Глоссарий проверяется по точному русскому термину и казахской основе, допуская окончания. Все находки являются предложениями к проверке, а не автоматическим доказательством ошибки. Бренды, игровые имена и заимствования могут выглядеть подозрительно, оставаясь верными.

Семантические кальки, естественность казахской речи и расхождения терминов без утверждённого глоссария требуют носителя языка; текущая версия не выдаёт непроверенные массовые автозамены. `machine_translation_suspect` сейчас опирается на небольшой приватный список подозрительных сочетаний в `private/suspect_kk.txt`, подключаемый через `--suspect-phrases`. Отсутствие таких находок не означает отсутствие проблем. Для `inconsistent_term` есть только узкая эвристика по заметным выбросам. Узбекский можно проверить тем же CLI, но языковые эвристики `wrong_language` и `suffix_harmony` ориентированы на казахский и отключаются для других локалей.

`glossary.csv` — начальная версия из 18 терминов и вариантов по игровому контексту. Её нужно согласовать с носителем и игроками. В `intl_kk_fixed.arb` сейчас 97 изменённых строк, **0 проверенных человеком**. Итоговый аудит показывает 4 пустых перевода: они могут быть намеренно пустыми по грамматике, но это должен подтвердить носитель. Доля качества среди 150 строк жюри неизвестна. Recall на скрытых 100 ошибках и precision по ручной выборке не измерялись: ключи подложенных ошибок организаторы не раскрывают, а независимой разметки 100 находок у нас пока нет. Стоимость внешних LLM API: 0 — они не использовались.

## Обучаемый детектор и три варианта перевода

`learn_detector.py` — отдельный обучаемый детектор. Он использует только строки, явно подтверждённые носителем, и не принимает весь исходный казахский ARB за эталон. После сохранения Excel-таблицы экспортируйте принятые строки:

```powershell
python learn_detector.py export-gold --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --baseline "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_kk.arb" --review private/merged_reviews.csv --issues corrections.csv --reviewer "Команда носителей" --out private/gold.csv
python learn_detector.py train --gold private/gold.csv --model private/detector.json --metrics private/detector_metrics.json
python learn_detector.py scan --model private/detector.json --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --target "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_kk.arb" --out private/learned_findings.json
```

Обучение требует минимум 20 подтверждённых ключей. Разделение на обучение и проверку происходит по исходной русской строке, поэтому искусственные варианты проверочного ключа не попадают в обучение. В `detector_metrics.json` реальные и искусственные ошибки оцениваются **раздельно**. Этот небольшой классификатор учится на примерах, но его признаки в основном лексические и структурные; он не доказывает понимание идиом или смысла. Балл модели в `scan` не является калиброванной вероятностью.

`model_proposals.py` — отдельный исправитель на базе локальной NLLB-модели. Он предлагает до трёх **непроверенных** вариантов только там, где не рискует повредить плейсхолдеры и разметку. Он записывает CSV, из которого собирается `review_queue_ai.xlsx`; итоговый вариант человек выбирает в столбце H, а проверку отмечает в I. Команда `locqa.py apply` уже принимает этот формат. Модель [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M) имеет лицензию CC BY-NC 4.0 и используется здесь только как исследовательский генератор черновиков; коммерческое внедрение потребует подходящей лицензии или другой модели.

## Проверка

```powershell
python -m unittest discover -s tests -v
```

Тесты проверяют чтение повторяющихся комментариев и ключей, обнаружение плейсхолдеров/ICU и сохранение структуры при исправлениях. Исходные ARB и результат проверены встроенным JSON-парсером; после черновых правок `placeholder_mismatch` стало 0 вместо 12.

Flutter 3.47.9 установлен локально в `.local_flutter/flutter` и успешно сгенерировал 3 Dart-файла из **временных копий** ARB после нормализации трёх невалидных имён ключей исходного набора. Строгий запуск на исходных ключах завершается ошибкой уже на `intl_ru.arb`: `UNeedHelp`, `TowConfirmDesc` начинаются с заглавной буквы, а `inventoryEquipped@description` содержит `@`. Имена в сдаваемых ARB не менялись, чтобы не нарушить контракт ключей игры. Для повторения проверки:

```powershell
python validate_flutter.py --source "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_ru.arb" --target intl_kk_fixed.arb --flutter ".local_flutter/flutter/bin/flutter.bat" --normalize-invalid-keys
```

Скрипт создаёт временный проект, вызывает `flutter gen-l10n`, проверяет наличие сгенерированного Dart-кода и удаляет временные файлы. Для буквальной компиляции исходного набора без временной нормализации нужно согласовать переименование трёх ключей с организаторами. Локальный SDK и модель исключены из Git.

## Конфиденциальность

`Исходники/`, `reports/`, `outputs/`, `corrections.csv`, `corrections.xlsx`, `glossary.csv` и `intl_kk_fixed.arb` исключены из Git через `.gitignore`: в них есть данные организатора или производные от них. Не публикуйте эти файлы и удалите данные в срок, установленный условиями кейса. Для передачи организаторам отправьте нужные результаты отдельно по указанному ими каналу.
