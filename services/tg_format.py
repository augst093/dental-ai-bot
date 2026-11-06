"""
Преобразование ответа LLM (Markdown) в Telegram HTML.

Бот отправляет сообщения с parse_mode=HTML, поэтому символы **, ##, - и т.п.
показываются пациенту как есть. Эта функция:
- сохраняет разрешённые теги <b>, <i>, <u>, <s>, <code>, <a href="...">;
- экранирует всё остальное (&, <, >), чтобы текст не ломал разметку Telegram;
- переводит Markdown в HTML: **жирный**, __жирный__, *курсив*, _курсив_, заголовки, маркеры списка.
"""

import html
import re

# Теги, которые Telegram понимает в HTML-режиме
_ALLOWED_TAG_RE = re.compile(r"</?(?:b|i|u|s|code|pre|a)(?:\s+href=\"[^\"<>]+\")?>", re.IGNORECASE)
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__", re.DOTALL)
_ITALIC_STAR_RE = re.compile(r"(?<![\*\w])\*(?=\S)(.+?)(?<=\S)\*(?![\*\w])")
_ITALIC_UNDER_RE = re.compile(r"(?<![_\w])_(?=\S)(.+?)(?<=\S)_(?![_\w])")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+", re.MULTILINE)


def to_telegram_html(text: str) -> str:
    if not text:
        return ""

    # 1. Прячем разрешённые теги, остальной текст экранируем
    tags: list[str] = []

    def _stash(match: re.Match) -> str:
        tags.append(match.group(0))
        return f"\x00{len(tags) - 1}\x00"

    stashed = _ALLOWED_TAG_RE.sub(_stash, text)
    escaped = html.escape(stashed, quote=False)

    # 2. Markdown -> HTML
    converted = _HEADER_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>", escaped)
    converted = _BULLET_RE.sub(lambda m: f"{m.group(1)}• ", converted)
    converted = _BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", converted)
    converted = _ITALIC_STAR_RE.sub(lambda m: f"<i>{m.group(1)}</i>", converted)
    converted = _ITALIC_UNDER_RE.sub(lambda m: f"<i>{m.group(1)}</i>", converted)

    # 3. Возвращаем разрешённые теги на место
    def _restore(match: re.Match) -> str:
        return tags[int(match.group(1))]

    restored = re.sub(r"\x00(\d+)\x00", _restore, converted)

    # 4. Закрываем незакрытые <b>/<i>, чтобы Telegram не отверг сообщение
    for tag in ("b", "i", "u", "s", "code"):
        opened = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", restored, re.IGNORECASE))
        closed = len(re.findall(rf"</{tag}>", restored, re.IGNORECASE))
        if opened > closed:
            restored += f"</{tag}>" * (opened - closed)
        elif closed > opened:
            restored = re.sub(rf"</{tag}>", "", restored, count=closed - opened, flags=re.IGNORECASE)

    return restored.strip()
