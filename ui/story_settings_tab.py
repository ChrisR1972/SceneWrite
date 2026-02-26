"""Story Settings tab -- per-project cinematic and audio generation controls."""

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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class StorySettingsTab(QWidget):
    """Per-project story settings for cinematic and audio generation."""

    data_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._screenplay = None
        self._loading = False
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

        layout.addWidget(self._build_cinematic_group())
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

    # -- Cinematic controls -------------------------------------------

    def _build_cinematic_group(self) -> QGroupBox:
        group = QGroupBox("Video Model and Cinematic Controls")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # 1) Multi-Shot + Max Duration (side by side)
        ms_row = QHBoxLayout()

        self.multishot_check = QCheckBox("Enable Multi-Shot Clustering")
        self.multishot_check.setToolTip(
            "When enabled, consecutive storyboard items that share environment, "
            "characters, and vehicles are grouped into a single generation cluster."
        )
        ms_row.addWidget(self.multishot_check)

        ms_row.addWidget(QLabel("Max clip duration:"))
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setRange(1, 30)
        self.max_duration_spin.setValue(8)
        self.max_duration_spin.setSuffix("s")
        self.max_duration_spin.setToolTip(
            "Maximum duration (in seconds) for a single generated video clip. "
            "The AI will determine optimal durations up to this limit."
        )
        ms_row.addWidget(self.max_duration_spin)
        ms_row.addStretch()
        form.addRow(ms_row)

        # 2) Aspect Ratio
        self.aspect_ratio_combo = QComboBox()
        for label, value in [
            ("16:9 (Widescreen)", "16:9"),
            ("9:16 (Vertical / Mobile)", "9:16"),
            ("1:1 (Square)", "1:1"),
            ("4:3 (Classic)", "4:3"),
            ("21:9 (Ultra-wide / Cinematic)", "21:9"),
            ("2.35:1 (Cinema Wide / Anamorphic)", "2.35:1"),
        ]:
            self.aspect_ratio_combo.addItem(label, value)
        self.aspect_ratio_combo.setToolTip(
            "Frame aspect ratio used for image and video generation."
        )
        form.addRow("Aspect Ratio:", self.aspect_ratio_combo)

        # 2b) Higgsfield Model
        self.higgsfield_model_combo = QComboBox()
        for label, value in [
            ("DoP Standard — high-quality animation", "higgsfield-ai/dop/standard"),
            ("DoP Preview — fast preview generation", "higgsfield-ai/dop/preview"),
            ("Kling 2.1 Pro — realistic human motion", "kling-video/v2.1/pro/image-to-video"),
            ("Kling 3.0 Pro — faster generation, reduced wait times", "kling-video/v3.0/pro/image-to-video"),
            ("Seedance Pro — character motion", "bytedance/seedance/v1/pro/image-to-video"),
        ]:
            self.higgsfield_model_combo.addItem(label, value)
        self.higgsfield_model_combo.setToolTip(
            "Default video generation model for Higgsfield API export.\n"
            "DoP Standard: general-purpose high quality.\n"
            "Kling 3.0 Pro: fastest, best for realistic human motion.\n"
            "Seedance Pro: best for character animation."
        )
        form.addRow("Video Model:", self.higgsfield_model_combo)

        # 2b2) Higgsfield Image Model
        self.higgsfield_image_model_combo = QComboBox()
        for label, value in [
            ("Soul Standard — creative character images", "higgsfield-ai/soul/standard"),
            ("Soul 2.0 — fashion-forward, cultural fluency", "higgsfield-ai/soul/2.0"),
            ("Nano Banana Pro — 4K image generation", "higgsfield-ai/nano-banana/pro"),
        ]:
            self.higgsfield_image_model_combo.addItem(label, value)
        self.higgsfield_image_model_combo.setToolTip(
            "Model used to generate hero frame images from keyframe prompts.\n"
            "Soul Standard: versatile creative image generation.\n"
            "Soul 2.0: fashion-forward with cultural fluency.\n"
            "Nano Banana Pro: highest quality, 4K resolution."
        )
        form.addRow("Image Model:", self.higgsfield_image_model_combo)

        # 2c) Visual Style
        self.visual_style_combo = QComboBox()
        from core.screenplay_engine import VISUAL_STYLE_OPTIONS
        for key, label in VISUAL_STYLE_OPTIONS.items():
            self.visual_style_combo.addItem(label, key)
        self.visual_style_combo.setToolTip(
            "Default visual rendering style for all generated prompts.\n"
            "Individual storyboard items can override this setting."
        )
        form.addRow("Visual Style:", self.visual_style_combo)

        # 2d) Default Focal Length
        self.default_focal_spin = QSpinBox()
        self.default_focal_spin.setRange(8, 50)
        self.default_focal_spin.setValue(35)
        self.default_focal_spin.setSuffix("mm")
        self.default_focal_spin.setToolTip(
            "Default focal length for new storyboard items (8mm ultra-wide to 50mm portrait).\n"
            "Matches Cinema Studio 2.0 optics simulation."
        )
        form.addRow("Default Focal Length:", self.default_focal_spin)

        # 3) Identity Lock Strength
        self.identity_lock_combo = QComboBox()
        for label, value in [
            ("Relaxed -- allow creative variation", "relaxed"),
            ("Standard -- consistent but flexible", "standard"),
            ("Strict -- enforce exact identity descriptions", "strict"),
        ]:
            self.identity_lock_combo.addItem(label, value)
        self.identity_lock_combo.setCurrentIndex(1)
        self.identity_lock_combo.setToolTip(
            "How strictly identity blocks (character appearances, vehicles, etc.) "
            "are enforced in generated prompts.\n"
            "Relaxed: broad consistency, allows artistic freedom.\n"
            "Standard: balanced fidelity.\n"
            "Strict: exact reproduction of identity descriptions."
        )
        form.addRow("Identity Lock Strength:", self.identity_lock_combo)

        # 4) Cinematic Beat Density
        self.beat_density_combo = QComboBox()
        for label, value in [
            ("Sparse -- fewer beats, longer moments", "sparse"),
            ("Balanced -- standard cinematic pacing", "balanced"),
            ("Dense -- rapid beats, fast pacing", "dense"),
        ]:
            self.beat_density_combo.addItem(label, value)
        self.beat_density_combo.setCurrentIndex(1)
        self.beat_density_combo.setToolTip(
            "Controls the number of story beats packed into each scene.\n"
            "Sparse: slow, contemplative pacing.\n"
            "Balanced: standard narrative rhythm.\n"
            "Dense: high-energy, trailer-like pacing."
        )
        form.addRow("Cinematic Beat Density:", self.beat_density_combo)

        # 5) Camera Movement Intensity
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
            "Intensity of camera movement suggested in motion prompts.\n"
            "Static: tripod-locked compositions.\n"
            "Subtle: slight push-ins, gentle pans.\n"
            "Dynamic: crane shots, tracking, orbits.\n"
            "Frenetic: handheld energy, whip-pans."
        )
        form.addRow("Camera Movement Intensity:", self.camera_intensity_combo)

        # 6) Prompt Output Format
        self.prompt_format_combo = QComboBox()
        for label, value in [
            ("Cinematic Script -- prose-style direction", "cinematic_script"),
            ("Shot List -- numbered shot breakdowns", "shot_list"),
            ("Director Notes -- terse technical cues", "director_notes"),
        ]:
            self.prompt_format_combo.addItem(label, value)
        self.prompt_format_combo.setToolTip(
            "Format used when assembling generation prompts.\n"
            "Cinematic Script: rich, narrative prose.\n"
            "Shot List: concise numbered shots.\n"
            "Director Notes: minimal technical directions."
        )
        form.addRow("Prompt Output Format:", self.prompt_format_combo)

        return group

    # -- Audio controls -----------------------------------------------

    def _build_audio_group(self) -> QGroupBox:
        group = QGroupBox("Audio Generation Settings")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # 1) Dialogue Generation Mode
        self.dialogue_mode_combo = QComboBox()
        for label, value in [
            ("Generate Dialogue + Audio", "generate"),
            ("Generate Script Only", "script_only"),
            ("Disable Dialogue", "disabled"),
        ]:
            self.dialogue_mode_combo.addItem(label, value)
        self.dialogue_mode_combo.setToolTip(
            "Generate Dialogue + Audio: dialogue text with audio direction cues.\n"
            "Generate Script Only: dialogue written but no audio metadata.\n"
            "Disable Dialogue: visual-only scenes, no spoken lines."
        )
        form.addRow("Dialogue Generation Mode:", self.dialogue_mode_combo)

        # 2) Sound Effects Density
        self.sfx_density_combo = QComboBox()
        for label, value in [
            ("Minimal -- essential SFX only", "minimal"),
            ("Cinematic -- environmental + interaction layers", "cinematic"),
            ("High-Impact -- dense trailer-style layering", "high_impact"),
        ]:
            self.sfx_density_combo.addItem(label, value)
        self.sfx_density_combo.setCurrentIndex(1)
        self.sfx_density_combo.setToolTip(
            "Controls how many sound-effect cues are injected into scenes.\n"
            "Minimal: only essential impacts, doors, engines.\n"
            "Cinematic: environmental ambience + interaction SFX.\n"
            "High-Impact: dense layering for trailer-style pacing."
        )
        form.addRow("Sound Effects Density:", self.sfx_density_combo)

        # 3) Music Strategy
        self.music_strategy_combo = QComboBox()
        for label, value in [
            ("None -- no music direction", "none"),
            ("Ambient Bed -- low-intensity background tone", "ambient"),
            ("Thematic Score -- recurring motif across scenes", "thematic"),
            ("Full Cinematic Score -- dynamic cue progression", "full_cinematic"),
        ]:
            self.music_strategy_combo.addItem(label, value)
        self.music_strategy_combo.setCurrentIndex(1)
        self.music_strategy_combo.setToolTip(
            "None: no music cues generated.\n"
            "Ambient Bed: subtle background atmosphere.\n"
            "Thematic Score: recurring musical motifs tied to story.\n"
            "Full Cinematic Score: dynamic cues aligned with beat density."
        )
        form.addRow("Music Strategy:", self.music_strategy_combo)

        return group

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

            self.multishot_check.setChecked(ss.get("supports_multishot", False))
            self.max_duration_spin.setValue(ss.get("max_generation_duration_seconds", 8))
            self._set_combo_by_data(self.aspect_ratio_combo, ss.get("aspect_ratio", "16:9"))
            self._set_combo_by_data(self.higgsfield_model_combo, ss.get("higgsfield_model", "higgsfield-ai/dop/standard"))
            self._set_combo_by_data(self.higgsfield_image_model_combo, ss.get("higgsfield_image_model", "higgsfield-ai/soul/standard"))
            self._set_combo_by_data(self.visual_style_combo, ss.get("visual_style", "photorealistic"))
            self.default_focal_spin.setValue(ss.get("default_focal_length", 35))
            self._set_combo_by_data(self.identity_lock_combo, ss.get("identity_lock_strength", "standard"))
            self._set_combo_by_data(self.beat_density_combo, ss.get("cinematic_beat_density", "balanced"))
            self._set_combo_by_data(self.camera_intensity_combo, ss.get("camera_movement_intensity", "subtle"))
            self._set_combo_by_data(self.prompt_format_combo, ss.get("prompt_output_format", "cinematic_script"))

            self._set_combo_by_data(self.dialogue_mode_combo, audio.get("dialogue_generation_mode", "generate"))
            self._set_combo_by_data(self.sfx_density_combo, audio.get("sfx_density", "cinematic"))
            self._set_combo_by_data(self.music_strategy_combo, audio.get("music_strategy", "ambient"))

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
            self.multishot_check.toggled,
            self.max_duration_spin.valueChanged,
            self.aspect_ratio_combo.currentIndexChanged,
            self.higgsfield_model_combo.currentIndexChanged,
            self.higgsfield_image_model_combo.currentIndexChanged,
            self.visual_style_combo.currentIndexChanged,
            self.default_focal_spin.valueChanged,
            self.identity_lock_combo.currentIndexChanged,
            self.beat_density_combo.currentIndexChanged,
            self.camera_intensity_combo.currentIndexChanged,
            self.prompt_format_combo.currentIndexChanged,
            self.dialogue_mode_combo.currentIndexChanged,
            self.sfx_density_combo.currentIndexChanged,
            self.music_strategy_combo.currentIndexChanged,
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

        ss["supports_multishot"] = self.multishot_check.isChecked()
        ss["max_generation_duration_seconds"] = self.max_duration_spin.value()
        ss["aspect_ratio"] = self.aspect_ratio_combo.currentData() or "16:9"
        ss["higgsfield_model"] = self.higgsfield_model_combo.currentData() or "higgsfield-ai/dop/standard"
        ss["higgsfield_image_model"] = self.higgsfield_image_model_combo.currentData() or "higgsfield-ai/soul/standard"
        ss["visual_style"] = self.visual_style_combo.currentData() or "photorealistic"
        ss["default_focal_length"] = self.default_focal_spin.value()
        ss["identity_lock_strength"] = self.identity_lock_combo.currentData() or "standard"
        ss["cinematic_beat_density"] = self.beat_density_combo.currentData() or "balanced"
        ss["camera_movement_intensity"] = self.camera_intensity_combo.currentData() or "subtle"
        ss["prompt_output_format"] = self.prompt_format_combo.currentData() or "cinematic_script"

        audio = ss.setdefault("audio_settings", {})
        audio["dialogue_generation_mode"] = self.dialogue_mode_combo.currentData() or "generate"
        audio["sfx_density"] = self.sfx_density_combo.currentData() or "cinematic"
        audio["music_strategy"] = self.music_strategy_combo.currentData() or "ambient"

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
