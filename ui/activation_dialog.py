"""
License activation and trial dialogs for SceneWrite.

Three dialog classes:
  - ActivationDialog  : first-launch screen (enter key or start trial)
  - TrialExpiredDialog : shown when the 7-day trial is over
  - LicenseStatusBar   : small widget for the bottom of MainWindow
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox, QWidget, QApplication, QFrame,
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDesktopServices

from config import APP_VERSION
from core.license_manager import (
    LicenseStatus, LicenseState,
    get_machine_id, activate_license,
    start_trial, trial_days_remaining,
    TRIAL_DAYS,
)

PURCHASE_URL = "https://scenewrite.app/#pricing"


# ---------------------------------------------------------------------------
#  Background activation thread (so the UI doesn't freeze)
# ---------------------------------------------------------------------------

class _ActivationThread(QThread):
    finished = pyqtSignal(object)  # emits LicenseState

    def __init__(self, key: str, machine_id: str):
        super().__init__()
        self.key = key
        self.machine_id = machine_id

    def run(self):
        state = activate_license(self.key, self.machine_id)
        self.finished.emit(state)


# ---------------------------------------------------------------------------
#  Main activation dialog (first launch or "Enter License Key" from menu)
# ---------------------------------------------------------------------------

class ActivationDialog(QDialog):
    """Shown on first launch or when the user chooses Help > Enter License Key."""

    def __init__(self, parent=None, allow_trial: bool = True, allow_close: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Activate SceneWrite")
        self.setFixedWidth(520)
        self.setModal(True)
        self._allow_close = allow_close
        self._allow_trial = allow_trial
        self._machine_id = get_machine_id()
        self._thread: _ActivationThread | None = None
        self._activated = False
        self._trial_started = False
        self._init_ui()

    # -- UI ----------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 24, 28, 20)

        title = QLabel("Welcome to SceneWrite")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(f"Version {APP_VERSION}")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        # License key section
        key_label = QLabel("Enter your license key:")
        key_label.setFont(QFont("", 10, QFont.Weight.Bold))
        layout.addWidget(key_label)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("SW-XXXX-XXXX-XXXX-XXXX")
        self._key_edit.setMinimumHeight(36)
        self._key_edit.setFont(QFont("Consolas, Courier New", 12))
        self._key_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._key_edit.returnPressed.connect(self._on_activate)
        layout.addWidget(self._key_edit)

        self._activate_btn = QPushButton("Activate License")
        self._activate_btn.setMinimumHeight(38)
        self._activate_btn.setDefault(True)
        self._activate_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "font-size: 13px; font-weight: bold; border-radius: 5px; }"
            "QPushButton:hover { background-color: #1a8ae8; }"
            "QPushButton:disabled { background-color: #999; }"
        )
        self._activate_btn.clicked.connect(self._on_activate)
        layout.addWidget(self._activate_btn)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # Separator
        or_label = QLabel("— or —")
        or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label.setStyleSheet("color: #aaa; margin: 4px 0;")
        layout.addWidget(or_label)

        # Trial / Purchase buttons
        btn_row = QHBoxLayout()

        if self._allow_trial:
            remaining = trial_days_remaining(self._machine_id)
            if remaining is None:
                trial_btn = QPushButton(f"Start {TRIAL_DAYS}-Day Free Trial")
                trial_btn.setMinimumHeight(34)
                trial_btn.setStyleSheet(
                    "QPushButton { font-size: 12px; padding: 6px 16px; }"
                )
                trial_btn.clicked.connect(self._on_start_trial)
                btn_row.addWidget(trial_btn)

        buy_btn = QPushButton("Purchase License")
        buy_btn.setMinimumHeight(34)
        buy_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 6px 16px; }"
        )
        buy_btn.clicked.connect(self._on_purchase)
        btn_row.addWidget(buy_btn)

        layout.addLayout(btn_row)

    # -- Slots -------------------------------------------------------------

    def _on_activate(self):
        key = self._key_edit.text().strip()
        if not key:
            self._status_label.setText("Please enter a license key.")
            self._status_label.setStyleSheet("color: #d32f2f;")
            return

        self._activate_btn.setEnabled(False)
        self._activate_btn.setText("Activating...")
        self._status_label.setText("")
        QApplication.processEvents()

        self._thread = _ActivationThread(key, self._machine_id)
        self._thread.finished.connect(self._on_activation_result)
        self._thread.start()

    def _on_activation_result(self, state: LicenseState):
        self._activate_btn.setEnabled(True)
        self._activate_btn.setText("Activate License")

        if state.status == LicenseStatus.VALID:
            self._status_label.setText(state.message)
            self._status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self._activated = True
            QMessageBox.information(self, "Activated", "Your license has been activated. Enjoy SceneWrite!")
            self.accept()
        else:
            self._status_label.setText(state.message)
            self._status_label.setStyleSheet("color: #d32f2f;")

    def _on_start_trial(self):
        start_trial(self._machine_id)
        self._trial_started = True
        self.accept()

    def _on_purchase(self):
        QDesktopServices.openUrl(QUrl(PURCHASE_URL))

    # -- Results -----------------------------------------------------------

    @property
    def was_activated(self) -> bool:
        return self._activated

    @property
    def was_trial_started(self) -> bool:
        return self._trial_started

    def closeEvent(self, event):
        if not self._allow_close:
            event.ignore()
        else:
            super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and not self._allow_close:
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
#  Trial-expired / license-required dialog
# ---------------------------------------------------------------------------

class TrialExpiredDialog(QDialog):
    """Shown when the trial has ended and no license is present."""

    def __init__(self, parent=None, message: str = ""):
        super().__init__(parent)
        self.setWindowTitle("License Required")
        self.setFixedWidth(460)
        self.setModal(True)
        self._message = message or "Your free trial has ended."
        self._wants_activate = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)

        icon_label = QLabel("SceneWrite")
        icon_label.setFont(QFont("", 15, QFont.Weight.Bold))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        msg = QLabel(self._message)
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size: 12px; margin: 8px 0;")
        layout.addWidget(msg)

        info = QLabel(
            "You can still open and read your existing projects.\n"
            "AI generation and export features require a license."
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 6px;")
        layout.addWidget(info)

        btn_row = QHBoxLayout()

        activate_btn = QPushButton("Enter License Key")
        activate_btn.setMinimumHeight(36)
        activate_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "font-size: 12px; font-weight: bold; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1a8ae8; }"
        )
        activate_btn.clicked.connect(self._on_activate)
        btn_row.addWidget(activate_btn)

        buy_btn = QPushButton("Purchase License")
        buy_btn.setMinimumHeight(36)
        buy_btn.setStyleSheet("QPushButton { font-size: 12px; padding: 6px 16px; }")
        buy_btn.clicked.connect(self._on_purchase)
        btn_row.addWidget(buy_btn)

        continue_btn = QPushButton("Continue (Read-Only)")
        continue_btn.setMinimumHeight(36)
        continue_btn.setStyleSheet("QPushButton { font-size: 12px; padding: 6px 16px; }")
        continue_btn.clicked.connect(self.accept)
        btn_row.addWidget(continue_btn)

        layout.addLayout(btn_row)

    def _on_activate(self):
        self._wants_activate = True
        self.reject()

    def _on_purchase(self):
        QDesktopServices.openUrl(QUrl(PURCHASE_URL))

    @property
    def wants_activate(self) -> bool:
        return self._wants_activate
