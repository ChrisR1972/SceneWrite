"""
Higgsfield API Panel — dock widget for generating images and videos
via the Higgsfield Platform API directly from the screenplay.

Provides:
  - API credential management (persisted to app config)
  - Model selection (image + video)
  - Segment list built from storyboard items
  - One-click generation with progress tracking
  - Result URLs with copy-to-clipboard
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.higgsfield_api_client import (
    ApiConfig,
    ApiError,
    GenerationRequest,
    HiggsfieldApiClient,
    IMAGE_MODELS,
    PipelineResult,
    VIDEO_MODELS,
)
from core.video_prompt_builder import compile_all_prompts


class _WorkerSignals(QObject):
    """Signals emitted by the background generation worker."""
    status_changed = pyqtSignal(int, str, str)   # segment_row, stage, status
    segment_done = pyqtSignal(int, object)        # segment_row, PipelineResult
    all_done = pyqtSignal()
    error = pyqtSignal(int, str)                  # segment_row, error message


class HiggsfieldPanel(QWidget):
    """Dock-widget panel for Higgsfield API generation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.screenplay = None
        self._api_config = ApiConfig()
        self._results: Dict[int, PipelineResult] = {}
        self._running = False
        self._cancel_flag = False

        self._build_ui()
        self._load_credentials()

    # ── UI Construction ──────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_credentials_section())
        layout.addWidget(self._build_model_section())
        layout.addWidget(self._build_segments_section())
        layout.addWidget(self._build_controls_section())
        layout.addWidget(self._build_log_section())
        layout.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll)

    def _build_credentials_section(self) -> QGroupBox:
        group = QGroupBox("API Credentials")
        form = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Higgsfield API key")
        self.api_key_edit.editingFinished.connect(self._save_credentials)
        row1.addWidget(self.api_key_edit)
        form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Secret:"))
        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_secret_edit.setPlaceholderText("Higgsfield API key secret")
        self.api_secret_edit.editingFinished.connect(self._save_credentials)
        row2.addWidget(self.api_secret_edit)
        form.addLayout(row2)

        self.cred_status = QLabel("")
        self.cred_status.setStyleSheet("font-size: 10px;")
        form.addWidget(self.cred_status)
        self._update_cred_status()

        return group

    def _build_model_section(self) -> QGroupBox:
        group = QGroupBox("Models")
        form = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Image:"))
        self.image_model_combo = QComboBox()
        for model_id, label in IMAGE_MODELS.items():
            self.image_model_combo.addItem(label, model_id)
        self.image_model_combo.currentIndexChanged.connect(self._on_model_changed)
        row1.addWidget(self.image_model_combo)
        form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Video:"))
        self.video_model_combo = QComboBox()
        for model_id, label in VIDEO_MODELS.items():
            self.video_model_combo.addItem(label, model_id)
        self.video_model_combo.currentIndexChanged.connect(self._on_model_changed)
        row2.addWidget(self.video_model_combo)
        form.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Duration:"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(2, 10)
        self.duration_spin.setValue(5)
        self.duration_spin.setSuffix("s")
        row3.addWidget(self.duration_spin)
        row3.addStretch()
        form.addLayout(row3)

        return group

    def _build_segments_section(self) -> QGroupBox:
        group = QGroupBox("Segments")
        layout = QVBoxLayout(group)

        self.refresh_btn = QPushButton("Refresh from Screenplay")
        self.refresh_btn.clicked.connect(self._refresh_segments)
        layout.addWidget(self.refresh_btn)

        self.seg_table = QTableWidget(0, 5)
        self.seg_table.setHorizontalHeaderLabels([
            "#", "Shot", "Status", "Image", "Video"
        ])
        self.seg_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.seg_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.seg_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.seg_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.seg_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.seg_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.seg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.seg_table.setMinimumHeight(180)
        layout.addWidget(self.seg_table)

        self.seg_info = QLabel("No screenplay loaded.")
        self.seg_info.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.seg_info)

        return group

    def _build_controls_section(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.generate_btn = QPushButton("Generate All")
        self.generate_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; } "
            "QPushButton:disabled { background-color: #888; }"
        )
        self.generate_btn.clicked.connect(self._on_generate_all)
        layout.addWidget(self.generate_btn)

        self.generate_selected_btn = QPushButton("Generate Selected")
        self.generate_selected_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; padding: 8px 16px; "
            "font-weight: bold; border-radius: 4px; } "
            "QPushButton:disabled { background-color: #888; }"
        )
        self.generate_selected_btn.clicked.connect(self._on_generate_selected)
        layout.addWidget(self.generate_selected_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; padding: 8px 12px; "
            "border-radius: 4px; } "
            "QPushButton:disabled { background-color: #888; }"
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_btn)

        return container

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("Log")
        layout = QVBoxLayout(group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(150)
        self.log_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(self.log_edit)

        return group

    # ── Public API ───────────────────────────────────────────────

    def set_screenplay(self, screenplay):
        self.screenplay = screenplay
        self._refresh_segments()

    # ── Credentials ──────────────────────────────────────────────

    def _load_credentials(self):
        try:
            from config import config as app_config
            data = app_config._config_data.get("higgsfield_api", {})
            if data:
                self._api_config = ApiConfig.from_dict(data)
                self.api_key_edit.setText(self._api_config.api_key)
                self.api_secret_edit.setText(self._api_config.api_key_secret)
                idx = self.image_model_combo.findData(self._api_config.image_model)
                if idx >= 0:
                    self.image_model_combo.setCurrentIndex(idx)
                idx = self.video_model_combo.findData(self._api_config.video_model)
                if idx >= 0:
                    self.video_model_combo.setCurrentIndex(idx)
        except Exception:
            pass
        self._update_cred_status()

    def _save_credentials(self):
        self._api_config.api_key = self.api_key_edit.text().strip()
        self._api_config.api_key_secret = self.api_secret_edit.text().strip()
        self._api_config.image_model = (
            self.image_model_combo.currentData() or "higgsfield-ai/soul/standard"
        )
        self._api_config.video_model = (
            self.video_model_combo.currentData() or "higgsfield-ai/dop/standard"
        )
        try:
            from config import config as app_config
            app_config._config_data["higgsfield_api"] = self._api_config.to_dict()
            app_config._save_config()
        except Exception:
            pass
        self._update_cred_status()

    def _update_cred_status(self):
        if self._api_config.is_configured:
            self.cred_status.setText("Credentials saved.")
            self.cred_status.setStyleSheet("color: #4CAF50; font-size: 10px;")
        else:
            self.cred_status.setText("Enter your Higgsfield API key and secret.")
            self.cred_status.setStyleSheet("color: #ff9800; font-size: 10px;")

    def _on_model_changed(self):
        self._save_credentials()

    # ── Segment Table ────────────────────────────────────────────

    def _refresh_segments(self):
        self.seg_table.setRowCount(0)
        self._segment_data = []

        if not self.screenplay:
            self.seg_info.setText("No screenplay loaded.")
            return

        items = self.screenplay.get_all_storyboard_items()
        if not items:
            self.seg_info.setText(
                "No storyboard items. Generate storyboards first."
            )
            return

        self.seg_table.setRowCount(len(items))
        for row, item in enumerate(items):
            scene = self._find_scene_for_item(item)
            prompts = compile_all_prompts(item, self.screenplay, scene)

            self._segment_data.append({
                "item": item,
                "scene": scene,
                "prompts": prompts,
            })

            num_item = QTableWidgetItem(str(item.sequence_number))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.seg_table.setItem(row, 0, num_item)

            desc = f"{item.shot_type} — {(item.storyline or '')[:60]}"
            self.seg_table.setItem(row, 1, QTableWidgetItem(desc))

            status = QTableWidgetItem("Ready")
            status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.seg_table.setItem(row, 2, status)

            self.seg_table.setItem(row, 3, QTableWidgetItem("—"))
            self.seg_table.setItem(row, 4, QTableWidgetItem("—"))

        self.seg_info.setText(f"{len(items)} segment(s) loaded.")

    def _find_scene_for_item(self, item):
        if not self.screenplay:
            return None
        for act in getattr(self.screenplay, "acts", []):
            for sc in act.scenes:
                if item.item_id in [si.item_id for si in sc.storyboard_items]:
                    return sc
        return None

    # ── Generation ───────────────────────────────────────────────

    def _on_generate_all(self):
        rows = list(range(self.seg_table.rowCount()))
        self._start_generation(rows)

    def _on_generate_selected(self):
        rows = sorted({idx.row() for idx in self.seg_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(
                self, "No Selection", "Select one or more segments to generate."
            )
            return
        self._start_generation(rows)

    def _on_cancel(self):
        self._cancel_flag = True
        self._log("Cancellation requested — finishing current segment...")
        self.cancel_btn.setEnabled(False)

    def _start_generation(self, rows: List[int]):
        if not self._api_config.is_configured:
            QMessageBox.warning(
                self, "Missing Credentials",
                "Enter your Higgsfield API key and secret first."
            )
            return
        if not rows or not self._segment_data:
            return

        self._running = True
        self._cancel_flag = False
        self.generate_btn.setEnabled(False)
        self.generate_selected_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_edit.clear()
        self._log(f"Starting generation for {len(rows)} segment(s)...")

        signals = _WorkerSignals()
        signals.status_changed.connect(self._on_status_update)
        signals.segment_done.connect(self._on_segment_done)
        signals.all_done.connect(self._on_all_done)
        signals.error.connect(self._on_error)

        t = threading.Thread(
            target=self._generation_worker,
            args=(rows, signals),
            daemon=True,
        )
        t.start()

    def _generation_worker(self, rows: List[int], signals: _WorkerSignals):
        client = HiggsfieldApiClient(self._api_config)
        total = len(rows)

        for i, row in enumerate(rows):
            if self._cancel_flag:
                signals.error.emit(row, "Cancelled by user")
                break

            seg = self._segment_data[row]
            item = seg["item"]
            prompts = seg["prompts"]

            keyframe = prompts.get("keyframe_prompt", "")
            video = prompts.get("video_prompt", "")
            hero_url = (item.environment_start_image or "").strip()
            if hero_url and not hero_url.startswith("http"):
                hero_url = ""

            ss = getattr(self.screenplay, "story_settings", {}) or {}
            aspect = ss.get("aspect_ratio", "16:9")
            duration = self.duration_spin.value()

            signals.status_changed.emit(row, "pipeline", "queued")

            try:
                def _on_change(stage, req):
                    signals.status_changed.emit(row, stage, req.status)

                result = client.run_pipeline(
                    keyframe_prompt=keyframe,
                    video_prompt=video,
                    duration=duration,
                    aspect_ratio=aspect,
                    hero_frame_url=hero_url or None,
                    segment_number=item.sequence_number,
                    max_wait_seconds=600,
                    poll_interval=5.0,
                    on_status_change=_on_change,
                )
                signals.segment_done.emit(row, result)
            except Exception as exc:
                signals.error.emit(row, str(exc))

            progress = int(((i + 1) / total) * 100)
            signals.status_changed.emit(row, "progress", str(progress))

        signals.all_done.emit()

    # ── Signal Handlers (UI thread) ──────────────────────────────

    def _on_status_update(self, row: int, stage: str, status: str):
        if stage == "progress":
            self.progress_bar.setValue(int(status))
            return
        status_item = self.seg_table.item(row, 2)
        if status_item:
            display = f"{stage}: {status}"
            status_item.setText(display)
            if status == "completed":
                status_item.setBackground(
                    Qt.GlobalColor.darkGreen
                )
            elif status in ("failed", "nsfw", "timeout"):
                status_item.setBackground(
                    Qt.GlobalColor.darkRed
                )
        self._log(f"Segment {row + 1} [{stage}]: {status}")

    def _on_segment_done(self, row: int, result: PipelineResult):
        self._results[row] = result

        if result.hero_frame_url:
            img_item = QTableWidgetItem("Copy")
            img_item.setToolTip(result.hero_frame_url)
            self.seg_table.setItem(row, 3, img_item)

        if result.video_url:
            vid_item = QTableWidgetItem("Copy")
            vid_item.setToolTip(result.video_url)
            self.seg_table.setItem(row, 4, vid_item)

        status_item = self.seg_table.item(row, 2)
        if result.success:
            if status_item:
                status_item.setText("Done")
            self._log(f"Segment {row + 1}: completed successfully.")
        else:
            if status_item:
                status_item.setText(f"Failed: {result.error or 'unknown'}")
            self._log(f"Segment {row + 1}: FAILED — {result.error}")

    def _on_error(self, row: int, message: str):
        status_item = self.seg_table.item(row, 2)
        if status_item:
            status_item.setText(f"Error: {message[:40]}")
        self._log(f"Segment {row + 1}: ERROR — {message}")

    def _on_all_done(self):
        self._running = False
        self.generate_btn.setEnabled(True)
        self.generate_selected_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        success = sum(1 for r in self._results.values() if r.success)
        total = len(self._results)
        self._log(f"Generation complete: {success}/{total} succeeded.")

        if success > 0:
            self._log(
                "Tip: Hover over 'Copy' cells in the Image/Video columns to see "
                "URLs. Click a cell and press Ctrl+C or right-click to copy."
            )

    # ── Helpers ──────────────────────────────────────────────────

    def _log(self, text: str):
        self.log_edit.append(text)
        sb = self.log_edit.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())
