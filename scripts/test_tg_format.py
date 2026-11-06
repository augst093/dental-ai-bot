"""Проверка преобразования Markdown -> Telegram HTML (без сети и без базы). Запуск: python scripts/test_tg_format.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tg_format import to_telegram_html  # noqa: E402

CASES = [
    ("bold and bullets", "**Лечение и гигиена**\n- Чистка — 550 000 сум\n* Кариес — от 450 000 сум",
     "<b>Лечение и гигиена</b>\n• Чистка — 550 000 сум\n• Кариес — от 450 000 сум"),
    ("escapes stray html chars", "Цена < 1000 & скидка > 10%", "Цена &lt; 1000 &amp; скидка &gt; 10%"),
    ("keeps allowed tags", "<b>Ок</b> и **жирный**", "<b>Ок</b> и <b>жирный</b>"),
    ("header", "### Заголовок", "<b>Заголовок</b>"),
    ("italic star", "*курсив* и 2*3*4", "<i>курсив</i> и 2*3*4"),
    ("unclosed bold stays literal", "**открыто", "**открыто"),
    ("unclosed allowed tag is closed", "<b>текст", "<b>текст</b>"),
    ("empty", "", ""),
]


def main() -> int:
    failed = 0
    for name, src, expected in CASES:
        got = to_telegram_html(src)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        got:      {got!r}\n        expected: {expected!r}"))
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
