import sys
from pathlib import Path

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _ensure_emoji_font() -> None:
    """Load the Noto Color Emoji font if it is available on the system."""

    emoji_font_paths = (
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf"),
    )

    for path in emoji_font_paths:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id != -1:
            break


def main():
    app = QApplication(sys.argv)
    _ensure_emoji_font()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
