"""
Editor dialog for individual storyboard items.

Organised around the Higgsfield Cinema Studio 2.0 three-layer workflow:
  1. Scene Setup   — storyline, shot settings, optics
  2. Image Mapping — hero frame, entity reference images
  3. Prompt Layers — keyframe, identity, video (generated + editable)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QTextEdit, QComboBox, QPushButton, QSpinBox,
    QGroupBox, QMessageBox, QSizePolicy, QScrollArea, QWidget, QApplication,
    QFileDialog, QGridLayout, QTabWidget, QLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QSize, QPoint
from PyQt6.QtGui import QFont, QPixmap
from .image_thumbnail import ClickableImageLabel
from typing import Optional, Dict, List, Set
from core.screenplay_engine import (
    StoryboardItem, SceneType, SHOT_TYPE_OPTIONS,
    CAMERA_MOTION_OPTIONS, APERTURE_STYLE_OPTIONS, FOCAL_LENGTH_RANGE,
    VISUAL_STYLE_OPTIONS,
)
from core.ai_generator import AIGenerator
from core.spell_checker import enable_spell_checking


class _FlowLayout(QLayout):
    """Compact flow layout that wraps widgets like text in a paragraph."""

    def __init__(self, parent=None, spacing=4):
        super().__init__(parent)
        self._items: List = []
        self._h_spacing = spacing
        self._v_spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            sz = item.sizeHint()
            next_x = x + sz.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + sz.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x = next_x
            line_height = max(line_height, sz.height())

        return y + line_height - rect.y() + m.bottom()


class StoryboardItemEditor(QDialog):
    """Dialog for editing a storyboard item."""

    item_saved = pyqtSignal(StoryboardItem)

    def __init__(self, item: StoryboardItem, screenplay=None,
                 ai_generator: Optional[AIGenerator] = None, parent=None):
        super().__init__(parent)
        self.item = item
        self.screenplay = screenplay
        self.ai_generator = ai_generator
        self.init_ui()
        self.load_item_data()

    # ================================================================
    #  UI Construction
    # ================================================================

    def init_ui(self):
        self.setWindowTitle(f"Edit Storyboard Item #{self.item.sequence_number}")

        screen = QApplication.primaryScreen().geometry()
        max_w = int(screen.width() * 0.9)
        max_h = int(screen.height() * 0.9)
        self.setMinimumWidth(720)
        self.setMinimumHeight(620)
        self.setMaximumWidth(max_w)
        self.setMaximumHeight(max_h)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # --- Section 1: Scene Setup ---
        layout.addWidget(self._build_scene_setup_group())

        # --- Section 2: Storyline & Dialogue ---
        layout.addWidget(self._build_storyline_group())
        layout.addWidget(self._build_dialogue_group())

        # --- Section 3: Image Mapping ---
        layout.addWidget(self._build_image_mapping_group())

        # --- Section 4: Prompt Layers ---
        layout.addWidget(self._build_prompt_layers_group())

        # --- Section 5: Audio (optional) ---
        layout.addWidget(self._build_audio_group())

        # --- Multi-shot cluster info ---
        layout.addWidget(self._build_cluster_group())

        layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Save/Cancel buttons (always visible)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.clicked.connect(self.save_item)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)

        main_layout.addLayout(btn_layout)

        # Tab key moves focus in form fields
        for w in (self.storyline_edit, self.dialogue_edit):
            w.setTabChangesFocus(True)

        # Spell checking
        enable_spell_checking(self.storyline_edit)
        enable_spell_checking(self.dialogue_edit)

        self.center_on_screen()

    # ── Scene Setup ──────────────────────────────────────────────

    def _build_scene_setup_group(self) -> QGroupBox:
        group = QGroupBox("Scene Setup")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Row 1: Duration + Scene Type
        row1 = QHBoxLayout()
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 30)
        self.duration_spinbox.setSuffix("s")
        self.duration_spinbox.setValue(self.item.duration)
        row1.addWidget(QLabel("Duration:"))
        row1.addWidget(self.duration_spinbox)
        row1.addSpacing(20)
        self.scene_type_combo = QComboBox()
        for st in SceneType:
            self.scene_type_combo.addItem(st.value.title(), st)
        row1.addWidget(QLabel("Scene Type:"))
        row1.addWidget(self.scene_type_combo)
        row1.addStretch()
        form.addRow(row1)

        # Row 2: Shot Type + Camera Motion
        row2 = QHBoxLayout()
        self.shot_type_combo = QComboBox()
        for key, label in SHOT_TYPE_OPTIONS.items():
            self.shot_type_combo.addItem(label, key)
        self.shot_type_combo.setMinimumWidth(180)
        row2.addWidget(QLabel("Shot Type:"))
        row2.addWidget(self.shot_type_combo)
        row2.addSpacing(20)
        self.camera_motion_combo = QComboBox()
        for key, label in CAMERA_MOTION_OPTIONS.items():
            self.camera_motion_combo.addItem(label, key)
        self.camera_motion_combo.setMinimumWidth(180)
        row2.addWidget(QLabel("Camera Motion:"))
        row2.addWidget(self.camera_motion_combo)
        row2.addStretch()
        form.addRow(row2)

        # Row 3: Focal Length + Aperture
        row3 = QHBoxLayout()
        self.focal_length_spin = QSpinBox()
        self.focal_length_spin.setRange(*FOCAL_LENGTH_RANGE)
        self.focal_length_spin.setSuffix("mm")
        self.focal_length_spin.setValue(35)
        self.focal_length_spin.setToolTip(
            "Focal length simulates real camera optics (8mm ultra-wide to 50mm portrait)."
        )
        row3.addWidget(QLabel("Focal Length:"))
        row3.addWidget(self.focal_length_spin)
        row3.addSpacing(20)
        self.aperture_combo = QComboBox()
        for key, label in APERTURE_STYLE_OPTIONS.items():
            self.aperture_combo.addItem(label, key)
        self.aperture_combo.setMinimumWidth(200)
        row3.addWidget(QLabel("Aperture:"))
        row3.addWidget(self.aperture_combo)
        row3.addSpacing(20)
        self.visual_style_combo = QComboBox()
        self.visual_style_combo.addItem("Project Default", "")
        for key, label in VISUAL_STYLE_OPTIONS.items():
            self.visual_style_combo.addItem(label, key)
        self.visual_style_combo.setMinimumWidth(200)
        self.visual_style_combo.setToolTip(
            "Visual rendering style for this item.\n"
            "\"Project Default\" uses the style set in Story Settings."
        )
        row3.addWidget(QLabel("Visual Style:"))
        row3.addWidget(self.visual_style_combo)
        row3.addStretch()
        form.addRow(row3)

        # Row 4: Mood/Tone + Lighting
        row4 = QHBoxLayout()
        self.mood_edit = QComboBox()
        self.mood_edit.setEditable(True)
        self.mood_edit.setMinimumWidth(180)
        for mood in ("", "Moody and tense", "Warm and hopeful", "Cold and clinical",
                      "Ethereal", "Gritty and raw", "Playful", "Melancholic",
                      "Epic and grand", "Intimate", "Mysterious"):
            self.mood_edit.addItem(mood)
        self.mood_edit.setToolTip("Mood/tone for the hero frame. Type a custom value or select a preset.")
        row4.addWidget(QLabel("Mood:"))
        row4.addWidget(self.mood_edit)
        row4.addSpacing(20)
        self.lighting_edit = QComboBox()
        self.lighting_edit.setEditable(True)
        self.lighting_edit.setMinimumWidth(220)
        for light in ("", "Natural daylight", "Golden hour", "Soft diffused light",
                       "Harsh shadows", "Neon-lit", "Candlelight", "Overcast flat light",
                       "Backlit silhouette", "Streetlight from left", "Studio three-point"):
            self.lighting_edit.addItem(light)
        self.lighting_edit.setToolTip("Lighting description for the hero frame.")
        row4.addWidget(QLabel("Lighting:"))
        row4.addWidget(self.lighting_edit)
        row4.addStretch()
        form.addRow(row4)

        return group

    # ── Storyline ────────────────────────────────────────────────

    def _build_storyline_group(self) -> QGroupBox:
        group = QGroupBox("Storyline")
        layout = QVBoxLayout(group)
        hint = QLabel(
            "What happens in this segment (2-4 sentences). "
            "This drives the keyframe and video prompt generation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 9px; padding: 2px;")
        layout.addWidget(hint)
        self.storyline_edit = QTextEdit()
        self.storyline_edit.setPlaceholderText(
            "Describe what happens in this segment..."
        )
        self.storyline_edit.setMinimumHeight(80)
        self.storyline_edit.setMaximumHeight(90)
        self.storyline_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.storyline_edit.setFont(QFont("Arial", 9))
        layout.addWidget(self.storyline_edit)
        return group

    # ── Dialogue ─────────────────────────────────────────────────

    def _build_dialogue_group(self) -> QGroupBox:
        group = QGroupBox("Dialogue")
        layout = QVBoxLayout(group)
        hint = QLabel(
            "Character dialogue for this segment. Format: CHARACTER: \"Dialogue text\""
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 9px; padding: 2px;")
        layout.addWidget(hint)
        self.dialogue_edit = QTextEdit()
        self.dialogue_edit.setPlaceholderText(
            "CHARACTER: \"Dialogue text...\""
        )
        self.dialogue_edit.setMinimumHeight(60)
        self.dialogue_edit.setMaximumHeight(70)
        self.dialogue_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.dialogue_edit.setFont(QFont("Arial", 9))
        layout.addWidget(self.dialogue_edit)
        return group

    # ── Image Mapping ────────────────────────────────────────────

    def _build_image_mapping_group(self) -> QGroupBox:
        group = QGroupBox("Image Mapping")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # Hero frame (environment start) + end frame
        env_grid = QGridLayout()
        env_grid.setSpacing(6)

        env_grid.addWidget(QLabel("Hero Frame (Required):"), 0, 0)
        self.env_start_thumb = ClickableImageLabel(max_short=60, max_long=80)
        env_grid.addWidget(self.env_start_thumb, 0, 1)
        self.env_start_btn = QPushButton("Upload")
        self.env_start_btn.setFixedWidth(70)
        self.env_start_btn.clicked.connect(lambda: self._upload_env_image("start"))
        env_grid.addWidget(self.env_start_btn, 0, 2)
        self.env_start_clear = QPushButton("Clear")
        self.env_start_clear.setFixedWidth(60)
        self.env_start_clear.clicked.connect(lambda: self._clear_env_image("start"))
        env_grid.addWidget(self.env_start_clear, 0, 3)
        env_grid.addWidget(QLabel("Assign to:"), 0, 4)
        self.hero_frame_combo = QComboBox()
        self.hero_frame_combo.setMinimumWidth(180)
        self.hero_frame_combo.addItem("(Unassigned)", "")
        self.hero_frame_combo.currentIndexChanged.connect(
            lambda _idx: self._on_frame_assignment_changed("start"))
        env_grid.addWidget(self.hero_frame_combo, 0, 5)

        env_grid.addWidget(QLabel("End Frame (Optional):"), 1, 0)
        self.env_end_thumb = ClickableImageLabel(max_short=60, max_long=80)
        env_grid.addWidget(self.env_end_thumb, 1, 1)
        self.env_end_btn = QPushButton("Upload")
        self.env_end_btn.setFixedWidth(70)
        self.env_end_btn.clicked.connect(lambda: self._upload_env_image("end"))
        env_grid.addWidget(self.env_end_btn, 1, 2)
        self.env_end_clear = QPushButton("Clear")
        self.env_end_clear.setFixedWidth(60)
        self.env_end_clear.clicked.connect(lambda: self._clear_env_image("end"))
        env_grid.addWidget(self.env_end_clear, 1, 3)
        env_grid.addWidget(QLabel("Assign to:"), 1, 4)
        self.end_frame_combo = QComboBox()
        self.end_frame_combo.setMinimumWidth(180)
        self.end_frame_combo.addItem("(Unassigned)", "")
        self.end_frame_combo.currentIndexChanged.connect(
            lambda _idx: self._on_frame_assignment_changed("end"))
        env_grid.addWidget(self.end_frame_combo, 1, 5)

        layout.addLayout(env_grid)

        # Entity reference image slots
        entity_grid = QGridLayout()
        entity_grid.setSpacing(6)
        self._image_slot_widgets: Dict[str, dict] = {}
        for idx, slot in enumerate(("image_1", "image_2", "image_3")):
            label_text = slot.replace("_", " ").title()
            entity_grid.addWidget(QLabel(f"{label_text}:"), idx, 0)

            thumb = ClickableImageLabel(max_short=60, max_long=80)
            entity_grid.addWidget(thumb, idx, 1)

            upload_btn = QPushButton("Upload")
            upload_btn.setFixedWidth(70)
            entity_grid.addWidget(upload_btn, idx, 2)

            clear_btn = QPushButton("Clear")
            clear_btn.setFixedWidth(60)
            entity_grid.addWidget(clear_btn, idx, 3)

            entity_grid.addWidget(QLabel("Assign to:"), idx, 4)
            combo = QComboBox()
            combo.setMinimumWidth(180)
            combo.addItem("(Unassigned)", "")
            entity_grid.addWidget(combo, idx, 5)

            self._image_slot_widgets[slot] = {
                "thumb": thumb, "upload": upload_btn,
                "clear": clear_btn, "combo": combo,
            }
            upload_btn.clicked.connect(
                lambda checked, s=slot: self._upload_entity_image(s)
            )
            clear_btn.clicked.connect(
                lambda checked, s=slot: self._clear_entity_image(s)
            )
            combo.currentIndexChanged.connect(
                lambda _idx, s=slot: self._on_assignment_changed(s)
            )

        layout.addLayout(entity_grid)

        # Entity tags — visual hint for identity-block vs markup-only entities
        entity_tags_header = QLabel("Entities in Scene:")
        entity_tags_header.setStyleSheet("font-size: 10px; font-weight: bold; padding: 2px 0 0 0;")
        layout.addWidget(entity_tags_header)

        self._entity_tags_container = QWidget()
        self._entity_tags_layout = _FlowLayout(self._entity_tags_container, spacing=5)
        self._entity_tags_layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self._entity_tags_container)

        legend = QLabel(
            '<span style="color:#888; font-size:9px;">'
            '\u25cf <span style="color:#5b9bd5;">Blue</span> = identity block (reference image assignable)  '
            '\u25cf <span style="color:#999;">Gray</span> = markup only (generator-handled)'
            '</span>'
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(legend)

        # Validation status
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("font-size: 10px; padding: 3px;")
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        return group

    # ── Prompt Layers (tabbed) ───────────────────────────────────

    def _build_prompt_layers_group(self) -> QGroupBox:
        group = QGroupBox("Prompt Layers")
        layout = QVBoxLayout(group)

        # Generate button
        gen_row = QHBoxLayout()
        gen_row.addStretch()
        self.generate_prompts_btn = QPushButton("Generate All Prompts")
        self.generate_prompts_btn.setFixedWidth(200)
        self.generate_prompts_btn.clicked.connect(self._on_generate_prompts)
        gen_row.addWidget(self.generate_prompts_btn)
        gen_row.addStretch()
        layout.addLayout(gen_row)

        # Error label
        self.prompt_error_label = QLabel("")
        self.prompt_error_label.setWordWrap(True)
        self.prompt_error_label.setStyleSheet(
            "color: #ff4444; font-size: 10px; padding: 4px;"
        )
        self.prompt_error_label.hide()
        layout.addWidget(self.prompt_error_label)

        # Tabs for 3 layers
        self.prompt_tabs = QTabWidget()

        # Tab 1: Keyframe Prompt
        kf_widget = QWidget()
        kf_layout = QVBoxLayout(kf_widget)
        kf_hint = QLabel(
            "Hero Frame layer (Popcorn) — static scene description. "
            "No motion verbs. Defines shot, lighting, environment, lens, mood."
        )
        kf_hint.setWordWrap(True)
        kf_hint.setStyleSheet("color: #666; font-size: 9px; padding: 2px;")
        kf_layout.addWidget(kf_hint)
        self.keyframe_prompt_edit = QTextEdit()
        self.keyframe_prompt_edit.setPlaceholderText(
            "Keyframe prompt will be generated from your scene setup..."
        )
        self.keyframe_prompt_edit.setMinimumHeight(120)
        self.keyframe_prompt_edit.setFont(QFont("Consolas", 9))
        kf_layout.addWidget(self.keyframe_prompt_edit)
        kf_copy_row = QHBoxLayout()
        kf_copy_row.addStretch()
        self.copy_keyframe_btn = QPushButton("Copy Keyframe Prompt")
        self.copy_keyframe_btn.setFixedWidth(180)
        self.copy_keyframe_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self.keyframe_prompt_edit)
        )
        kf_copy_row.addWidget(self.copy_keyframe_btn)
        kf_layout.addLayout(kf_copy_row)
        self.prompt_tabs.addTab(kf_widget, "Keyframe (Hero Frame)")

        # Tab 2: Identity Prompt
        id_widget = QWidget()
        id_layout = QVBoxLayout(id_widget)
        id_hint = QLabel(
            "Identity details (character locks, wardrobe, reference images) are managed in the "
            "Identity Blocks and Character Details tabs. The identity prompt is auto-generated "
            "from those settings when you click Generate Prompts."
        )
        id_hint.setWordWrap(True)
        id_hint.setStyleSheet("color: #666; font-size: 11px; padding: 8px 4px;")
        id_layout.addWidget(id_hint)
        self.identity_prompt_edit = QTextEdit()
        self.identity_prompt_edit.setReadOnly(True)
        self.identity_prompt_edit.setMinimumHeight(120)
        self.identity_prompt_edit.setFont(QFont("Consolas", 9))
        self.identity_prompt_edit.setStyleSheet("")
        id_layout.addWidget(self.identity_prompt_edit)
        id_copy_row = QHBoxLayout()
        id_copy_row.addStretch()
        self.copy_identity_btn = QPushButton("Copy Identity Prompt")
        self.copy_identity_btn.setFixedWidth(180)
        self.copy_identity_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self.identity_prompt_edit)
        )
        id_copy_row.addWidget(self.copy_identity_btn)
        id_layout.addLayout(id_copy_row)
        self.prompt_tabs.addTab(id_widget, "Identity (Soul ID)")

        # Tab 3: Video Prompt
        vp_widget = QWidget()
        vp_layout = QVBoxLayout(vp_widget)
        vp_hint = QLabel(
            "Video layer (Motion) — camera movement, action, dialogue, audio. "
            "Camera verbs (dolly, orbit, handheld) are encouraged here."
        )
        vp_hint.setWordWrap(True)
        vp_hint.setStyleSheet("color: #666; font-size: 9px; padding: 2px;")
        vp_layout.addWidget(vp_hint)
        self.video_prompt_edit = QTextEdit()
        self.video_prompt_edit.setPlaceholderText(
            "Video prompt will be generated from storyline, camera motion, and dialogue..."
        )
        self.video_prompt_edit.setMinimumHeight(140)
        self.video_prompt_edit.setFont(QFont("Consolas", 9))
        vp_layout.addWidget(self.video_prompt_edit)
        vp_copy_row = QHBoxLayout()
        vp_copy_row.addStretch()
        self.copy_video_btn = QPushButton("Copy Video Prompt")
        self.copy_video_btn.setFixedWidth(180)
        self.copy_video_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self.video_prompt_edit)
        )
        vp_copy_row.addWidget(self.copy_video_btn)
        vp_layout.addLayout(vp_copy_row)
        self.prompt_tabs.addTab(vp_widget, "Video (Motion)")

        layout.addWidget(self.prompt_tabs)

        # Copy All button
        all_copy_row = QHBoxLayout()
        all_copy_row.addStretch()
        self.copy_all_btn = QPushButton("Copy All Prompts")
        self.copy_all_btn.setFixedWidth(160)
        self.copy_all_btn.clicked.connect(self._on_copy_all_prompts)
        all_copy_row.addWidget(self.copy_all_btn)
        all_copy_row.addStretch()
        layout.addLayout(all_copy_row)

        return group

    # ── Audio (optional) ─────────────────────────────────────────

    def _build_audio_group(self) -> QGroupBox:
        self.audio_group = QGroupBox("Audio Intent (optional)")
        self.audio_group.setCheckable(True)
        self.audio_group.setChecked(False)
        self.audio_group.setToolTip("Optional sound design notes.")
        layout = QVBoxLayout(self.audio_group)

        lbl = QLabel("Audio intent:")
        lbl.setStyleSheet("color: #666; font-size: 9px;")
        layout.addWidget(lbl)
        self.audio_intent_edit = QTextEdit()
        self.audio_intent_edit.setPlaceholderText(
            "e.g., Soft rain ambience with distant city hum"
        )
        self.audio_intent_edit.setMaximumHeight(50)
        self.audio_intent_edit.setTabChangesFocus(True)
        layout.addWidget(self.audio_intent_edit)

        lbl2 = QLabel("Audio notes:")
        lbl2.setStyleSheet("color: #666; font-size: 9px;")
        layout.addWidget(lbl2)
        self.audio_notes_edit = QTextEdit()
        self.audio_notes_edit.setPlaceholderText("Free-form notes")
        self.audio_notes_edit.setMaximumHeight(50)
        self.audio_notes_edit.setTabChangesFocus(True)
        layout.addWidget(self.audio_notes_edit)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Audio source:"))
        self.audio_source_combo = QComboBox()
        self.audio_source_combo.addItem("None", "none")
        self.audio_source_combo.addItem("Generated with video", "generated")
        self.audio_source_combo.addItem("Added in post", "post")
        src_row.addWidget(self.audio_source_combo)
        src_row.addStretch()
        layout.addLayout(src_row)

        return self.audio_group

    # ── Multi-shot cluster info ──────────────────────────────────

    def _build_cluster_group(self) -> QGroupBox:
        self.cluster_group = QGroupBox("Multi-Shot Cluster")
        form = QFormLayout(self.cluster_group)
        self.cluster_id_label = QLabel("")
        form.addRow("Cluster ID:", self.cluster_id_label)
        self.cluster_shot_label = QLabel("")
        form.addRow("Shot:", self.cluster_shot_label)
        self.cluster_duration_label = QLabel("")
        form.addRow("Total Duration:", self.cluster_duration_label)
        self.cluster_transition_label = QLabel("")
        self.cluster_transition_label.setWordWrap(True)
        form.addRow("Transition:", self.cluster_transition_label)
        self.cluster_group.setVisible(False)
        return self.cluster_group

    # ================================================================
    #  Data Loading
    # ================================================================

    def load_item_data(self):
        """Populate all editor fields from the item."""
        self.duration_spinbox.setValue(self.item.duration)

        # Scene type
        for i in range(self.scene_type_combo.count()):
            if self.scene_type_combo.itemData(i) == self.item.scene_type:
                self.scene_type_combo.setCurrentIndex(i)
                break

        # Shot type
        shot = getattr(self.item, "shot_type", "wide") or "wide"
        idx = self.shot_type_combo.findData(shot)
        if idx >= 0:
            self.shot_type_combo.setCurrentIndex(idx)

        # Camera motion
        motion = getattr(self.item, "camera_motion", "static") or "static"
        idx = self.camera_motion_combo.findData(motion)
        if idx >= 0:
            self.camera_motion_combo.setCurrentIndex(idx)

        # Focal length
        self.focal_length_spin.setValue(getattr(self.item, "focal_length", 35) or 35)

        # Aperture
        ap = getattr(self.item, "aperture_style", "cinematic_bokeh") or "cinematic_bokeh"
        idx = self.aperture_combo.findData(ap)
        if idx >= 0:
            self.aperture_combo.setCurrentIndex(idx)

        # Visual style override
        vs = getattr(self.item, "visual_style", "") or ""
        idx = self.visual_style_combo.findData(vs)
        if idx >= 0:
            self.visual_style_combo.setCurrentIndex(idx)

        # Mood
        mood = getattr(self.item, "mood_tone", "") or ""
        self.mood_edit.setCurrentText(mood)

        # Lighting
        lighting = getattr(self.item, "lighting_description", "") or ""
        self.lighting_edit.setCurrentText(lighting)

        # Text fields
        self.storyline_edit.setPlainText(self.item.storyline)
        self.dialogue_edit.setPlainText(self.item.dialogue)

        # Prompt layers (load existing prompts into the editable fields)
        self.keyframe_prompt_edit.setPlainText(self.item.image_prompt)
        self.video_prompt_edit.setPlainText(self.item.prompt)

        # Audio
        self.audio_intent_edit.setPlainText(
            getattr(self.item, "audio_intent", "") or ""
        )
        self.audio_notes_edit.setPlainText(
            getattr(self.item, "audio_notes", "") or ""
        )
        src = getattr(self.item, "audio_source", "none") or "none"
        idx = self.audio_source_combo.findData(
            src if src in ("none", "generated", "post") else "none"
        )
        if idx >= 0:
            self.audio_source_combo.setCurrentIndex(idx)
        has_audio = bool(
            (getattr(self.item, "audio_intent", "") or "").strip()
            or (getattr(self.item, "audio_notes", "") or "").strip()
        )
        self.audio_group.setChecked(has_audio)
        if self.screenplay:
            strategy = (
                getattr(self.screenplay, "audio_strategy", "generated_with_video")
                or "generated_with_video"
            )
            self.audio_group.setVisible(strategy != "no_audio")

        # Image mapping
        self._populate_entity_combos()
        if (getattr(self.item, "environment_start_image", "") or "").strip():
            self._set_thumb(self.env_start_thumb, self.item.environment_start_image)
        if (getattr(self.item, "environment_end_image", "") or "").strip():
            self._set_thumb(self.env_end_thumb, self.item.environment_end_image)
        self._restore_entity_assignments()
        self._populate_entity_tags()
        self._update_validation()

        # Multi-shot cluster info
        self._load_cluster_info()

    # ================================================================
    #  Prompt Generation
    # ================================================================

    def _on_generate_prompts(self):
        """Generate all three prompt layers from current editor state."""
        self.prompt_error_label.hide()

        if not self.screenplay:
            self.prompt_error_label.setText("No screenplay loaded.")
            self.prompt_error_label.show()
            return

        # Sync editor values into the item
        self._sync_item_from_ui()

        scene = self._find_parent_scene()

        from core.video_prompt_builder import compile_all_prompts
        result = compile_all_prompts(self.item, self.screenplay, scene)

        if not result["success"]:
            self.prompt_error_label.setText("\n".join(result["errors"]))
            self.prompt_error_label.show()
            return

        self.keyframe_prompt_edit.setPlainText(result["keyframe_prompt"])
        self.identity_prompt_edit.setPlainText(result["identity_prompt"])
        self.video_prompt_edit.setPlainText(result["video_prompt"])

    def _sync_item_from_ui(self):
        """Write current UI values back to the item object."""
        self.item.duration = self.duration_spinbox.value()
        self.item.scene_type = self.scene_type_combo.currentData() or SceneType.ACTION
        self.item.shot_type = self.shot_type_combo.currentData() or "wide"
        self.item.camera_motion = self.camera_motion_combo.currentData() or "static"
        self.item.focal_length = self.focal_length_spin.value()
        self.item.aperture_style = self.aperture_combo.currentData() or "cinematic_bokeh"
        self.item.visual_style = self.visual_style_combo.currentData() or ""
        self.item.mood_tone = self.mood_edit.currentText().strip()
        self.item.lighting_description = self.lighting_edit.currentText().strip()
        self.item.storyline = self.storyline_edit.toPlainText().strip()
        self.item.dialogue = self.dialogue_edit.toPlainText().strip()
        self.item.image_prompt = self.keyframe_prompt_edit.toPlainText().strip()
        self.item.prompt = self.video_prompt_edit.toPlainText().strip()
        self.item.camera_notes = CAMERA_MOTION_OPTIONS.get(
            self.item.camera_motion, "Static"
        )

    # ================================================================
    #  Clipboard
    # ================================================================

    def _copy_to_clipboard(self, text_edit: QTextEdit):
        text = text_edit.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)

    def _on_copy_all_prompts(self):
        parts = []
        kf = self.keyframe_prompt_edit.toPlainText().strip()
        if kf:
            parts.append(f"--- KEYFRAME (Hero Frame) ---\n{kf}")
        ip = self.identity_prompt_edit.toPlainText().strip()
        if ip:
            parts.append(f"--- IDENTITY ---\n{ip}")
        vp = self.video_prompt_edit.toPlainText().strip()
        if vp:
            parts.append(f"--- VIDEO (Motion) ---\n{vp}")
        if parts:
            QApplication.clipboard().setText("\n\n".join(parts))

    # ================================================================
    #  Image Mapping Helpers
    # ================================================================

    def _upload_env_image(self, which: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {'Hero Frame' if which == 'start' else 'End Frame'}",
            "",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        if which == "start":
            self.item.environment_start_image = path
            self._set_thumb(self.env_start_thumb, path)
        else:
            self.item.environment_end_image = path
            self._set_thumb(self.env_end_thumb, path)
        self._update_validation()

    def _clear_env_image(self, which: str):
        if which == "start":
            self.item.environment_start_image = ""
            self.env_start_thumb.clearImage()
        else:
            self.item.environment_end_image = ""
            self.env_end_thumb.clearImage()
        self._update_validation()

    def _upload_entity_image(self, slot: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {slot.replace('_', ' ').title()} Reference Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        widgets = self._image_slot_widgets[slot]
        self._set_thumb(widgets["thumb"], path)
        assignments = getattr(self.item, "image_assignments", None) or {}
        if slot not in assignments:
            assignments[slot] = {}
        assignments[slot]["path"] = path
        self.item.image_assignments = assignments
        self._update_validation()

    def _clear_entity_image(self, slot: str):
        widgets = self._image_slot_widgets[slot]
        widgets["thumb"].clearImage()
        widgets["combo"].setCurrentIndex(0)
        assignments = getattr(self.item, "image_assignments", None) or {}
        assignments.pop(slot, None)
        self.item.image_assignments = assignments
        self._update_validation()

    def _on_assignment_changed(self, slot: str):
        widgets = self._image_slot_widgets[slot]
        combo = widgets["combo"]
        data = combo.currentData()
        assignments = getattr(self.item, "image_assignments", None) or {}
        if slot not in assignments:
            assignments[slot] = {}
        if data and isinstance(data, dict):
            entity_id = data.get("entity_id", "")
            assignments[slot]["entity_id"] = entity_id
            assignments[slot]["entity_name"] = data.get("entity_name", "")
            assignments[slot]["entity_type"] = data.get("entity_type", "")
            if entity_id:
                auto_path = self._lookup_entity_image(entity_id)
                if auto_path:
                    assignments[slot]["path"] = auto_path
                    self._set_thumb(widgets["thumb"], auto_path)
        else:
            assignments[slot].pop("entity_id", None)
            assignments[slot].pop("entity_name", None)
            assignments[slot].pop("entity_type", None)
        self.item.image_assignments = assignments
        self._update_validation()

    def _lookup_entity_image(self, entity_id: str) -> str:
        """Look up the best available image for an entity.

        For characters, checks the current scene's wardrobe variant first,
        then falls back to the main identity block image_path.
        """
        if not self.screenplay:
            return ""
        meta = getattr(self.screenplay, "identity_block_metadata", {}) or {}
        entity_meta = meta.get(entity_id)
        if not entity_meta:
            return ""

        etype = (entity_meta.get("type") or "").lower()

        if etype == "character":
            scene = self._find_parent_scene()
            if scene:
                sid = getattr(scene, "scene_id", "")
                variant = self.screenplay.get_scene_wardrobe_variant(sid, entity_id)
                if variant:
                    vpath = (variant.get("image_path") or "").strip()
                    if vpath:
                        return vpath

        return (entity_meta.get("image_path") or "").strip()

    def _on_frame_assignment_changed(self, which: str):
        """Handle hero frame or end frame entity assignment change."""
        if which == "start":
            combo = self.hero_frame_combo
            thumb = self.env_start_thumb
        else:
            combo = self.end_frame_combo
            thumb = self.env_end_thumb

        data = combo.currentData()
        entity_id = ""
        if data and isinstance(data, dict):
            entity_id = data.get("entity_id", "")

        if which == "start":
            self.item.hero_frame_entity_id = entity_id
        else:
            self.item.end_frame_entity_id = entity_id

        if entity_id:
            auto_path = self._lookup_entity_image(entity_id)
            if auto_path:
                if which == "start":
                    self.item.environment_start_image = auto_path
                else:
                    self.item.environment_end_image = auto_path
                self._set_thumb(thumb, auto_path)

        self._update_validation()

    def _set_thumb(self, label, path: str):
        label.setImageFromPath(path)

    def _populate_entity_combos(self):
        """Fill assignment dropdowns with screenplay entities."""
        char_obj_veh: list = []
        all_entities: list = []
        if self.screenplay:
            meta = getattr(self.screenplay, "identity_block_metadata", {}) or {}
            for eid, m in meta.items():
                etype = m.get("type", "")
                ename = (m.get("name") or "").strip()
                if not ename:
                    continue
                entry = {
                    "entity_id": eid,
                    "entity_name": ename,
                    "entity_type": etype,
                }
                all_entities.append(entry)
                if etype in ("character", "object", "vehicle"):
                    char_obj_veh.append(entry)

        for slot, widgets in self._image_slot_widgets.items():
            combo: QComboBox = widgets["combo"]
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(Unassigned)", "")
            for ent in char_obj_veh:
                label = f"{ent['entity_name']}  [{ent['entity_type']}]"
                combo.addItem(label, ent)
            combo.blockSignals(False)

        for frame_combo in (self.hero_frame_combo, self.end_frame_combo):
            frame_combo.blockSignals(True)
            frame_combo.clear()
            frame_combo.addItem("(Unassigned)", "")
            for ent in all_entities:
                label = f"{ent['entity_name']}  [{ent['entity_type']}]"
                frame_combo.addItem(label, ent)
            frame_combo.blockSignals(False)

    def _restore_entity_assignments(self):
        """Set combo selections from item.image_assignments and frame entity IDs."""
        assignments = getattr(self.item, "image_assignments", {}) or {}
        for slot, widgets in self._image_slot_widgets.items():
            info = assignments.get(slot)
            if not info:
                continue
            path = (info.get("path") or "").strip()
            if path:
                self._set_thumb(widgets["thumb"], path)
            entity_id = (info.get("entity_id") or "").strip()
            if entity_id:
                combo: QComboBox = widgets["combo"]
                combo.blockSignals(True)
                for i in range(combo.count()):
                    d = combo.itemData(i)
                    if isinstance(d, dict) and d.get("entity_id") == entity_id:
                        combo.setCurrentIndex(i)
                        break
                combo.blockSignals(False)

        for eid_attr, combo in (
            ("hero_frame_entity_id", self.hero_frame_combo),
            ("end_frame_entity_id", self.end_frame_combo),
        ):
            entity_id = (getattr(self.item, eid_attr, "") or "").strip()
            if entity_id:
                combo.blockSignals(True)
                for i in range(combo.count()):
                    d = combo.itemData(i)
                    if isinstance(d, dict) and d.get("entity_id") == entity_id:
                        combo.setCurrentIndex(i)
                        break
                combo.blockSignals(False)

    def _populate_entity_tags(self):
        """Show colour-coded tags for entities found in the storyline.

        Blue tags  = entity has an identity block (reference image assignable).
        Gray tags  = markup-only entity (handled by the generator).
        """
        from core.storyboard_validator import extract_entities

        while self._entity_tags_layout.count():
            child = self._entity_tags_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        storyline = getattr(self.item, "storyline", "") or ""
        if not storyline:
            placeholder = QLabel("No entities detected (empty storyline)")
            placeholder.setStyleSheet("color: #888; font-size: 9px; padding: 2px;")
            self._entity_tags_layout.addWidget(placeholder)
            return

        ent = extract_entities(storyline, self.screenplay)

        known_lower: Dict[str, Set[str]] = {
            "character": set(), "object": set(),
            "vehicle": set(), "environment": set(),
        }
        if self.screenplay:
            meta = getattr(self.screenplay, "identity_block_metadata", {}) or {}
            for m in meta.values():
                etype = (m.get("type") or "").lower()
                ename = (m.get("name") or "").strip()
                if etype in known_lower and ename:
                    known_lower[etype].add(ename.lower())

        type_icons = {
            "character": "\U0001F464",
            "object": "\U0001F4E6",
            "vehicle": "\U0001F697",
            "environment": "\U0001F30D",
        }
        _IDENTITY_BG = (
            "background-color:#1a3a5c; color:#9ecbff; border:1px solid #2a6cb5;"
            "border-radius:8px; padding:2px 7px; font-size:9px;"
        )
        _MARKUP_BG = (
            "background-color:#3a3a3a; color:#aaa; border:1px solid #555;"
            "border-radius:8px; padding:2px 7px; font-size:9px;"
        )

        entries: list = []
        for name in sorted(ent.characters):
            has_id = name.lower() in known_lower["character"]
            entries.append(("character", name, has_id))
        for name in sorted(ent.objects):
            has_id = name.lower() in known_lower["object"]
            entries.append(("object", name, has_id))
        for name in sorted(ent.vehicles):
            has_id = name.lower() in known_lower["vehicle"]
            entries.append(("vehicle", name, has_id))
        for name in sorted(ent.environments):
            has_id = name.lower() in known_lower["environment"]
            entries.append(("environment", name, has_id))

        if not entries:
            placeholder = QLabel("No entities detected")
            placeholder.setStyleSheet("color: #888; font-size: 9px; padding: 2px;")
            self._entity_tags_layout.addWidget(placeholder)
            return

        for etype, name, has_identity_block in entries:
            icon = type_icons.get(etype, "")
            display = name if len(name) <= 28 else name[:25] + "\u2026"
            tag = QLabel(f"{icon} {display}")
            tag.setStyleSheet(_IDENTITY_BG if has_identity_block else _MARKUP_BG)
            tip = f"{etype.title()}: {name}"
            if has_identity_block:
                tip += "\n\u2714 Identity block — reference image assignable"
            else:
                tip += "\nMarkup only — generator-handled"
            tag.setToolTip(tip)
            self._entity_tags_layout.addWidget(tag)

    def _update_validation(self):
        from core.video_prompt_builder import validate_for_generation
        valid, errors = validate_for_generation(self.item)
        if valid:
            self.validation_label.setText("Ready for generation.")
            self.validation_label.setStyleSheet(
                "font-size: 10px; padding: 3px; color: #00AA00; font-weight: bold;"
            )
        else:
            self.validation_label.setText("  ".join(errors))
            self.validation_label.setStyleSheet(
                "font-size: 10px; padding: 3px; color: #CC0000; font-weight: bold;"
            )

    # ================================================================
    #  Multi-Shot Cluster
    # ================================================================

    def _find_parent_scene(self):
        if not self.screenplay:
            return None
        for act in getattr(self.screenplay, "acts", []):
            for sc in act.scenes:
                if self.item.item_id in [si.item_id for si in sc.storyboard_items]:
                    return sc
        return None

    def _load_cluster_info(self):
        cluster_id = getattr(self.item, "cluster_id", None)
        if not cluster_id or not self.screenplay:
            self.cluster_group.setVisible(False)
            return

        cluster = None
        for act in getattr(self.screenplay, "acts", []):
            for sc in act.scenes:
                for cl in getattr(sc, "multishot_clusters", []):
                    if cl.cluster_id == cluster_id:
                        cluster = cl
                        break
                if cluster:
                    break
            if cluster:
                break

        if not cluster or len(cluster.item_ids) <= 1:
            self.cluster_group.setVisible(False)
            return

        shot_num = getattr(self.item, "shot_number_in_cluster", None) or "?"
        total = len(cluster.item_ids)
        self.cluster_id_label.setText(cluster_id)
        self.cluster_shot_label.setText(f"{shot_num} of {total}")
        self.cluster_duration_label.setText(f"{cluster.total_duration}s")

        if isinstance(shot_num, int) and shot_num <= len(cluster.transitions):
            t = cluster.transitions[shot_num - 1]
            self.cluster_transition_label.setText(
                f"{t.transition_type.replace('_', ' ').title()} -> Shot {t.to_shot}"
            )
        elif isinstance(shot_num, int) and shot_num == total:
            self.cluster_transition_label.setText("(final shot)")
        else:
            self.cluster_transition_label.setText("")

        self.cluster_group.setVisible(True)

    # ================================================================
    #  Save
    # ================================================================

    def save_item(self):
        """Validate and save the edited item."""
        try:
            if not self.item:
                QMessageBox.critical(self, "Save Error", "No item to save.")
                return

            self._sync_item_from_ui()

            if not self.item.prompt and not self.item.storyline:
                QMessageBox.warning(
                    self, "Missing Content",
                    "Please provide a storyline or generate a video prompt.",
                )
                return

            # Audio
            if hasattr(self.item, "audio_intent"):
                self.item.audio_intent = self.audio_intent_edit.toPlainText().strip()
            if hasattr(self.item, "audio_notes"):
                self.item.audio_notes = self.audio_notes_edit.toPlainText().strip()
            if hasattr(self.item, "audio_source"):
                val = self.audio_source_combo.currentData()
                self.item.audio_source = (
                    val if val in ("none", "generated", "post") else "none"
                )

            # Timestamp
            from datetime import datetime
            self.item.updated_at = datetime.now().isoformat()

            self.item_saved.emit(self.item)
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Save Error", f"An error occurred while saving:\n{str(e)}"
            )
            import traceback
            traceback.print_exc()

    # ================================================================
    #  Utility
    # ================================================================

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        geo = self.frameGeometry()
        geo.moveCenter(screen.center())
        self.move(geo.topLeft())
