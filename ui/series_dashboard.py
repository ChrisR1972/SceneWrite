"""
Series Dashboard for the Episodic Series System.

Shows all episodes in a series at a glance with episode cards,
series-level statistics, and quick actions (open, new episode).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGroupBox, QFrame, QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Optional, List, Dict, Any

from core.series_bible import SeriesBible
from core.series_manager import SeriesManager


class EpisodeCard(QFrame):
    """Visual card for a single episode."""

    open_requested = pyqtSignal(str)  # filepath

    def __init__(self, episode_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.episode_data = episode_data
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.setStyleSheet(
            "EpisodeCard { border: 1px solid #ccc; border-radius: 6px; "
            "padding: 8px; margin: 4px; background: palette(base); }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        ep_num = episode_data.get("episode_number", "?")
        title = episode_data.get("title", "Untitled")
        status = episode_data.get("status", "draft")

        header = QLabel(f"<b>Episode {ep_num}: {title}</b>")
        header.setStyleSheet("font-size: 13px;")
        layout.addWidget(header)

        status_label = QLabel(f"Status: {status.capitalize()}")
        status_colors = {"draft": "#888", "in_progress": "#d4a017", "complete": "#228B22"}
        status_label.setStyleSheet(f"color: {status_colors.get(status, '#888')}; font-size: 11px;")
        layout.addWidget(status_label)

        premise = episode_data.get("premise", "")
        if premise:
            premise_label = QLabel(premise[:200] + ("..." if len(premise) > 200 else ""))
            premise_label.setWordWrap(True)
            premise_label.setStyleSheet("color: #555; font-size: 11px;")
            layout.addWidget(premise_label)

        summary = episode_data.get("summary", "")
        if summary:
            summary_label = QLabel(f"<i>{summary[:200]}{'...' if len(summary) > 200 else ''}</i>")
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet("font-size: 11px;")
            layout.addWidget(summary_label)

        scene_count = episode_data.get("scene_count", 0)
        if scene_count:
            layout.addWidget(QLabel(f"Scenes: {scene_count}"))

        filepath = episode_data.get("filepath", "")
        if filepath:
            open_btn = QPushButton("Open Episode")
            open_btn.setMaximumWidth(140)
            open_btn.clicked.connect(lambda: self.open_requested.emit(filepath))
            layout.addWidget(open_btn)


class SeriesDashboard(QDialog):
    """Dashboard showing all episodes in a series."""

    episode_open_requested = pyqtSignal(str)  # filepath
    new_episode_requested = pyqtSignal()
    edit_bible_requested = pyqtSignal()

    def __init__(self, bible: SeriesBible, series_folder: str, parent=None):
        super().__init__(parent)
        self.bible = bible
        self.series_folder = series_folder
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"Series Dashboard — {self.bible.series_title}")
        self.setMinimumSize(600, 450)
        self.resize(720, 520)

        layout = QVBoxLayout(self)

        # Header
        header_row = QHBoxLayout()
        title = QLabel(f"<h2>{self.bible.series_title}</h2>")
        header_row.addWidget(title, 1)

        edit_bible_btn = QPushButton("Edit Series Bible")
        edit_bible_btn.clicked.connect(self.edit_bible_requested.emit)
        header_row.addWidget(edit_bible_btn)

        new_ep_btn = QPushButton("New Episode")
        new_ep_btn.clicked.connect(self.new_episode_requested.emit)
        header_row.addWidget(new_ep_btn)
        layout.addLayout(header_row)

        # Stats
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.stats_label)

        # Episode list scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll, 1)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate()

    def _populate(self):
        # Clear existing cards
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Merge bible episode_history with on-disk files
        file_episodes = SeriesManager.get_episode_list(self.series_folder)
        file_map = {ep["episode_number"]: ep for ep in file_episodes}

        bible_eps = sorted(self.bible.episode_history, key=lambda e: e.get("episode_number", 0))
        displayed = set()

        total_scenes = 0
        for ep in bible_eps:
            ep_num = ep.get("episode_number", 0)
            merged = dict(ep)
            if ep_num in file_map:
                merged["filepath"] = file_map[ep_num]["filepath"]
            card = EpisodeCard(merged)
            card.open_requested.connect(self.episode_open_requested.emit)
            self.card_layout.addWidget(card)
            displayed.add(ep_num)
            total_scenes += ep.get("scene_count", 0)

        # Show file-only episodes not in bible
        for ep in file_episodes:
            if ep["episode_number"] not in displayed:
                card = EpisodeCard(ep)
                card.open_requested.connect(self.episode_open_requested.emit)
                self.card_layout.addWidget(card)

        ep_count = len(bible_eps) or len(file_episodes)
        char_count = len(self.bible.main_characters)
        self.stats_label.setText(
            f"{ep_count} episode(s) | {char_count} persistent character(s) | {total_scenes} total scene(s)"
        )

        if not bible_eps and not file_episodes:
            self.card_layout.addWidget(QLabel("No episodes yet. Click 'New Episode' to get started."))
