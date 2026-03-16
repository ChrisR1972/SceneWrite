"""
Update notification dialog and background check thread for SceneWrite.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QDialogButtonBox, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QDesktopServices

from config import APP_VERSION, config
from core.update_checker import (
    UpdateInfo, check_for_update,
    seconds_since_last_check, record_update_check,
)

CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # once per day


class UpdateCheckThread(QThread):
    """Runs the update check on a background thread so the UI stays responsive."""

    update_available = pyqtSignal(object)  # emits UpdateInfo

    def run(self):
        if not config._config_data.get("check_for_updates", True):
            return
        if seconds_since_last_check(config) < CHECK_INTERVAL_SECONDS:
            return
        info = check_for_update()
        record_update_check(config)
        if info is not None:
            self.update_available.emit(info)


class UpdateAvailableDialog(QDialog):
    """Shown when a newer version of SceneWrite is available."""

    def __init__(self, info: UpdateInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(480)
        self.setModal(not info.is_mandatory)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        heading = QLabel(
            f"SceneWrite {self.info.version} is available"
        )
        heading.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(heading)

        sub = QLabel(f"You are currently running version {APP_VERSION}.")
        sub.setStyleSheet("color: #888;")
        layout.addWidget(sub)

        if self.info.release_date:
            date_label = QLabel(f"Released: {self.info.release_date}")
            date_label.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(date_label)

        if self.info.release_notes:
            notes_label = QLabel("What's new:")
            notes_label.setFont(QFont("", 10, QFont.Weight.Bold))
            layout.addWidget(notes_label)

            notes = QTextEdit()
            notes.setReadOnly(True)
            notes.setPlainText(self.info.release_notes)
            notes.setMaximumHeight(180)
            layout.addWidget(notes)

        if self.info.is_mandatory:
            warn = QLabel(
                "This update is required. Please update before continuing."
            )
            warn.setStyleSheet("color: #d32f2f; font-weight: bold;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if not self.info.is_mandatory:
            skip_btn = QPushButton("Remind Me Later")
            skip_btn.clicked.connect(self.reject)
            btn_layout.addWidget(skip_btn)

        if self.info.download_url:
            dl_btn = QPushButton("Download Update")
            dl_btn.setDefault(True)
            dl_btn.setStyleSheet(
                "QPushButton { background-color: #0078d4; color: white; "
                "padding: 6px 18px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #1a8ae8; }"
            )
            dl_btn.clicked.connect(self._open_download)
            btn_layout.addWidget(dl_btn)

        layout.addLayout(btn_layout)

    def _open_download(self):
        QDesktopServices.openUrl(QUrl(self.info.download_url))
        self.accept()

    def closeEvent(self, event):
        if self.info.is_mandatory:
            event.ignore()
        else:
            super().closeEvent(event)
