#!/usr/bin/env python3
"""Rebuild storm-prints-catalog.jpg from product photos."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / "images"
OUT_PATHS = [
    ROOT / "storm-prints-catalog.jpg",
    Path("/opt/cursor/artifacts/storm-prints-catalog.jpg"),
]

W = 1200
INK = (20, 23, 28)
ORANGE = (232, 90, 26)


def load_font(size, bold=False):
    path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    return ImageFont.truetype(path, size) if Path(path).exists() else ImageFont.load_default()


title_f = load_font(64, True)
h2_f = load_font(36, True)
item_f = load_font(26, True)
price_f = load_font(28, True)
body_f = load_font(22, False)
footer_f = load_font(22, True)
footer_num = load_font(30, True)
cap_f = load_font(16, False)


def fit_crop(im, tw, th):
    im = im.convert("RGB")
    src_w, src_h = im.size
    scale = max(tw / src_w, th / src_h)
    nw, nh = int(src_w * scale), int(src_h * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def place_item(canvas, draw, x, y, path, name, price, box_w, box_h, label_h=68):
    photo = fit_crop(Image.open(IMG_DIR / path), box_w, box_h)
    canvas.paste(photo, (x, y))
    draw.rectangle([x, y + box_h, x + box_w, y + box_h + label_h], fill=(255, 255, 255))
    draw.rectangle([x, y + box_h, x + box_w, y + box_h + label_h], outline=(220, 224, 230))
    draw.text((x + 12, y + box_h + 14), name, font=item_f, fill=INK)
    pw = draw.textlength(price, font=price_f)
    draw.text((x + box_w - pw - 12, y + box_h + 16), price, font=price_f, fill=ORANGE)
    return y + box_h + label_h


def place_pair(canvas, draw, x, y, path_back, path_front, name, price, total_w, box_h, label_h=68, gap=10):
    half = (total_w - gap) // 2
    canvas.paste(fit_crop(Image.open(IMG_DIR / path_back), half, box_h), (x, y))
    canvas.paste(fit_crop(Image.open(IMG_DIR / path_front), half, box_h), (x + half + gap, y))
    bar = Image.new("RGB", (half, 28), (20, 23, 28))
    canvas.paste(bar, (x, y + box_h - 28))
    canvas.paste(bar, (x + half + gap, y + box_h - 28))
    draw.text((x + 8, y + box_h - 22), "Back", font=cap_f, fill=(220, 224, 230))
    draw.text((x + half + gap + 8, y + box_h - 22), "Front", font=cap_f, fill=(220, 224, 230))
    draw.rectangle([x, y + box_h, x + total_w, y + box_h + label_h], fill=(255, 255, 255))
    draw.rectangle([x, y + box_h, x + total_w, y + box_h + label_h], outline=(220, 224, 230))
    draw.text((x + 12, y + box_h + 14), name, font=item_f, fill=INK)
    pw = draw.textlength(price, font=price_f)
    draw.text((x + total_w - pw - 12, y + box_h + 16), price, font=price_f, fill=ORANGE)
    return y + box_h + label_h


def build():
    canvas = Image.new("RGB", (W, 2600), "#eef1f4")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, W, 160], fill=(20, 23, 28))
    draw.text((48, 42), "Storm Prints", font=title_f, fill=(244, 246, 248))
    draw.text((52, 112), "3D Print Catalog", font=body_f, fill=(200, 205, 212))

    y = 190
    draw.text((48, y), "Figurines", font=h2_f, fill=INK)
    y += 55

    y = place_item(canvas, draw, 48, y, "big-pigeon.jpg", "Big Pigeon", "£5", W - 96, 340, 68)
    y += 18

    gap = 22
    half = (W - 96 - gap) // 2
    y1 = place_item(canvas, draw, 48, y, "gold-rocktopus.jpg", "Gold Rocktopus", "£4", half, 300, 68)
    y2 = place_item(canvas, draw, 48 + half + gap, y, "orange-person.jpg", "Orange Person", "£4", half, 300, 68)
    y = max(y1, y2) + 26

    draw.text((48, y), "Phones — £5 each", font=h2_f, fill=INK)
    y += 46

    full = W - 96
    y = place_pair(canvas, draw, 48, y, "phone-orange-single.jpg", "phone-orange-front.jpg", "Orange Phone", "£5", full, 210, 64)
    y += 14
    y = place_pair(canvas, draw, 48, y, "phone-white-logo.jpg", "phone-classic-home.jpg", "Classic White Phone", "£5", full, 210, 64)
    y += 14

    y1 = place_item(canvas, draw, 48, y, "phone-orange-pro.jpg", "Orange Pro", "£5", half, 230, 64)
    y2 = place_item(canvas, draw, 48 + half + gap, y, "phone-matte-black.jpg", "Matte Black", "£5", half, 230, 64)
    y = max(y1, y2) + 28

    line1 = "Contact Logan on WhatsApp to buy anything here"
    line2 = "or for custom requests:"
    number = "+44 7359188808"
    footer_h = 150
    final_h = y + footer_h
    canvas = canvas.crop((0, 0, W, final_h))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, y, W, final_h], fill=(20, 23, 28))

    w1 = draw.textlength(line1, font=footer_f)
    w2 = draw.textlength(line2, font=footer_f)
    wn = draw.textlength(number, font=footer_num)
    ty = y + 28
    draw.text(((W - w1) / 2, ty), line1, font=footer_f, fill=(244, 246, 248))
    draw.text(((W - w2) / 2, ty + 32), line2, font=footer_f, fill=(200, 205, 212))
    draw.text(((W - wn) / 2, ty + 68), number, font=footer_num, fill=ORANGE)

    for out in OUT_PATHS:
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out, quality=92, optimize=True)
        print("wrote", out, canvas.size)


if __name__ == "__main__":
    build()
