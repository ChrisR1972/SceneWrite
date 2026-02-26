"""
Reusable high-DPI image thumbnail label with auto-orientation
and double-click full-size preview.
"""

import os
from PyQt6.QtWidgets import QLabel, QDialog, QVBoxLayout, QScrollArea, QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QMouseEvent, QImageReader


class ImagePreviewDialog(QDialog):
    """Full-size image preview opened on double-click.

    Loads the image fresh from *image_path* at original resolution so
    the preview is always full quality, independent of any thumbnail
    scaling that was applied earlier.
    """

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(image_path) if image_path else "Image Preview")
        self.setMinimumSize(400, 300)

        reader = QImageReader(image_path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return
        full_pix = QPixmap.fromImage(image)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
        if screen:
            available = screen.availableGeometry()
            max_logical_w = int(available.width() * 0.85)
            max_logical_h = int(available.height() * 0.85)
        else:
            max_logical_w, max_logical_h = 1200, 800

        max_physical_w = int(max_logical_w * ratio)
        max_physical_h = int(max_logical_h * ratio)

        if full_pix.width() > max_physical_w or full_pix.height() > max_physical_h:
            display_pix = full_pix.scaled(
                max_physical_w, max_physical_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            display_pix = full_pix

        display_pix.setDevicePixelRatio(ratio)
        label.setPixmap(display_pix)
        scroll.setWidget(label)
        layout.addWidget(scroll)

        logical_w = int(display_pix.width() / ratio)
        logical_h = int(display_pix.height() / ratio)
        dialog_w = min(logical_w + 40, max_logical_w)
        dialog_h = min(logical_h + 40, max_logical_h)
        self.resize(dialog_w, dialog_h)


class ClickableImageLabel(QLabel):
    """
    Drop-in replacement for QLabel thumbnail that provides:
    - High-DPI aware pixmap rendering (sharp on scaled displays)
    - Auto-orientation: switches between portrait/landscape layout
      based on the source image's aspect ratio
    - Double-click opens a full-size preview dialog
    """

    def __init__(
        self,
        max_short: int = 80,
        max_long: int = 120,
        parent=None,
    ):
        super().__init__(parent)
        self._max_short = max_short
        self._max_long = max_long
        self._source_pixmap: QPixmap | None = None
        self._image_path: str = ""

        self.setFixedSize(max_long, max_long)
        self.setStyleSheet("border: 1px solid #555555; background: #3c3c3c;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("No Image")
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def setImageFromPath(self, path: str) -> bool:
        """Load an image from *path*, orient the label, and display a
        high-DPI thumbnail.  Returns True on success."""
        pix = QPixmap(path)
        if pix.isNull():
            self.clearImage()
            self.setText("Invalid")
            return False

        self._source_pixmap = pix
        self._image_path = path
        self._apply_orientation(pix)
        self._render_thumbnail(pix)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        return True

    def clearImage(self):
        self._source_pixmap = None
        self._image_path = ""
        self.setFixedSize(self._max_long, self._max_long)
        self.setPixmap(QPixmap())
        self.setText("No Image")
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _apply_orientation(self, pix: QPixmap):
        """Resize the label to portrait or landscape depending on the
        source image's aspect ratio."""
        if pix.width() >= pix.height():
            w, h = self._max_long, self._max_short
        else:
            w, h = self._max_short, self._max_long
        self.setFixedSize(w, h)

    def _render_thumbnail(self, pix: QPixmap):
        ratio = self.devicePixelRatio()
        target_w = int(self.width() * ratio)
        target_h = int(self.height() * ratio)

        scaled = pix.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        self.setText("")
        self.setPixmap(scaled)

    # ── Double-click preview ──────────────────────────────────────

    def mouseDoubleClickEvent(self, event: QMouseEvent | None):
        if self._image_path and os.path.isfile(self._image_path):
            dlg = ImagePreviewDialog(self._image_path, parent=self.window())
            dlg.exec()
        else:
            super().mouseDoubleClickEvent(event)
