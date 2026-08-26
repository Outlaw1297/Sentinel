"""Tests for browser / PWA notification icon generation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import generate_browser_icons as icons  # noqa: E402


class NotificationIconTests(unittest.TestCase):
    def test_badge_is_white_silhouette_on_transparent(self) -> None:
        source_path = ROOT / "static" / "icons" / "tray-left-icon.png"
        if not source_path.is_file():
            source_path = ROOT / "static" / "icons" / "sentinel-mark.png"
        source = Image.open(source_path).convert("RGBA")
        badge = icons._white_silhouette(source.resize((96, 96), Image.Resampling.LANCZOS))
        px = list(badge.getdata())
        transparent = sum(1 for _r, _g, _b, a in px if a < 16)
        white_opaque = sum(1 for r, g, b, a in px if a > 200 and r > 250 and g > 250 and b > 250)
        self.assertGreater(transparent / len(px), 0.5)
        self.assertGreater(white_opaque, 50)
        # Corners of the branding canvas should stay clear.
        w, h = badge.size
        corner_alpha = [badge.getpixel(p)[3] for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        self.assertTrue(all(a < 16 for a in corner_alpha), corner_alpha)

    def test_checked_in_badge_asset(self) -> None:
        badge = Image.open(ROOT / "static" / "icons" / "notification-badge.png").convert("RGBA")
        self.assertEqual(badge.size, (96, 96))
        px = list(badge.getdata())
        transparent = sum(1 for _r, _g, _b, a in px if a < 16)
        self.assertGreater(transparent / len(px), 0.5)
        for point in ((0, 0), (95, 0), (0, 95), (95, 95)):
            self.assertLess(badge.getpixel(point)[3], 16)

    def test_notification_icon_punches_dark_background(self) -> None:
        source = Image.open(ROOT / "static" / "icons" / "sentinel-mark.png").convert("RGBA")
        icon = icons._with_transparent_background(
            source.resize((64, 64), Image.Resampling.LANCZOS)
        )
        self.assertEqual(icon.getpixel((0, 0))[3], 0)
        opaque = sum(1 for _r, _g, _b, a in icon.getdata() if a > 200)
        self.assertGreater(opaque, 20)

    def test_script_writes_notification_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Point the module at a temp icon dir with a copied source.
            src = ROOT / "static" / "icons" / "sentinel-mark.png"
            icon_dir = tmp_path / "icons"
            icon_dir.mkdir()
            (icon_dir / "sentinel-mark.png").write_bytes(src.read_bytes())
            static = tmp_path
            old_static, old_icons = icons.STATIC, icons.ICON_DIR
            try:
                icons.STATIC = static
                icons.ICON_DIR = icon_dir
                icons.main()
            finally:
                icons.STATIC = old_static
                icons.ICON_DIR = old_icons
            self.assertTrue((icon_dir / "notification-badge.png").is_file())
            self.assertTrue((icon_dir / "notification-icon.png").is_file())


if __name__ == "__main__":
    unittest.main()
