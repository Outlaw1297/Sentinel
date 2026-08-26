"""Regenerate browser favicons, PWA icons, and notification badge assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ICON_DIR = STATIC / "icons"

# Near-black branding canvas — treat as transparent for notification assets.
# Keep a little headroom for resize anti-aliasing at the edges.
_BG_LUMA_MAX = 42
_BG_CHROMA_MAX = 36


def _source_path() -> Path:
    for name in ("tray-left-icon.png", "sentinel-logo.png", "sentinel-mark.png"):
        path = ICON_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError("Missing tray-left-icon.png / sentinel-logo.png / sentinel-mark.png")


def _fit_square(img: Image.Image, size: int) -> Image.Image:
    return img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def _pixel_is_background(r: int, g: int, b: int, a: int) -> bool:
    if a < 16:
        return True
    luma = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
    chroma = max(r, g, b) - min(r, g, b)
    return luma <= _BG_LUMA_MAX and chroma <= _BG_CHROMA_MAX


def _with_transparent_background(img: Image.Image) -> Image.Image:
    """Keep logo colors; punch the solid dark canvas to alpha 0."""
    src = img.convert("RGBA")
    pixels = list(src.getdata())
    out = []
    for r, g, b, a in pixels:
        if _pixel_is_background(r, g, b, a):
            out.append((r, g, b, 0))
        else:
            out.append((r, g, b, a))
    result = Image.new("RGBA", src.size)
    result.putdata(out)
    return result


def _white_silhouette(img: Image.Image) -> Image.Image:
    """Android/iOS status-bar badge: opaque white mark on transparent background."""
    src = _with_transparent_background(img)
    pixels = list(src.getdata())
    out = []
    for r, g, b, a in pixels:
        if a < 16:
            out.append((0, 0, 0, 0))
            continue
        # Soften anti-aliased edges using source alpha/luma so the badge isn't blocky.
        luma = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
        strength = max(a, min(255, int(luma + 40)))
        out.append((255, 255, 255, strength))
    result = Image.new("RGBA", src.size)
    result.putdata(out)
    return result


def _save_ico(path: Path, sizes: tuple[int, ...]) -> None:
    images = [_fit_square(_SOURCE, size) for size in sorted(sizes, reverse=True)]
    images[0].save(
        path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )


_SOURCE: Image.Image | None = None


def main() -> None:
    global _SOURCE
    source = _source_path()
    _SOURCE = Image.open(source).convert("RGBA")

    ICON_DIR.mkdir(parents=True, exist_ok=True)

    favicon_32 = _fit_square(_SOURCE, 32)
    favicon_32.save(STATIC / "favicon.png")
    favicon_32.save(ICON_DIR / "favicon.png")

    _save_ico(STATIC / "favicon.ico", (16, 32, 48))

    _fit_square(_SOURCE, 192).save(ICON_DIR / "icon-192.png")
    _fit_square(_SOURCE, 512).save(ICON_DIR / "icon-512.png")
    _fit_square(_SOURCE, 180).save(ICON_DIR / "apple-touch-icon.png")

    # Notification assets: transparent canvas + monochrome badge for status bars.
    color_transparent = _with_transparent_background(_fit_square(_SOURCE, 192))
    color_transparent.save(ICON_DIR / "notification-icon.png")

    badge = _white_silhouette(_fit_square(_SOURCE, 96))
    badge.save(ICON_DIR / "notification-badge.png")

    print(f"Source: {source}")
    print(f"Wrote {STATIC / 'favicon.ico'}")
    print(f"Wrote {STATIC / 'favicon.png'}")
    print(f"Wrote {ICON_DIR / 'icon-192.png'}")
    print(f"Wrote {ICON_DIR / 'icon-512.png'}")
    print(f"Wrote {ICON_DIR / 'apple-touch-icon.png'}")
    print(f"Wrote {ICON_DIR / 'notification-icon.png'}")
    print(f"Wrote {ICON_DIR / 'notification-badge.png'}")


if __name__ == "__main__":
    main()
