"""
Novel/Story Import Configuration Dialog.
Shown after the user selects a text file, before AI processing begins.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QGroupBox, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from core.novel_importer import word_count, estimate_processing_time, validate_text

import os


class NovelImportDialog(QDialog):
    """Configuration dialog for novel-to-screenplay import."""

    def __init__(self, filepath: str, text: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.text = text
        self._word_count = word_count(text)

        self.setWindowTitle("Import Story from Text")
        self.setMinimumWidth(650)
        self.setMinimumHeight(520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # File info
        info_group = QGroupBox("File Information")
        info_layout = QFormLayout()

        filename = os.path.basename(self.filepath)
        info_layout.addRow("File:", QLabel(filename))
        info_layout.addRow("Word count:", QLabel(f"{self._word_count:,}"))
        info_layout.addRow("Estimated time:", QLabel(estimate_processing_time(self.text)))

        is_valid, warning = validate_text(self.text)
        if warning:
            warning_label = QLabel(warning)
            warning_label.setWordWrap(True)
            warning_label.setStyleSheet("color: orange; font-style: italic;")
            info_layout.addRow("Note:", warning_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Configuration
        config_group = QGroupBox("Screenplay Settings")
        config_layout = QFormLayout()

        self.length_combo = QComboBox()
        self.length_combo.addItems([
            "Micro (1 act, 1-5 scenes)",
            "Short (3 acts, 9-15 scenes)",
            "Medium (3 acts, 15-24 scenes)",
            "Long (5 acts, 30-50 scenes)"
        ])
        self.length_combo.setCurrentIndex(2)
        self.length_combo.setToolTip(
            "Controls how aggressively the novel is condensed.\n"
            "Micro: Extreme condensation, only the core moment\n"
            "Short: Key scenes only, rapid pacing\n"
            "Medium: Balanced adaptation with room for development\n"
            "Long: Most comprehensive adaptation"
        )
        config_layout.addRow("Story Length:", self.length_combo)

        self.intent_combo = QComboBox()
        self.intent_combo.addItems([
            "General Story",
            "Advertisement / Brand Film",
            "Social Media / Short-form",
            "Visual Art / Abstract"
        ])
        self.intent_combo.setCurrentIndex(0)
        self.intent_combo.setToolTip(
            "Affects scene density, pacing, and prompt style.\n"
            "General Story: Balanced narrative adaptation\n"
            "Social Media / Short-form: Hook-first, punchy pacing\n"
            "Visual Art / Abstract: Mood-driven, non-linear"
        )
        config_layout.addRow("Story Intent:", self.intent_combo)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Text preview
        preview_group = QGroupBox("Text Preview (first 500 words)")
        preview_layout = QVBoxLayout()

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(180)

        words = self.text.split()
        preview_text = " ".join(words[:500])
        if len(words) > 500:
            preview_text += " ..."
        self.preview_edit.setPlainText(preview_text)

        preview_layout.addWidget(self.preview_edit)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.convert_btn = QPushButton("Convert to Screenplay")
        self.convert_btn.setDefault(True)
        self.convert_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.convert_btn)

        layout.addLayout(button_layout)

    def get_length(self) -> str:
        """Get selected story length key."""
        length_map = {0: "micro", 1: "short", 2: "medium", 3: "long"}
        return length_map.get(self.length_combo.currentIndex(), "medium")

    def get_intent(self) -> str:
        """Get selected story intent."""
        return self.intent_combo.currentText()
