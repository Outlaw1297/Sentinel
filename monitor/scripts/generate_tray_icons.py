"""Build tray-mark.png and tray-green/amber/gray.ico for the system tray."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "static" / "icons"

STATUS_COLORS = {
    "green": (34, 197, 94, 255),
    "amber": (245, 158, 11, 255),
    "gray": (125, 141, 161, 255),
}


def _left_icon_source() -> Path:
    for name in ("tray-left-icon.png", "sentinel-logo.png"):
        path = ICON_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing tray icon source in {ICON_DIR}")


def _is_background(r: int, g: int, b: int, a: int) -> bool:
    if a < 8:
        return True
    return r < 30 and g < 36 and b < 50


def build_tray_mark() -> Image.Image:
    src = Image.open(_left_icon_source()).convert("RGBA")
    px = src.load()
    width, height = src.size

    cleaned = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    clean_px = cleaned.load()
    for y in range(height):
        for x in range(width):
            rgba = px[x, y]
            if not _is_background(*rgba):
                clean_px[x, y] = rgba

    bbox = cleaned.getbbox()
    if not bbox:
        return src.resize((128, 128), Image.Resampling.LANCZOS)

    cropped = cleaned.crop(bbox)
    cw, ch = cropped.size
    side = max(cw, ch)
    margin = max(4, int(side * 0.08))
    square = Image.new("RGBA", (side + margin * 2, side + margin * 2), (0, 0, 0, 0))
    square.paste(cropped, (margin + (side - cw) // 2, margin + (side - ch) // 2))
    return square.resize((128, 128), Image.Resampling.LANCZOS)


def compose_icon(
    mark: Image.Image,
    color: tuple[int, int, int, int],
    *,
    canvas_size: int = 32,
) -> Image.Image:
    logo_size = canvas_size - 4
    pad = (canvas_size - logo_size) // 2
    status_inset = max(2, canvas_size // 8)
    status_size = max(4, canvas_size // 5)

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    logo = mark.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    canvas.paste(logo, (pad, pad), logo)

    x0 = canvas_size - status_inset - status_size
    y0 = canvas_size - status_inset - status_size
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        (x0, y0, x0 + status_size, y0 + status_size),
        fill=color,
        outline=(11, 15, 22, 255),
        width=1,
    )
    return canvas


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    mark = build_tray_mark()
    mark.save(ICON_DIR / "tray-mark.png")

    for name, color in STATUS_COLORS.items():
        icon_32 = compose_icon(mark, color, canvas_size=32)
        icon_16 = compose_icon(mark, color, canvas_size=16)
        out = ICON_DIR / f"tray-{name}.ico"
        icon_32.save(out, format="ICO", sizes=[(32, 32), (16, 16)], append_images=[icon_16])
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
