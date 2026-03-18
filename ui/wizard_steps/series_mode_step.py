"""
Step 0: Series Mode selection for the Story Creation Wizard.

Lets the user choose between creating a standalone story, starting a new
series, or adding a new episode to an existing series.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QButtonGroup, QComboBox, QGroupBox, QLineEdit, QPushButton,
    QMessageBox, QSizePolicy, QSpinBox, QTextEdit,
)
from PyQt6.QtCore import pyqtSignal
from typing import Optional, Dict, Any


class SeriesModeStepWidget(QWidget):
    """Step 0: Choose standalone story, new series, or new episode."""

    mode_changed = pyqtSignal()

    MODE_STANDALONE = "standalone"
    MODE_NEW_SERIES = "new_series"
    MODE_NEW_EPISODE = "new_episode"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series_list = []
        self.init_ui()

    def init_ui(self):
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        title_label = QLabel("What would you like to create?")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 0; padding: 0;")
        layout.addWidget(title_label)

        description = QLabel(
            "Choose whether to create a standalone story, start a new episodic series, "
            "or add a new episode to an existing series."
        )
        description.setWordWrap(True)
        description.setStyleSheet("margin: 0; padding: 0;")
        layout.addWidget(description)

        self.button_group = QButtonGroup(self)

        self.radio_standalone = QRadioButton("Standalone Story")
        self.radio_standalone.setToolTip("Create a single, self-contained story (default workflow)")
        self.radio_standalone.setChecked(True)
        self.button_group.addButton(self.radio_standalone)
        layout.addWidget(self.radio_standalone)

        self.radio_new_series = QRadioButton("New Series")
        self.radio_new_series.setToolTip(
            "Start a new episodic series with a shared Series Bible. "
            "Characters, locations, and world context persist across episodes."
        )
        self.button_group.addButton(self.radio_new_series)
        layout.addWidget(self.radio_new_series)

        # New series options
        self.new_series_group = QGroupBox("Series Details")
        ns_layout = QVBoxLayout(self.new_series_group)
        ns_layout.setSpacing(8)
        ns_layout.setContentsMargins(10, 14, 10, 10)

        ns_row = QHBoxLayout()
        ns_row.addWidget(QLabel("Series Title:"))
        self.series_title_edit = QLineEdit()
        self.series_title_edit.setPlaceholderText("Enter the title for your new series...")
        ns_row.addWidget(self.series_title_edit)
        ns_layout.addLayout(ns_row)

        ep_count_row = QHBoxLayout()
        ep_count_row.addWidget(QLabel("Planned Episodes:"))
        self.episode_count_spin = QSpinBox()
        self.episode_count_spin.setRange(2, 24)
        self.episode_count_spin.setValue(6)
        self.episode_count_spin.setToolTip(
            "How many episodes in this series. The AI will distribute the "
            "story arc across this many episodes instead of resolving everything at once."
        )
        ep_count_row.addWidget(self.episode_count_spin)
        ep_count_row.addStretch()
        ns_layout.addLayout(ep_count_row)

        ns_layout.addWidget(QLabel("Series Premise:"))
        self.series_premise_edit = QTextEdit()
        self.series_premise_edit.setPlaceholderText(
            "Describe the overarching concept for the entire series. "
            "This is the big-picture idea that spans all episodes, not the plot of a single episode.\n\n"
            "Example: An alien DJ named Nova Slate uses music to abduct humans for his dying "
            "civilization, while a detective and a sound engineer close in on the truth."
        )
        self.series_premise_edit.setMinimumHeight(90)
        self.series_premise_edit.setMaximumHeight(150)
        ns_layout.addWidget(self.series_premise_edit)

        self.new_series_group.hide()
        layout.addWidget(self.new_series_group)

        self.radio_new_episode = QRadioButton("New Episode (of existing series)")
        self.radio_new_episode.setToolTip(
            "Add a new episode to an existing series. "
            "Characters and world context are loaded from the Series Bible."
        )
        self.button_group.addButton(self.radio_new_episode)
        layout.addWidget(self.radio_new_episode)

        # Existing series picker
        self.episode_group = QGroupBox("Select Series")
        eg_layout = QVBoxLayout(self.episode_group)

        series_row = QHBoxLayout()
        series_row.addWidget(QLabel("Series:"))
        self.series_combo = QComboBox()
        self.series_combo.setMinimumWidth(250)
        series_row.addWidget(self.series_combo, 1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMaximumWidth(80)
        self.refresh_btn.clicked.connect(self.refresh_series_list)
        series_row.addWidget(self.refresh_btn)
        eg_layout.addLayout(series_row)

        ep_row = QHBoxLayout()
        ep_row.addWidget(QLabel("Episode Title:"))
        self.episode_title_edit = QLineEdit()
        self.episode_title_edit.setPlaceholderText("Enter the episode title...")
        ep_row.addWidget(self.episode_title_edit)
        eg_layout.addLayout(ep_row)

        self.episode_group.hide()
        layout.addWidget(self.episode_group)

        layout.addStretch()

        self.button_group.buttonClicked.connect(self._on_mode_changed)
        self.series_title_edit.textChanged.connect(lambda: self.mode_changed.emit())
        self.series_premise_edit.textChanged.connect(lambda: self.mode_changed.emit())
        self.episode_count_spin.valueChanged.connect(lambda: self.mode_changed.emit())
        self.episode_title_edit.textChanged.connect(lambda: self.mode_changed.emit())

    def _on_mode_changed(self):
        mode = self.get_mode()
        self.new_series_group.setVisible(mode == self.MODE_NEW_SERIES)
        self.episode_group.setVisible(mode == self.MODE_NEW_EPISODE)

        if mode == self.MODE_NEW_EPISODE and not self._series_list:
            self.refresh_series_list()

        self.mode_changed.emit()

    def refresh_series_list(self):
        from core.series_manager import SeriesManager
        self._series_list = SeriesManager.list_all_series()
        self.series_combo.clear()
        if self._series_list:
            for s in self._series_list:
                label = f"{s['title']} ({s['episode_count']} episodes)"
                self.series_combo.addItem(label)
        else:
            self.series_combo.addItem("(no series found)")

    def get_mode(self) -> str:
        if self.radio_new_series.isChecked():
            return self.MODE_NEW_SERIES
        if self.radio_new_episode.isChecked():
            return self.MODE_NEW_EPISODE
        return self.MODE_STANDALONE

    def get_new_series_title(self) -> str:
        return self.series_title_edit.text().strip()

    def get_episode_count(self) -> int:
        return self.episode_count_spin.value()

    def get_series_premise(self) -> str:
        return self.series_premise_edit.toPlainText().strip()

    def get_selected_series_folder(self) -> str:
        idx = self.series_combo.currentIndex()
        if 0 <= idx < len(self._series_list):
            return self._series_list[idx]["folder"]
        return ""

    def get_episode_title(self) -> str:
        return self.episode_title_edit.text().strip()

    def is_valid(self) -> bool:
        mode = self.get_mode()
        if mode == self.MODE_STANDALONE:
            return True
        if mode == self.MODE_NEW_SERIES:
            return bool(self.get_new_series_title()) and bool(self.get_series_premise())
        if mode == self.MODE_NEW_EPISODE:
            return bool(self.get_selected_series_folder()) and bool(self._series_list)
        return False
