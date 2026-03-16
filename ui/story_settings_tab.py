"""Story Settings tab -- per-project cinematic and audio generation controls.

The Generation Platform selector drives which video/image models appear and
which platform-specific controls are visible.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.prompt_adapters import PLATFORM_REGISTRY, get_adapter_class


class StorySettingsTab(QWidget):
    """Per-project story settings for cinematic and audio generation."""

    data_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._screenplay = None
        self._loading = False
        self._platform_controls: dict = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(self._build_platform_group())
        layout.addWidget(self._build_cinematic_group())
        layout.addWidget(self._build_platform_specific_group())
        layout.addWidget(self._build_audio_group())

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setToolTip("Restore all story settings to their default values.")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        reset_row.addWidget(self.reset_btn)
        layout.addLayout(reset_row)

        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # -- Platform selector ---------------------------------------------

    def _build_platform_group(self) -> QGroupBox:
        group = QGroupBox("Generation Platform")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.platform_combo = QComboBox()
        for pid, cls in PLATFORM_REGISTRY.items():
            self.platform_combo.addItem(f"{cls.platform_name}  —  {cls.description}", pid)
        self.platform_combo.setToolTip(
            "Select the AI video generation platform.\n"
            "This determines available models, controls, and prompt format."
        )
        form.addRow("Platform:", self.platform_combo)

        self.video_model_combo = QComboBox()
        self.video_model_combo.setToolTip("Video generation model for the selected platform.")
        form.addRow("Video Model:", self.video_model_combo)

        self.image_model_combo = QComboBox()
        self.image_model_combo.setToolTip("Image generation model (hero frames).")
        self.image_model_label = QLabel("Image Model:")
        form.addRow(self.image_model_label, self.image_model_combo)

        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)

        return group

    # -- Cinematic controls -------------------------------------------

    def _build_cinematic_group(self) -> QGroupBox:
        group = QGroupBox("Cinematic Controls")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Multi-Shot + Max Duration
        ms_row = QHBoxLayout()

        self.multishot_check = QCheckBox("Enable Multi-Shot Clustering")
        self.multishot_check.setToolTip(
            "When enabled, consecutive storyboard items that share environment, "
            "characters, and vehicles are grouped into a single generation cluster."
        )
        ms_row.addWidget(self.multishot_check)
        self.multishot_label = self.multishot_check

        ms_row.addWidget(QLabel("Max clip duration:"))
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setRange(1, 30)
        self.max_duration_spin.setValue(8)
        self.max_duration_spin.setSuffix("s")
        self.max_duration_spin.setToolTip(
            "Maximum duration (in seconds) for a single generated video clip."
        )
        self.max_duration_label = QLabel("Max clip duration:")
        ms_row.addWidget(self.max_duration_spin)
        ms_row.addStretch()
        form.addRow(ms_row)

        # Aspect Ratio
        self.aspect_ratio_combo = QComboBox()
        self._all_aspect_ratios = [
            ("16:9 (Widescreen)", "16:9"),
            ("9:16 (Vertical / Mobile)", "9:16"),
            ("1:1 (Square)", "1:1"),
            ("4:3 (Classic)", "4:3"),
            ("21:9 (Ultra-wide / Cinematic)", "21:9"),
            ("2.35:1 (Cinema Wide / Anamorphic)", "2.35:1"),
        ]
        for label, value in self._all_aspect_ratios:
            self.aspect_ratio_combo.addItem(label, value)
        self.aspect_ratio_combo.setToolTip(
            "Frame aspect ratio used for image and video generation."
        )
        form.addRow("Aspect Ratio:", self.aspect_ratio_combo)

        # Visual Style
        self.visual_style_combo = QComboBox()
        from core.screenplay_engine import VISUAL_STYLE_OPTIONS
        for key, label in VISUAL_STYLE_OPTIONS.items():
            self.visual_style_combo.addItem(label, key)
        self.visual_style_combo.setToolTip(
            "Default visual rendering style for all generated prompts.\n"
            "Individual storyboard items can override this setting."
        )
        form.addRow("Visual Style:", self.visual_style_combo)

        # Content Rating
        self.content_rating_combo = QComboBox()
        from core.screenplay_engine import CONTENT_RATING_OPTIONS
        for key, label in CONTENT_RATING_OPTIONS.items():
            self.content_rating_combo.addItem(label, key)
        self.content_rating_combo.setToolTip(
            "Controls the content safety level for all AI-generated text and prompts.\n\n"
            "• Unrestricted — No content filtering. Full creative freedom.\n"
            "• Teen (PG-13) — Moderate action/violence, mild language, romantic tension. No gore or explicit content.\n"
            "• Family Friendly (PG) — Mild peril and slapstick OK. No graphic violence, bad language, or sexual content.\n"
            "• Child Safe (G) — No violence, scary imagery, bad language, or mature themes. Bright and positive tone."
        )
        form.addRow("Content Rating:", self.content_rating_combo)

        # Default Focal Length
        self.default_focal_spin = QSpinBox()
        self.default_focal_spin.setRange(8, 50)
        self.default_focal_spin.setValue(35)
        self.default_focal_spin.setSuffix("mm")
        self.default_focal_spin.setToolTip(
            "Default focal length for new storyboard items (8mm ultra-wide to 50mm portrait)."
        )
        form.addRow("Default Focal Length:", self.default_focal_spin)

        # Identity Lock Strength
        self.identity_lock_combo = QComboBox()
        for label, value in [
            ("Relaxed -- allow creative variation", "relaxed"),
            ("Standard -- consistent but flexible", "standard"),
            ("Strict -- enforce exact identity descriptions", "strict"),
        ]:
            self.identity_lock_combo.addItem(label, value)
        self.identity_lock_combo.setCurrentIndex(1)
        self.identity_lock_combo.setToolTip(
            "How strictly identity blocks are enforced in generated prompts."
        )
        self.identity_lock_label = QLabel("Identity Lock Strength:")
        form.addRow(self.identity_lock_label, self.identity_lock_combo)

        # Cinematic Beat Density
        self.beat_density_combo = QComboBox()
        for label, value in [
            ("Sparse -- fewer beats, longer moments", "sparse"),
            ("Balanced -- standard cinematic pacing", "balanced"),
            ("Dense -- rapid beats, fast pacing", "dense"),
        ]:
            self.beat_density_combo.addItem(label, value)
        self.beat_density_combo.setCurrentIndex(1)
        self.beat_density_combo.setToolTip(
            "Controls the number of story beats packed into each scene."
        )
        form.addRow("Cinematic Beat Density:", self.beat_density_combo)

        # Camera Movement Intensity
        self.camera_intensity_combo = QComboBox()
        for label, value in [
            ("Static -- locked-off, minimal movement", "static"),
            ("Subtle -- gentle pans and slow dollies", "subtle"),
            ("Dynamic -- tracking shots, sweeping moves", "dynamic"),
            ("Frenetic -- handheld, rapid motion", "frenetic"),
        ]:
            self.camera_intensity_combo.addItem(label, value)
        self.camera_intensity_combo.setCurrentIndex(1)
        self.camera_intensity_combo.setToolTip(
            "Intensity of camera movement suggested in motion prompts."
        )
        form.addRow("Camera Movement Intensity:", self.camera_intensity_combo)

        # Prompt Output Format
        self.prompt_format_combo = QComboBox()
        for label, value in [
            ("Cinematic Script -- prose-style direction", "cinematic_script"),
            ("Shot List -- numbered shot breakdowns", "shot_list"),
            ("Director Notes -- terse technical cues", "director_notes"),
        ]:
            self.prompt_format_combo.addItem(label, value)
        self.prompt_format_combo.setToolTip(
            "Format used when assembling generation prompts."
        )
        form.addRow("Prompt Output Format:", self.prompt_format_combo)

        return group

    # -- Platform-specific controls ------------------------------------

    def _build_platform_specific_group(self) -> QGroupBox:
        group = QGroupBox("Platform-Specific Options")
        self._platform_specific_group = group
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Duration preset (Sora, Veo, Minimax)
        self.duration_preset_combo = QComboBox()
        self.duration_preset_label = QLabel("Duration Preset:")
        form.addRow(self.duration_preset_label, self.duration_preset_combo)
        self._platform_controls["duration_preset"] = (
            self.duration_preset_label,
            self.duration_preset_combo,
        )

        # Pika: motion strength slider
        self.pika_motion_slider = QSlider(Qt.Orientation.Horizontal)
        self.pika_motion_slider.setRange(1, 5)
        self.pika_motion_slider.setValue(3)
        self.pika_motion_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.pika_motion_slider.setTickInterval(1)
        self.pika_motion_label = QLabel("Motion Strength:")
        self.pika_motion_value_label = QLabel("3")
        pika_row = QHBoxLayout()
        pika_row.addWidget(self.pika_motion_slider)
        pika_row.addWidget(self.pika_motion_value_label)
        pika_widget = QWidget()
        pika_widget.setLayout(pika_row)
        form.addRow(self.pika_motion_label, pika_widget)
        self.pika_motion_slider.valueChanged.connect(
            lambda v: self.pika_motion_value_label.setText(str(v))
        )
        self._platform_controls["pika_motion"] = (
            self.pika_motion_label,
            pika_widget,
        )

        # Luma: loop checkbox
        self.luma_loop_check = QCheckBox("Enable Loop Mode")
        self.luma_loop_check.setToolTip("Generate seamlessly looping video clips.")
        self.luma_loop_label = QLabel("Loop:")
        form.addRow(self.luma_loop_label, self.luma_loop_check)
        self._platform_controls["luma_loop"] = (
            self.luma_loop_label,
            self.luma_loop_check,
        )

        self._hide_all_platform_controls()
        return group

    def _hide_all_platform_controls(self):
        for label, widget in self._platform_controls.values():
            label.setVisible(False)
            widget.setVisible(False)
        self._platform_specific_group.setVisible(False)

    # -- Audio controls -----------------------------------------------

    def _build_audio_group(self) -> QGroupBox:
        group = QGroupBox("Audio Generation Settings")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.dialogue_mode_combo = QComboBox()
        for label, value in [
            ("Generate Dialogue + Audio", "generate"),
            ("Generate Script Only", "script_only"),
            ("Disable Dialogue", "disabled"),
        ]:
            self.dialogue_mode_combo.addItem(label, value)
        form.addRow("Dialogue Generation Mode:", self.dialogue_mode_combo)

        self.sfx_density_combo = QComboBox()
        for label, value in [
            ("Minimal -- essential SFX only", "minimal"),
            ("Cinematic -- environmental + interaction layers", "cinematic"),
            ("High-Impact -- dense trailer-style layering", "high_impact"),
        ]:
            self.sfx_density_combo.addItem(label, value)
        self.sfx_density_combo.setCurrentIndex(1)
        form.addRow("Sound Effects Density:", self.sfx_density_combo)

        self.music_strategy_combo = QComboBox()
        for label, value in [
            ("None -- no music direction", "none"),
            ("Ambient Bed -- low-intensity background tone", "ambient"),
            ("Thematic Score -- recurring motif across scenes", "thematic"),
            ("Full Cinematic Score -- dynamic cue progression", "full_cinematic"),
        ]:
            self.music_strategy_combo.addItem(label, value)
        self.music_strategy_combo.setCurrentIndex(1)
        form.addRow("Music Strategy:", self.music_strategy_combo)

        return group

    # ------------------------------------------------------------------
    # Platform change handler
    # ------------------------------------------------------------------

    def _on_platform_changed(self, _index=None):
        """Reconfigure model combos and visibility when platform changes."""
        platform_id = self.platform_combo.currentData()
        if not platform_id:
            return
        adapter_cls = get_adapter_class(platform_id)
        if not adapter_cls:
            return

        was_loading = self._loading
        self._loading = True
        try:
            # Video models
            self.video_model_combo.blockSignals(True)
            self.video_model_combo.clear()
            for model_id, label in adapter_cls.video_models.items():
                self.video_model_combo.addItem(label, model_id)
            self.video_model_combo.blockSignals(False)

            # Image models
            self.image_model_combo.blockSignals(True)
            self.image_model_combo.clear()
            if adapter_cls.supports_image_generation and adapter_cls.image_models:
                for model_id, label in adapter_cls.image_models.items():
                    self.image_model_combo.addItem(label, model_id)
                self.image_model_combo.setVisible(True)
                self.image_model_label.setVisible(True)
            else:
                self.image_model_combo.setVisible(False)
                self.image_model_label.setVisible(False)
            self.image_model_combo.blockSignals(False)

            # Multi-shot and identity lock only for Higgsfield
            show_higgsfield = adapter_cls.supports_multishot
            self.multishot_check.setVisible(show_higgsfield)
            show_identity_lock = adapter_cls.supports_identity_lock
            self.identity_lock_combo.setVisible(show_identity_lock)
            self.identity_lock_label.setVisible(show_identity_lock)

            # Max duration range
            self.max_duration_spin.setMaximum(adapter_cls.max_duration)
            if self.max_duration_spin.value() > adapter_cls.max_duration:
                self.max_duration_spin.setValue(adapter_cls.max_duration)

            # Aspect ratios
            current_ar = self.aspect_ratio_combo.currentData()
            self.aspect_ratio_combo.blockSignals(True)
            self.aspect_ratio_combo.clear()
            supported = set(adapter_cls.supported_aspect_ratios)
            for label, value in self._all_aspect_ratios:
                if value in supported:
                    self.aspect_ratio_combo.addItem(label, value)
            idx = self.aspect_ratio_combo.findData(current_ar)
            if idx >= 0:
                self.aspect_ratio_combo.setCurrentIndex(idx)
            self.aspect_ratio_combo.blockSignals(False)

            # Platform-specific controls
            self._hide_all_platform_controls()

            any_visible = False

            # Duration presets
            if adapter_cls.duration_presets:
                self.duration_preset_combo.blockSignals(True)
                self.duration_preset_combo.clear()
                for d in adapter_cls.duration_presets:
                    self.duration_preset_combo.addItem(f"{d} seconds", d)
                self.duration_preset_combo.blockSignals(False)
                for w in self._platform_controls["duration_preset"]:
                    w.setVisible(True)
                any_visible = True

            # Pika motion strength
            if platform_id == "pika":
                for w in self._platform_controls["pika_motion"]:
                    w.setVisible(True)
                any_visible = True

            # Luma loop
            if platform_id == "luma":
                for w in self._platform_controls["luma_loop"]:
                    w.setVisible(True)
                any_visible = True

            self._platform_specific_group.setVisible(any_visible)

        finally:
            self._loading = was_loading

        if not self._loading and self._screenplay:
            self._save_to_screenplay()
            self.data_changed.emit()

    # ------------------------------------------------------------------
    # Data <-> UI
    # ------------------------------------------------------------------

    def load_settings(self, screenplay):
        """Populate widgets from the screenplay's story_settings dict."""
        self._screenplay = screenplay
        if not screenplay:
            return

        self._loading = True
        try:
            ss = getattr(screenplay, "story_settings", {}) or {}
            audio = ss.get("audio_settings", {}) or {}
            pc = ss.get("platform_config", {}) or {}

            # Platform (triggers _on_platform_changed which rebuilds model combos)
            self._set_combo_by_data(
                self.platform_combo,
                ss.get("generation_platform", "higgsfield"),
            )
            self._on_platform_changed()

            # Models — set AFTER platform change rebuilt the combos
            self._set_combo_by_data(
                self.video_model_combo,
                ss.get("video_model", ss.get("higgsfield_model", "")),
            )
            self._set_combo_by_data(
                self.image_model_combo,
                ss.get("image_model", ss.get("higgsfield_image_model", "")),
            )

            self.multishot_check.setChecked(ss.get("supports_multishot", False))
            self.max_duration_spin.setValue(ss.get("max_generation_duration_seconds", 8))
            self._set_combo_by_data(self.aspect_ratio_combo, ss.get("aspect_ratio", "16:9"))
            self._set_combo_by_data(self.visual_style_combo, ss.get("visual_style") or "photorealistic")
            self._set_combo_by_data(self.content_rating_combo, ss.get("content_rating") or "unrestricted")
            self.default_focal_spin.setValue(ss.get("default_focal_length", 35))
            self._set_combo_by_data(self.identity_lock_combo, ss.get("identity_lock_strength", "standard"))
            self._set_combo_by_data(self.beat_density_combo, ss.get("cinematic_beat_density", "balanced"))
            self._set_combo_by_data(self.camera_intensity_combo, ss.get("camera_movement_intensity", "subtle"))
            self._set_combo_by_data(self.prompt_format_combo, ss.get("prompt_output_format", "cinematic_script"))

            self._set_combo_by_data(self.dialogue_mode_combo, audio.get("dialogue_generation_mode", "generate"))
            self._set_combo_by_data(self.sfx_density_combo, audio.get("sfx_density", "cinematic"))
            self._set_combo_by_data(self.music_strategy_combo, audio.get("music_strategy", "ambient"))

            # Platform-specific
            if pc.get("duration_preset"):
                self._set_combo_by_data(self.duration_preset_combo, pc["duration_preset"])
            if "pika_motion_strength" in pc:
                self.pika_motion_slider.setValue(pc["pika_motion_strength"])
            if "luma_loop" in pc:
                self.luma_loop_check.setChecked(pc["luma_loop"])

            self._connect_signals()
        finally:
            self._loading = False

    def _connect_signals(self):
        """Wire widget change signals (safe to call multiple times)."""
        for sig in self._change_signals():
            try:
                sig.disconnect(self._on_setting_changed)
            except TypeError:
                pass
            sig.connect(self._on_setting_changed)

    def _change_signals(self):
        return [
            self.platform_combo.currentIndexChanged,
            self.video_model_combo.currentIndexChanged,
            self.image_model_combo.currentIndexChanged,
            self.multishot_check.toggled,
            self.max_duration_spin.valueChanged,
            self.aspect_ratio_combo.currentIndexChanged,
            self.visual_style_combo.currentIndexChanged,
            self.content_rating_combo.currentIndexChanged,
            self.default_focal_spin.valueChanged,
            self.identity_lock_combo.currentIndexChanged,
            self.beat_density_combo.currentIndexChanged,
            self.camera_intensity_combo.currentIndexChanged,
            self.prompt_format_combo.currentIndexChanged,
            self.dialogue_mode_combo.currentIndexChanged,
            self.sfx_density_combo.currentIndexChanged,
            self.music_strategy_combo.currentIndexChanged,
            self.duration_preset_combo.currentIndexChanged,
            self.pika_motion_slider.valueChanged,
            self.luma_loop_check.toggled,
        ]

    def _on_setting_changed(self):
        if self._loading or not self._screenplay:
            return
        self._save_to_screenplay()
        self.data_changed.emit()

    def _reset_to_defaults(self):
        """Reset all controls to their default values and save."""
        from core.screenplay_engine import get_default_story_settings

        if not self._screenplay:
            return

        self._screenplay.story_settings = get_default_story_settings()
        self.load_settings(self._screenplay)
        self.data_changed.emit()

    def _save_to_screenplay(self):
        if not self._screenplay:
            return

        ss = getattr(self._screenplay, "story_settings", None)
        if ss is None:
            from core.screenplay_engine import get_default_story_settings
            ss = get_default_story_settings()
            self._screenplay.story_settings = ss

        ss["generation_platform"] = self.platform_combo.currentData() or "higgsfield"
        ss["video_model"] = self.video_model_combo.currentData() or ""
        ss["image_model"] = self.image_model_combo.currentData() or ""
        ss["supports_multishot"] = self.multishot_check.isChecked()
        ss["max_generation_duration_seconds"] = self.max_duration_spin.value()
        ss["aspect_ratio"] = self.aspect_ratio_combo.currentData() or "16:9"
        ss["visual_style"] = self.visual_style_combo.currentData() or "photorealistic"
        ss["content_rating"] = self.content_rating_combo.currentData() or "unrestricted"
        ss["default_focal_length"] = self.default_focal_spin.value()
        ss["identity_lock_strength"] = self.identity_lock_combo.currentData() or "standard"
        ss["cinematic_beat_density"] = self.beat_density_combo.currentData() or "balanced"
        ss["camera_movement_intensity"] = self.camera_intensity_combo.currentData() or "subtle"
        ss["prompt_output_format"] = self.prompt_format_combo.currentData() or "cinematic_script"

        audio = ss.setdefault("audio_settings", {})
        audio["dialogue_generation_mode"] = self.dialogue_mode_combo.currentData() or "generate"
        audio["sfx_density"] = self.sfx_density_combo.currentData() or "cinematic"
        audio["music_strategy"] = self.music_strategy_combo.currentData() or "ambient"

        # Platform config
        pc = ss.setdefault("platform_config", {})
        if self.duration_preset_combo.isVisible():
            pc["duration_preset"] = self.duration_preset_combo.currentData()
        if self.pika_motion_slider.isVisible():
            pc["pika_motion_strength"] = self.pika_motion_slider.value()
        if self.luma_loop_check.isVisible():
            pc["luma_loop"] = self.luma_loop_check.isChecked()

        # Remove old keys if present
        ss.pop("higgsfield_model", None)
        ss.pop("higgsfield_image_model", None)

        # Validation: if multishot disabled, revert all scenes to single-shot
        if not ss["supports_multishot"]:
            for act in getattr(self._screenplay, "acts", []):
                for scene in getattr(act, "scenes", []):
                    if getattr(scene, "generation_strategy", None) == "multi_shot":
                        scene.generation_strategy = "single_shot"
                        scene.multishot_clusters = []
                        for item in getattr(scene, "storyboard_items", []):
                            item.cluster_id = None
                            item.shot_number_in_cluster = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
