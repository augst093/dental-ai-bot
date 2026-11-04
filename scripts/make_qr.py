"""
Generate a QR code that opens the bot with a source tag, for stands, flyers and business cards.

Usage:
    pip install qrcode[pil]
    python scripts/make_qr.py instagram --bot YourClinicBot --out qr_instagram.png

The source tag is stored on the patient's first /start, so the director can see
which channel brings patients in /digest.
"""

import argparse
import re
import sys

import qrcode


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a QR code for a bot source tag")
    parser.add_argument("source", help="Channel name: letters, digits, _ or -, up to 32 characters")
    parser.add_argument("--bot", required=True, help="Bot username without @")
    parser.add_argument("--out", default=None, help="Output PNG path (default: qr_<source>.png)")
    args = parser.parse_args()

    source = args.source.lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", source):
        sys.exit("Источник: только латиница, цифры, '_' и '-', до 32 символов.")

    url = f"https://t.me/{args.bot.lstrip('@')}?start={source}"
    out_path = args.out or f"qr_{source}.png"
    qrcode.make(url).save(out_path)
    print(f"{url}\n-> {out_path}")


if __name__ == "__main__":
    main()
