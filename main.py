import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _ensure_emoji_font(app: QApplication) -> None:
    """Load the Noto Color Emoji font if it is available on the system."""

    emoji_font_paths = (
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf"),
    )

    font_loaded = False
    for path in emoji_font_paths:
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            font_loaded = font_id != -1
        if font_loaded:
            break

    if font_loaded:
        base_font = QFont(app.font())
        families = ["Noto Color Emoji"]
        default_family = base_font.defaultFamily()
        if default_family and default_family not in families:
            families.append(default_family)
        base_font.setFamilies(families)
        app.setFont(base_font)


def main():
    app = QApplication(sys.argv)
    _ensure_emoji_font(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
