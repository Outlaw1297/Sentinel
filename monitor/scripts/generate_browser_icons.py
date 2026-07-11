"""Regenerate browser favicons and PWA icons from the Sentinel app mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ICON_DIR = STATIC / "icons"


def _source_path() -> Path:
    for name in ("tray-left-icon.png", "sentinel-logo.png"):
        path = ICON_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError("Missing tray-left-icon.png or sentinel-logo.png")


def _fit_square(img: Image.Image, size: int) -> Image.Image:
    return img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


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

    print(f"Source: {source}")
    print(f"Wrote {STATIC / 'favicon.ico'}")
    print(f"Wrote {STATIC / 'favicon.png'}")
    print(f"Wrote {ICON_DIR / 'icon-192.png'}")
    print(f"Wrote {ICON_DIR / 'icon-512.png'}")
    print(f"Wrote {ICON_DIR / 'apple-touch-icon.png'}")


if __name__ == "__main__":
    main()
