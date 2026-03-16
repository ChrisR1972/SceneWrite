"""
Identity Block Manager Widget for SceneWrite.
Provides a UI for reviewing, editing, and approving entity identity blocks.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel,
    QPushButton, QGroupBox, QFormLayout, QMessageBox,
    QLineEdit, QProgressDialog, QScrollArea, QSizePolicy,
    QComboBox, QDialog, QApplication, QStyle, QDialogButtonBox,
    QCheckBox, QFileDialog, QMenu, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QPixmap
from .image_thumbnail import ClickableImageLabel
from typing import Optional, Dict, Any, List
from core.screenplay_engine import Screenplay
from core.ai_generator import AIGenerator


def _safe_print(*args, **kwargs):
    """Route output through debug_log instead of stdout (hidden in production)."""
    try:
        from debug_log import debug_log as _dl
        _dl(" ".join(str(a) for a in args))
    except Exception:
        pass


class IdentityBlockGenerationThread(QThread):
    """Thread for generating identity blocks from user notes."""
    
    finished = pyqtSignal(str)  # Generated identity block
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, ai_generator: AIGenerator, entity_name: str, entity_type: str, 
                 user_notes: str, scene_context: str, screenplay: Screenplay,
                 wizard_physical_appearance: str = "",
                 strip_clothing_emphasis: bool = False):
        super().__init__()
        self.ai_generator = ai_generator
        self.entity_name = entity_name
        self.entity_type = entity_type
        self.user_notes = user_notes
        self.scene_context = scene_context
        self.screenplay = screenplay
        self.wizard_physical_appearance = wizard_physical_appearance or ""
        self.strip_clothing_emphasis = strip_clothing_emphasis
    
    def run(self):
        """Generate identity block in background."""
        try:
            identity_block = self.ai_generator.generate_identity_block_from_notes(
                self.entity_name,
                self.entity_type,
                self.user_notes,
                self.scene_context,
                self.screenplay,
                wizard_physical_appearance=self.wizard_physical_appearance,
                strip_clothing_emphasis=self.strip_clothing_emphasis
            )
            self.finished.emit(identity_block)
        except Exception as e:
            self.error.emit(str(e))


class AddEntityDialog(QDialog):
    """Dialog for manually adding entities to the identity list."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Entity")
        self.setModal(True)
        self.setFixedSize(400, 200)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Entity name input
        form_layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter entity name (e.g., 'John Smith', 'Red Car', 'Library')")
        form_layout.addRow("Entity Name:", self.name_edit)
        
        # Entity type selection
        self.type_combo = QComboBox()
        self.type_combo.addItems(["character", "vehicle", "object", "environment"])
        self.type_combo.setCurrentText("character")
        form_layout.addRow("Entity Type:", self.type_combo)
        
        layout.addLayout(form_layout)
        
        # Help text
        help_text = QLabel("Manually add entities that weren't automatically detected from scenes. "
                          "You can then generate identity blocks and reference images for them.")
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; font-size: 10px; margin: 10px 0px;")
        layout.addWidget(help_text)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        add_btn = QPushButton("Add Entity")
        add_btn.clicked.connect(self.accept)
        add_btn.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(add_btn)
        
        layout.addLayout(button_layout)
    
    def get_entity_name(self) -> str:
        """Get the entered entity name."""
        return self.name_edit.text().strip()
    
    def get_entity_type(self) -> str:
        """Get the selected entity type."""
        return self.type_combo.currentText()


class IdentityBlockManager(QWidget):
    """Widget for managing identity blocks with user review and approval."""
    
    # Signals
    identity_block_updated = pyqtSignal(str)  # entity_id
    identity_blocks_changed = pyqtSignal()  # General change notification
    
    def _show_status(self, message: str, timeout: int = 3000):
        """Show a brief message on the main window's status bar (if available)."""
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, 'status_bar'):
                main_win.status_bar.showMessage(message, timeout)
        except Exception:
            pass

    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenplay: Optional[Screenplay] = None
        self.ai_generator: Optional[AIGenerator] = None
        self.current_entity_id: Optional[str] = None
        self.current_scene = None  # The currently selected scene in the framework view
        self.generation_thread: Optional[IdentityBlockGenerationThread] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create splitter for list and editor
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Entity list
        left_widget = self.create_entity_list()
        splitter.addWidget(left_widget)
        
        # Right side: Identity block editor
        right_widget = self.create_identity_editor()
        splitter.addWidget(right_widget)
        
        # Set splitter proportions (30% list, 70% editor)
        splitter.setStretchFactor(0, 30)
        splitter.setStretchFactor(1, 70)
        
        layout.addWidget(splitter)
    
    def create_entity_list(self) -> QWidget:
        """Create the entity list tree widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Entity List")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Scene filter row
        filter_row = QHBoxLayout()
        self.scene_filter_label = QLabel("Scene: (none selected)")
        self.scene_filter_label.setStyleSheet("color: #888; font-size: 10px;")
        filter_row.addWidget(self.scene_filter_label)
        filter_row.addStretch()
        self.show_all_checkbox = QCheckBox("Show All")
        self.show_all_checkbox.setToolTip("Show entities from all scenes, not just the selected scene")
        self.show_all_checkbox.setChecked(False)
        self.show_all_checkbox.toggled.connect(self._on_show_all_toggled)
        filter_row.addWidget(self.show_all_checkbox)
        layout.addLayout(filter_row)

        # Search/filter bar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search entities...")
        self.search_box.textChanged.connect(self.filter_entities)
        layout.addWidget(self.search_box)
        
        # Tree widget
        self.entity_tree = QTreeWidget()
        self.entity_tree.setHeaderLabels(["Entity", "Status"])
        self.entity_tree.setColumnWidth(0, 200)
        self.entity_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.entity_tree.itemSelectionChanged.connect(self.on_entity_selected)
        self.entity_tree.itemDoubleClicked.connect(self.on_entity_double_clicked)
        self.entity_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.entity_tree.customContextMenuRequested.connect(self._show_entity_context_menu)
        layout.addWidget(self.entity_tree)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        
        # Refresh button
        refresh_btn = QPushButton("Refresh List")
        refresh_btn.clicked.connect(self.refresh_entity_list)
        button_layout.addWidget(refresh_btn)
        
        # Add Entity button
        add_entity_btn = QPushButton("Add Entity")
        add_entity_btn.clicked.connect(self.add_manual_entity)
        button_layout.addWidget(add_entity_btn)
        
        # Remove Entity button (quick access from list)
        remove_entity_btn = QPushButton("Remove Entity")
        remove_entity_btn.clicked.connect(self.remove_selected_entity)
        button_layout.addWidget(remove_entity_btn)
        self.remove_entity_btn = remove_entity_btn
        
        # Select All button
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_entities)
        button_layout.addWidget(select_all_btn)
        self.select_all_btn = select_all_btn
        
        layout.addLayout(button_layout)
        
        return widget

    def remove_selected_entity(self):
        """Remove the currently selected entities from the identity list."""
        selected_items = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected_items or not self.screenplay:
            return

        if len(selected_items) > 1:
            self._delete_selected_entities()
        else:
            entity_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            self.load_entity(entity_id)
            self.delete_entity()
    
    def update_entity_status_in_tree(self, new_status: str):
        """Update the status of the current entity in the tree without full refresh."""
        if not self.current_entity_id:
            return
        
        # Find the current entity item in the tree
        for i in range(self.entity_tree.topLevelItemCount()):
            category_item = self.entity_tree.topLevelItem(i)
            for j in range(category_item.childCount()):
                entity_item = category_item.child(j)
                if entity_item.data(0, Qt.ItemDataRole.UserRole) == self.current_entity_id:
                    # Update the status column
                    entity_item.setText(1, new_status)
                    # Update the status label in the editor
                    self.entity_status_label.setText(new_status)
                    return
    
    def ensure_entity_selected(self):
        """Ensure the current entity remains selected and visible in the UI."""
        if not self.current_entity_id:
            return
        
        # Store current selection state
        was_blocked = self.entity_tree.signalsBlocked()
        
        # Block signals if not already blocked
        if not was_blocked:
            self.entity_tree.blockSignals(True)
        
        # Find and select the entity in the tree
        for i in range(self.entity_tree.topLevelItemCount()):
            category_item = self.entity_tree.topLevelItem(i)
            for j in range(category_item.childCount()):
                entity_item = category_item.child(j)
                if entity_item.data(0, Qt.ItemDataRole.UserRole) == self.current_entity_id:
                    # Ensure category is expanded
                    category_item.setExpanded(True)
                    
                    # Clear selection first, then select the specific item
                    self.entity_tree.clearSelection()
                    entity_item.setSelected(True)
                    self.entity_tree.setCurrentItem(entity_item)
                    
                    # Set focus back to tree to maintain selection
                    self.entity_tree.setFocus()
                    
                    # Ensure it's visible
                    self.entity_tree.scrollToItem(entity_item)
                    
                    # Force UI update
                    self.entity_tree.update()
                    self.entity_tree.repaint()
                    
                    # Process events to ensure UI updates
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    
                    _safe_print(f"Entity {self.current_entity_id} selection maintained")
                    
                    # Restore signal blocking state
                    if not was_blocked:
                        self.entity_tree.blockSignals(False)
                    return
        
        # Restore signal blocking state if entity not found
        if not was_blocked:
            self.entity_tree.blockSignals(False)
    
    def add_manual_entity(self):
        """Show dialog to manually add an entity."""
        dialog = AddEntityDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            entity_name = dialog.get_entity_name()
            entity_type = dialog.get_entity_type()
            
            if entity_name and entity_type:
                self.create_manual_entity(entity_name, entity_type)
    
    def create_manual_entity(self, entity_name: str, entity_type: str):
        """Create a new manual entity in the screenplay."""
        if not self.screenplay:
            QMessageBox.warning(self, "No Screenplay", "Please load a screenplay first.")
            return
        
        # Create a unique entity ID
        entity_id = f"manual_{entity_type}_{entity_name.lower().replace(' ', '_')}"
        
        # Check if entity already exists
        existing_metadata = self.screenplay.identity_block_metadata.get(entity_id)
        if existing_metadata:
            self._show_status(f"Entity '{entity_name}' already exists")
            return
        
        # Create new entity metadata
        import datetime
        now = datetime.datetime.now().isoformat()
        
        # For characters, user_notes stays empty (wardrobe is per-scene)
        if entity_type == "character":
            default_notes = ""
        else:
            default_notes = f"Manually added {entity_type}: {entity_name}"
        
        entity_metadata = {
            "name": entity_name,
            "type": entity_type,
            "scene_id": "manual",  # Indicate this is manually created
            "status": "placeholder",
            "user_notes": default_notes,
            "identity_block": "",
            "reference_image_prompt": "",
            "created_at": now,
            "updated_at": now
        }
        
        # Add to screenplay
        self.screenplay.identity_block_metadata[entity_id] = entity_metadata
        
        # Refresh the entity list to show the new entity
        self.refresh_entity_list()
        
        # Select the newly created entity
        self.select_entity_by_id(entity_id)
        
        self._show_status(f"'{entity_name}' added to identity list")
    
    def select_entity_by_id(self, entity_id: str):
        """Select an entity in the tree by its ID."""
        for i in range(self.entity_tree.topLevelItemCount()):
            category_item = self.entity_tree.topLevelItem(i)
            for j in range(category_item.childCount()):
                entity_item = category_item.child(j)
                if entity_item.data(0, Qt.ItemDataRole.UserRole) == entity_id:
                    self.entity_tree.setCurrentItem(entity_item)
                    category_item.setExpanded(True)
                    return
    
    def create_identity_editor(self) -> QWidget:
        """Create the identity block editor widget."""
        # Create scroll area as the main container
        scroll_area = QScrollArea()
        # Keep reference so we can reset scroll on selection
        self.editor_scroll_area = scroll_area
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Content widget inside scroll area
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Entity info group
        info_group = QGroupBox("Entity Information")
        info_layout = QFormLayout()
        
        self.entity_name_label = QLabel("(No entity selected)")
        self.entity_type_label = QLabel("")
        self.entity_scene_label = QLabel("")
        self.entity_status_label = QLabel("")
        
        info_layout.addRow("Name:", self.entity_name_label)
        info_layout.addRow("Type:", self.entity_type_label)
        info_layout.addRow("Scene:", self.entity_scene_label)
        info_layout.addRow("Status:", self.entity_status_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Environment extras group (only for type environment; show/hide in load_entity)
        self.env_extras_group = QGroupBox("Environment Extras (MODE A/B)")
        env_extras_layout = QFormLayout()
        self.extras_present_check = QCheckBox("Environment includes background extras (MODE B)")
        self.extras_present_check.setToolTip("If checked, reference images may include non-distinct background people (guests, crowd). If unchecked, no people (MODE A).")
        self.extras_present_check.stateChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("", self.extras_present_check)
        self.extras_density_combo = QComboBox()
        self.extras_density_combo.addItems(["sparse", "medium", "dense"])
        self.extras_density_combo.currentTextChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("Extras density:", self.extras_density_combo)
        self.extras_activities_edit = QLineEdit()
        self.extras_activities_edit.setPlaceholderText("e.g. seated guests, mingling crowd")
        self.extras_activities_edit.textChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("Extras activities:", self.extras_activities_edit)
        self.extras_depth_combo = QComboBox()
        self.extras_depth_combo.addItems(["background_only", "midground", "background_and_midground"])
        self.extras_depth_combo.currentTextChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("Extras depth:", self.extras_depth_combo)
        self.foreground_zone_combo = QComboBox()
        self.foreground_zone_combo.addItems(["clear", "partial", "none"])
        self.foreground_zone_combo.setToolTip("clear = no extras in foreground (default for hero placement)")
        self.foreground_zone_combo.currentTextChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("Foreground zone:", self.foreground_zone_combo)
        self.is_primary_env_check = QCheckBox("Primary Environment (first location in scene)")
        self.is_primary_env_check.setToolTip("If checked, this is the primary environment for the scene. Unchecked = secondary/transitional location.")
        self.is_primary_env_check.stateChanged.connect(self._on_extras_options_changed)
        env_extras_layout.addRow("", self.is_primary_env_check)
        self.env_extras_group.setLayout(env_extras_layout)
        self.env_extras_group.setVisible(False)
        layout.addWidget(self.env_extras_group)

        # Group controls (only for type group; show/hide in load_entity)
        self.group_controls_group = QGroupBox("Group Settings")
        group_ctrl_layout = QFormLayout()
        self.group_member_count_spin = QSpinBox()
        self.group_member_count_spin.setRange(2, 50)
        self.group_member_count_spin.setValue(3)
        self.group_member_count_spin.setToolTip("Total number of members in this group")
        self.group_member_count_spin.valueChanged.connect(self._on_group_options_changed)
        group_ctrl_layout.addRow("Member count:", self.group_member_count_spin)
        self.group_visible_count_spin = QSpinBox()
        self.group_visible_count_spin.setRange(0, 50)
        self.group_visible_count_spin.setValue(0)
        self.group_visible_count_spin.setToolTip("Visible on-screen at once (0 = same as member count)")
        self.group_visible_count_spin.valueChanged.connect(self._on_group_options_changed)
        group_ctrl_layout.addRow("Visible count:", self.group_visible_count_spin)
        self.group_formation_combo = QComboBox()
        self.group_formation_combo.addItems([
            "scattered", "line", "wedge", "cluster", "surrounding", "flanking"
        ])
        self.group_formation_combo.setToolTip("Default spatial arrangement of the group")
        self.group_formation_combo.currentTextChanged.connect(self._on_group_options_changed)
        group_ctrl_layout.addRow("Formation:", self.group_formation_combo)
        self.group_individuality_combo = QComboBox()
        self.group_individuality_combo.addItems(["identical", "slight_variation", "distinct"])
        self.group_individuality_combo.setToolTip(
            "identical = all members look the same; slight_variation = minor "
            "differences (height, build); distinct = each member visually unique"
        )
        self.group_individuality_combo.currentTextChanged.connect(self._on_group_options_changed)
        group_ctrl_layout.addRow("Individuality:", self.group_individuality_combo)
        self.group_uniform_edit = QLineEdit()
        self.group_uniform_edit.setPlaceholderText("e.g. polished silver breastplates with winged sun emblem")
        self.group_uniform_edit.textChanged.connect(self._on_group_options_changed)
        group_ctrl_layout.addRow("Uniform:", self.group_uniform_edit)
        self.group_controls_group.setLayout(group_ctrl_layout)
        self.group_controls_group.setVisible(False)
        layout.addWidget(self.group_controls_group)

        # Alias controls (link this entity as the same person as another)
        self.alias_controls_group = QGroupBox("Character Alias")
        alias_layout = QVBoxLayout()
        alias_help = QLabel(
            "Link entities that are the same person under different names "
            "(e.g. HOODED FIGURE → TALON → LYRA STORMWEAVER). "
            "Select the canonical (real) identity below."
        )
        alias_help.setWordWrap(True)
        alias_help.setStyleSheet("color: #666; font-style: italic;")
        alias_layout.addWidget(alias_help)
        alias_row = QHBoxLayout()
        self.alias_combo = QComboBox()
        self.alias_combo.setToolTip("Select the canonical identity this entity is an alias of")
        self.alias_combo.addItem("(none — this is the canonical identity)", "")
        alias_row.addWidget(self.alias_combo, stretch=1)
        self.alias_link_btn = QPushButton("Link")
        self.alias_link_btn.setToolTip("Set this entity as an alias of the selected canonical entity")
        self.alias_link_btn.clicked.connect(self._on_alias_link)
        alias_row.addWidget(self.alias_link_btn)
        self.alias_unlink_btn = QPushButton("Unlink")
        self.alias_unlink_btn.setToolTip("Remove the alias link")
        self.alias_unlink_btn.clicked.connect(self._on_alias_unlink)
        alias_row.addWidget(self.alias_unlink_btn)
        alias_layout.addLayout(alias_row)
        self.alias_status_label = QLabel("")
        self.alias_status_label.setWordWrap(True)
        alias_layout.addWidget(self.alias_status_label)
        self.alias_controls_group.setLayout(alias_layout)
        self.alias_controls_group.setVisible(False)
        layout.addWidget(self.alias_controls_group)

        # User notes group — label changes dynamically for characters vs other entities
        self.notes_group = QGroupBox("User Notes (Short Description)")
        notes_layout = QVBoxLayout()
        
        self.notes_help = QLabel("Provide a brief description of this entity. "
                           "The AI will expand this into a detailed identity block.")
        self.notes_help.setWordWrap(True)
        self.notes_help.setStyleSheet("color: #666; font-style: italic;")
        notes_layout.addWidget(self.notes_help)
        
        # Scene context label — shown for characters to indicate which scene wardrobe applies to
        self.wardrobe_scene_label = QLabel("")
        self.wardrobe_scene_label.setWordWrap(True)
        self.wardrobe_scene_label.setStyleSheet("color: #2196F3; font-weight: bold; margin: 2px 0;")
        self.wardrobe_scene_label.setVisible(False)
        notes_layout.addWidget(self.wardrobe_scene_label)
        
        self.user_notes_edit = QTextEdit()
        self.user_notes_edit.setTabChangesFocus(True)
        self.user_notes_edit.setPlaceholderText(
            "Example for character: 'Male captain, 40s, worn military uniform, weathered face'\n"
            "Example for vehicle: 'Large starship, angular hull, battle-scarred, grey metallic'\n"
            "Example for object: 'Ancient alien artifact, glowing blue crystal, ornate metallic frame'\n"
            "Example for environment: 'Desolate wasteland, dusk lighting, abandoned structures'"
        )
        self.user_notes_edit.setMinimumHeight(100)
        self.user_notes_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.user_notes_edit.textChanged.connect(self.on_notes_changed)
        notes_layout.addWidget(self.user_notes_edit)
        
        # Generate button
        generate_btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Identity Block")
        self.generate_btn.clicked.connect(self.generate_identity_block)
        self.generate_btn.setEnabled(False)
        generate_btn_layout.addStretch()
        generate_btn_layout.addWidget(self.generate_btn)
        notes_layout.addLayout(generate_btn_layout)
        
        self.notes_group.setLayout(notes_layout)
        layout.addWidget(self.notes_group)
        
        # Redirect label for characters (hidden by default)
        self.char_redirect_label = QLabel(
            "Character identity blocks are generated in the Character Details tab.\n"
            "Use the Character Details tab to generate and approve identity blocks for characters."
        )
        self.char_redirect_label.setWordWrap(True)
        self.char_redirect_label.setStyleSheet(
            "color: #2196F3; font-style: italic; font-size: 11px; "
            "padding: 12px; border: 1px dashed #2196F3; border-radius: 4px; margin: 4px 0;"
        )
        self.char_redirect_label.setVisible(False)
        layout.addWidget(self.char_redirect_label)

        # Generated identity block group
        self.block_group = QGroupBox("Generated Identity Block")
        block_layout = QVBoxLayout()
        
        block_help = QLabel("Review and edit the generated identity block. "
                           "Once satisfied, click 'Approve'.")
        block_help.setWordWrap(True)
        block_help.setStyleSheet("color: #666; font-style: italic;")
        block_layout.addWidget(block_help)
        
        self.identity_block_edit = QTextEdit()
        self.identity_block_edit.setTabChangesFocus(True)
        self.identity_block_edit.setPlaceholderText(
            "Generated identity block will appear here...\n\n"
            "You can edit it before approving."
        )
        self.identity_block_edit.setMinimumHeight(200)
        self.identity_block_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.identity_block_edit.textChanged.connect(self.on_block_changed)
        block_layout.addWidget(self.identity_block_edit)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        self.approve_btn = QPushButton("Approve")
        self.approve_btn.clicked.connect(self.approve_identity_block)
        self.approve_btn.setEnabled(False)
        self.approve_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        
        self.delete_btn = QPushButton("Delete Entity")
        self.delete_btn.clicked.connect(self.delete_entity)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        
        button_layout.addStretch()
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.approve_btn)
        
        block_layout.addLayout(button_layout)
        self.block_group.setLayout(block_layout)
        layout.addWidget(self.block_group)
        
        # Reference Image Prompt group (for Higgsfield reference images)
        self.ref_image_group = QGroupBox("Reference Image Prompt (for Higgsfield)")
        ref_image_layout = QVBoxLayout()
        
        ref_help = QLabel("Generate a prompt for creating a standalone reference image in Higgsfield. "
                         "Only available for approved identity blocks. Copy this prompt to Higgsfield to create the reference image.")
        ref_help.setWordWrap(True)
        ref_help.setStyleSheet("color: #666; font-style: italic;")
        ref_image_layout.addWidget(ref_help)
        
        self.ref_image_prompt_edit = QTextEdit()
        self.ref_image_prompt_edit.setPlaceholderText(
            "Reference image prompt will appear here after approval or generation...\n\n"
            "Editable; use Save to persist changes."
        )
        self.ref_image_prompt_edit.setMinimumHeight(150)
        self.ref_image_prompt_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.ref_image_prompt_edit.setReadOnly(False)  # Editable; user can save edits
        self.ref_image_prompt_edit.setTabChangesFocus(True)
        ref_image_layout.addWidget(self.ref_image_prompt_edit)
        
        # Reference image prompt buttons
        ref_btn_layout = QHBoxLayout()
        
        self.generate_ref_prompt_btn = QPushButton("Generate Reference Image Prompt")
        self.generate_ref_prompt_btn.clicked.connect(self.generate_reference_image_prompt)
        self.generate_ref_prompt_btn.setEnabled(False)
        self.generate_ref_prompt_btn.setStyleSheet("background-color: #2196F3; color: white;")
        
        self.copy_ref_prompt_btn = QPushButton("Copy to Clipboard")
        self.copy_ref_prompt_btn.clicked.connect(self.copy_reference_prompt_to_clipboard)
        self.copy_ref_prompt_btn.setEnabled(False)
        
        ref_btn_layout.addStretch()
        ref_btn_layout.addWidget(self.generate_ref_prompt_btn)
        ref_btn_layout.addWidget(self.copy_ref_prompt_btn)
        
        ref_image_layout.addLayout(ref_btn_layout)
        self.ref_image_group.setLayout(ref_image_layout)
        layout.addWidget(self.ref_image_group)

        # Reference Image thumbnail group
        self.ref_thumb_group = QGroupBox("Reference Image")
        ref_thumb_layout = QHBoxLayout()

        self.ref_thumb_label = ClickableImageLabel(max_short=120, max_long=160)
        ref_thumb_layout.addWidget(self.ref_thumb_label)

        thumb_btn_col = QVBoxLayout()
        self.upload_ref_image_btn = QPushButton("Upload Image")
        self.upload_ref_image_btn.setFixedWidth(120)
        self.upload_ref_image_btn.clicked.connect(self._upload_reference_image)
        thumb_btn_col.addWidget(self.upload_ref_image_btn)

        self.clear_ref_image_btn = QPushButton("Clear")
        self.clear_ref_image_btn.setFixedWidth(120)
        self.clear_ref_image_btn.clicked.connect(self._clear_reference_image)
        thumb_btn_col.addWidget(self.clear_ref_image_btn)
        thumb_btn_col.addStretch()
        ref_thumb_layout.addLayout(thumb_btn_col)
        ref_thumb_layout.addStretch()

        self.ref_thumb_group.setLayout(ref_thumb_layout)
        layout.addWidget(self.ref_thumb_group)
        
        layout.addStretch()
        
        # Set content widget in scroll area
        scroll_area.setWidget(content_widget)
        
        return scroll_area
    
    def set_screenplay(self, screenplay: Screenplay):
        """Set the screenplay to manage."""
        self.screenplay = screenplay
        self.refresh_entity_list()
    
    def set_ai_generator(self, ai_generator: AIGenerator):
        """Set the AI generator for identity block generation."""
        self.ai_generator = ai_generator
    
    def set_current_scene(self, scene):
        """Set the currently active scene and refresh the entity list.

        Args:
            scene: A StoryScene instance or None.
        """
        prev_scene = self.current_scene
        self.current_scene = scene

        # Update the scene label
        if scene and hasattr(scene, "title"):
            self.scene_filter_label.setText(f"Scene: {scene.title}")
        else:
            self.scene_filter_label.setText("Scene: (none selected)")

        # Refresh entity list when the scene changes (unless "Show All" hides the effect)
        if scene != prev_scene:
            self.refresh_entity_list()

        # If a character entity is currently loaded, refresh to show wardrobe for the new scene
        if self.current_entity_id and self.screenplay:
            metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
            if metadata and (metadata.get("type") or "").lower() == "character":
                self._load_character_wardrobe(self.current_entity_id)

    def _on_show_all_toggled(self, checked: bool):
        """Toggle between scene-filtered and global entity views."""
        self.refresh_entity_list()

    def _show_entity_context_menu(self, position):
        """Show right-click context menu for the entity tree."""
        menu = QMenu(self)

        selected_items = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        single = len(selected_items) == 1
        any_selected = len(selected_items) > 0

        # Gather metadata for all selected items
        selected_metas = []
        for item in selected_items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = (self.screenplay.get_identity_block_metadata_by_id(eid)
                    if self.screenplay else None) or {}
            selected_metas.append((eid, meta))

        # Determine types in selection
        selected_types = {(m.get("type") or "").lower() for _, m in selected_metas}
        all_obj_or_vehicle = selected_types <= {"object", "vehicle"} and len(selected_metas) > 0

        if single:
            entity_id, meta = selected_metas[0]
            status = meta.get("status", "")
            has_block = bool(meta.get("identity_block"))
            has_ref_prompt = bool(meta.get("reference_image_prompt"))
            is_approved = status == "approved"

            gen_action = menu.addAction("Generate Identity Block")
            gen_action.setEnabled(bool(self.ai_generator))
            gen_action.triggered.connect(self.generate_identity_block)

            approve_action = menu.addAction("Approve Identity Block")
            approve_action.setEnabled(has_block)
            approve_action.triggered.connect(self.approve_identity_block)

            menu.addSeparator()

            gen_ref_action = menu.addAction("Generate Reference Image Prompt")
            gen_ref_action.setEnabled(is_approved and has_block and bool(self.ai_generator))
            gen_ref_action.triggered.connect(self.generate_reference_image_prompt)

            copy_ref_action = menu.addAction("Copy Reference Prompt to Clipboard")
            copy_ref_action.setEnabled(has_ref_prompt)
            copy_ref_action.triggered.connect(self.copy_reference_prompt_to_clipboard)

            entity_type = (meta.get("type") or "").lower()
            if entity_type in ("object", "vehicle"):
                menu.addSeparator()
                is_passive = status == "passive"
                if is_passive:
                    unpassive_action = menu.addAction("Remove Passive Label")
                    unpassive_action.triggered.connect(self._unmark_passive_entity)
                else:
                    passive_action = menu.addAction("Mark as Passive (Name Only)")
                    passive_action.triggered.connect(self._mark_passive_entity)

            menu.addSeparator()

        elif any_selected and all_obj_or_vehicle:
            n = len(selected_items)

            gen_action = menu.addAction(f"Generate Identity Blocks ({n})")
            gen_action.setEnabled(bool(self.ai_generator))
            gen_action.triggered.connect(self._generate_selected_identity_blocks)

            any_has_block = any(bool(m.get("identity_block")) for _, m in selected_metas)
            approve_action = menu.addAction(f"Approve Identity Blocks ({n})")
            approve_action.setEnabled(any_has_block)
            approve_action.triggered.connect(self._approve_selected_identity_blocks)

            menu.addSeparator()

            any_approved = any(
                m.get("status") == "approved" and bool(m.get("identity_block"))
                for _, m in selected_metas
            )
            gen_ref_action = menu.addAction(f"Generate Reference Image Prompts ({n})")
            gen_ref_action.setEnabled(any_approved and bool(self.ai_generator))
            gen_ref_action.triggered.connect(self._generate_selected_reference_prompts)

            menu.addSeparator()

            passive_count = sum(1 for _, m in selected_metas if m.get("status") == "passive")
            non_passive_count = n - passive_count
            if non_passive_count > 0:
                passive_action = menu.addAction(
                    f"Mark as Passive ({non_passive_count})"
                    if non_passive_count < n else f"Mark as Passive ({n})"
                )
                passive_action.triggered.connect(self._mark_passive_entity)
            if passive_count > 0:
                unpassive_action = menu.addAction(
                    f"Remove Passive Label ({passive_count})"
                    if passive_count < n else f"Remove Passive Label ({n})"
                )
                unpassive_action.triggered.connect(self._unmark_passive_entity)

            menu.addSeparator()

        if any_selected:
            delete_action = menu.addAction("Delete Entity" if single else f"Delete {len(selected_items)} Entities")
            delete_action.triggered.connect(
                self.delete_entity if single else self._delete_selected_entities
            )
            menu.addSeparator()

        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.select_all_entities)

        add_action = menu.addAction("Add Entity...")
        add_action.triggered.connect(self.add_manual_entity)

        refresh_action = menu.addAction("Refresh List")
        refresh_action.triggered.connect(self.refresh_entity_list)

        menu.exec(self.entity_tree.viewport().mapToGlobal(position))

    def _delete_selected_entities(self):
        """Delete all currently selected entities after confirmation."""
        if not self.screenplay:
            return
        selected_items = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected_items:
            return

        names = []
        for item in selected_items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.identity_block_metadata.get(eid, {})
            names.append(meta.get("name", eid))

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {len(names)} entities?\n\n"
            + "\n".join(f"  • {n}" for n in names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for item in selected_items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.identity_block_metadata.get(eid, {})
            entity_key = f"{meta.get('type', '')}:{meta.get('name', '')}".lower()
            self.screenplay.identity_block_metadata.pop(eid, None)
            self.screenplay.identity_blocks.pop(eid, None)
            self.screenplay.identity_block_ids.pop(entity_key, None)

        self.identity_blocks_changed.emit()
        self.clear_editor()
        self.refresh_entity_list()
        self._show_status(f"{len(names)} entities deleted")

    def refresh_entity_list(self):
        """Refresh the entity list from screenplay, filtered by the current scene."""
        self.entity_tree.clear()
        
        if not self.screenplay:
            return

        # Build dict of recurring object names → warning text for visual indicator
        self._recurring_object_info: dict = {}
        try:
            _warnings = self.screenplay.detect_recurring_objects_needing_identity()
            for w in _warnings:
                import re as _re
                m = _re.search(r'\[([^\]]+)\] appears in', w)
                if m:
                    self._recurring_object_info[m.group(1).lower()] = w
        except Exception:
            pass

        # Determine which entity IDs to show
        show_all = self.show_all_checkbox.isChecked()
        scene_entity_ids: Optional[set] = None
        if not show_all and self.current_scene is not None:
            scene_entity_ids = self.screenplay.get_entity_ids_for_scene(self.current_scene)
        
        # Group entities by type
        environments = []
        characters = []
        groups = []
        vehicles = []
        objects = []
        
        for entity_id, metadata in self.screenplay.identity_block_metadata.items():
            if scene_entity_ids is not None and entity_id not in scene_entity_ids:
                continue

            entity_type = metadata.get("type", "")
            entity_data = metadata.copy()
            entity_data["entity_id"] = entity_id
            
            if entity_type == "environment":
                environments.append(entity_data)
            elif entity_type == "character":
                characters.append(entity_data)
            elif entity_type == "group":
                groups.append(entity_data)
            elif entity_type == "vehicle":
                vehicles.append(entity_data)
            elif entity_type == "object":
                objects.append(entity_data)
        
        # Create tree structure
        if environments:
            env_parent = QTreeWidgetItem(self.entity_tree, ["Environments", ""])
            env_parent.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            for entity in environments:
                self._add_entity_item(env_parent, entity)
            env_parent.setExpanded(True)
        
        if characters:
            char_parent = QTreeWidgetItem(self.entity_tree, ["Characters", ""])
            char_parent.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            for entity in characters:
                self._add_entity_item(char_parent, entity)
            char_parent.setExpanded(True)

        if groups:
            group_parent = QTreeWidgetItem(self.entity_tree, ["Groups", ""])
            group_parent.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            for entity in groups:
                self._add_entity_item(group_parent, entity)
            group_parent.setExpanded(True)
        
        if vehicles:
            veh_parent = QTreeWidgetItem(self.entity_tree, ["Vehicles", ""])
            veh_parent.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            for entity in vehicles:
                self._add_entity_item(veh_parent, entity)
            veh_parent.setExpanded(True)
        
        if objects:
            obj_parent = QTreeWidgetItem(self.entity_tree, ["Objects", ""])
            obj_parent.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))
            for entity in objects:
                self._add_entity_item(obj_parent, entity)
            obj_parent.setExpanded(True)
    
    def _add_entity_item(self, parent: QTreeWidgetItem, entity: Dict[str, Any]):
        """Add an entity item to the tree."""
        name = entity.get("name", "Unknown")
        status = entity.get("status", "unknown")
        entity_id = entity.get("entity_id", "")
        entity_type = (entity.get("type") or "").lower()
        linked_group_id = entity.get("linked_group_id", "") or ""

        # Recurring object indicator
        _recurring_info = getattr(self, "_recurring_object_info", {})
        is_recurring = entity_type == "object" and name.lower() in _recurring_info
        display_name = f"🔄 {name}" if is_recurring else name
        
        # Format status
        status_text = status.capitalize()
        if status == "placeholder":
            status_text = "⚠ Pending"
        elif status == "approved":
            status_text = "✓ Approved"
        elif status == "generating":
            status_text = "⏳ Generating"
        elif status == "passive":
            status_text = "◇ Passive"
        elif status == "referenced":
            status_text = "👁 Referenced"
        if linked_group_id:
            status_text = f"{status_text} 🔗 Linked"
        if is_recurring:
            status_text = f"{status_text} 🔄 Recurring"
        
        item = QTreeWidgetItem(parent, [display_name, status_text])
        item.setData(0, Qt.ItemDataRole.UserRole, entity_id)

        if is_recurring:
            item.setToolTip(0, _recurring_info.get(name.lower(), ""))
            item.setToolTip(1, "This object appears in multiple scenes — generate an identity block for visual continuity")
        
        # Tick icon for completed (approved) entities
        if status == "approved":
            try:
                item.setIcon(0, QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                # Fallback: prefix name with tick if icon fails
                item.setText(0, f"✓ {name}")
        
        # Color code by status
        if status == "placeholder":
            item.setForeground(1, QColor("#ff9800"))  # Orange
        elif status == "approved":
            item.setForeground(1, QColor("#4CAF50"))  # Green
        elif status == "generating":
            item.setForeground(1, QColor("#2196F3"))  # Blue
        elif status == "passive":
            item.setForeground(0, QColor("#9E9E9E"))  # Grey name
            item.setForeground(1, QColor("#9E9E9E"))  # Grey status
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)
        elif status == "referenced":
            item.setForeground(0, QColor("#78909C"))  # Blue-grey name
            item.setForeground(1, QColor("#78909C"))  # Blue-grey status
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)
            item.setToolTip(0, "This environment is referenced but not visited in this scene")
            item.setToolTip(1, "Mentioned in dialogue, visions, or lore — not a scene location")
    
    def filter_entities(self, text: str):
        """Filter entities by search text."""
        # Simple filtering - hide items that don't match
        search_text = text.lower()
        
        for i in range(self.entity_tree.topLevelItemCount()):
            parent = self.entity_tree.topLevelItem(i)
            visible_children = 0
            
            for j in range(parent.childCount()):
                child = parent.child(j)
                name = child.text(0).lower()
                
                if search_text in name or not search_text:
                    child.setHidden(False)
                    visible_children += 1
                else:
                    child.setHidden(True)
            
            # Hide parent if no visible children
            parent.setHidden(visible_children == 0 and search_text)
    
    def on_entity_selected(self):
        """Handle entity selection from tree."""
        selected_items = self.entity_tree.selectedItems()
        if not selected_items:
            self.clear_editor()
            return

        # Load the most recently selected entity (last in list) into the editor
        for item in reversed(selected_items):
            entity_id = item.data(0, Qt.ItemDataRole.UserRole)
            if entity_id and self.screenplay:
                self.load_entity(entity_id)
                return

        self.clear_editor()
    
    def on_entity_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on entity."""
        # Focus on user notes edit
        self.user_notes_edit.setFocus()
    
    def load_entity(self, entity_id: str):
        """Load entity data into the editor."""
        if not self.screenplay:
            return
        
        metadata = self.screenplay.get_identity_block_metadata_by_id(entity_id)
        if not metadata:
            return
        
        self.current_entity_id = entity_id
        
        # Update entity info
        self.entity_name_label.setText(metadata.get("name", ""))
        entity_type = (metadata.get("type") or "").lower()
        self.entity_type_label.setText(entity_type.capitalize())
        
        # Get scene info if environment
        scene_id = metadata.get("scene_id", "")
        if scene_id:
            scene = self.screenplay.get_scene(scene_id)
            if scene:
                self.entity_scene_label.setText(f"{scene.title} (Scene {scene.scene_number})")
            else:
                self.entity_scene_label.setText(scene_id)
        else:
            self.entity_scene_label.setText("Global")
        
        status = metadata.get("status", "")
        status_text = status.capitalize()
        if metadata.get("source") == "series_bible":
            status_text += "  [Series Bible]"
        self.entity_status_label.setText(status_text)
        
        # ---------- CHARACTER: show wardrobe only, redirect to Character Details ----------
        if entity_type == "character":
            self.notes_group.setTitle("Scene Wardrobe (Clothing & Accessories)")
            self.notes_help.setText(
                "Short wardrobe description for this character in the current scene."
            )
            self.user_notes_edit.setPlaceholderText(
                "No wardrobe specified for this scene."
            )
            if self.current_scene:
                scene_title = getattr(self.current_scene, "title", "") or ""
                scene_num = getattr(self.current_scene, "scene_number", "") or ""
                self.wardrobe_scene_label.setText(
                    f"Wardrobe for: {scene_title} (Scene {scene_num})"
                )
                self.wardrobe_scene_label.setVisible(True)
            else:
                self.wardrobe_scene_label.setText("No scene selected — select a scene to edit wardrobe.")
                self.wardrobe_scene_label.setVisible(True)

            self._load_character_wardrobe(entity_id)

            self.user_notes_edit.setReadOnly(True)
            pal = self.user_notes_edit.palette()
            pal.setBrush(pal.ColorRole.Base, pal.brush(pal.ColorRole.Window))
            self.user_notes_edit.setPalette(pal)
            self.user_notes_edit.setMinimumHeight(0)
            self.user_notes_edit.setMaximumHeight(16777215)
            self._fit_notes_to_content()

            self.generate_btn.setVisible(False)
            self.block_group.setVisible(False)
            self.ref_image_group.setVisible(False)
            self.char_redirect_label.setVisible(True)
        
        # ---------- NON-CHARACTER: unchanged behaviour ----------
        else:
            self.notes_group.setTitle("User Notes (Short Description)")
            self.notes_help.setText(
                "Provide a brief description of this entity. "
                "The AI will expand this into a detailed identity block."
            )
            # Set type-specific placeholder
            if entity_type == "environment":
                self.user_notes_edit.setPlaceholderText(
                    "Examples:\n"
                    "  'Dimly lit Victorian library, tall oak bookshelves, dust motes in candlelight'\n"
                    "  'Rain-soaked city alley at night, neon reflections on wet cobblestones, steam from grates'\n"
                    "  'Sunlit meadow at dawn, wildflowers, distant mountains, morning mist'"
                )
            elif entity_type == "vehicle":
                self.user_notes_edit.setPlaceholderText(
                    "Examples:\n"
                    "  'Large starship, angular hull, battle-scarred, grey metallic'\n"
                    "  'Vintage red convertible, chrome bumpers, white-wall tires, dusty'"
                )
            elif entity_type == "object":
                self.user_notes_edit.setPlaceholderText(
                    "Examples:\n"
                    "  'Ancient alien artifact, glowing blue crystal, ornate metallic frame'\n"
                    "  'Weathered leather-bound journal, brass clasp, yellowed pages'"
                )
            elif entity_type == "group":
                self.user_notes_edit.setPlaceholderText(
                    "Examples:\n"
                    "  'Elite imperial soldiers in polished silver armor with winged sun emblems'\n"
                    "  'Ragged rebel fighters in mismatched gear, bandanas and improvised weapons'"
                )
            else:
                self.user_notes_edit.setPlaceholderText(
                    "Provide a brief description of this entity."
                )
            self.wardrobe_scene_label.setVisible(False)
            
            # Load user_notes from identity block metadata (original behavior)
            user_notes = metadata.get("user_notes", "") or ""
            self.user_notes_edit.blockSignals(True)
            self.user_notes_edit.setPlainText(user_notes)
            self.user_notes_edit.blockSignals(False)

            self.user_notes_edit.setReadOnly(False)
            self.user_notes_edit.setPalette(self.palette())
            self.user_notes_edit.setMinimumHeight(100)
            self.user_notes_edit.setMaximumHeight(16777215)

            self.generate_btn.setVisible(True)
            self.block_group.setVisible(True)
            self.ref_image_group.setVisible(True)
            self.char_redirect_label.setVisible(False)
        
        # Load identity block
        self.identity_block_edit.blockSignals(True)
        self.identity_block_edit.setPlainText(metadata.get("identity_block", ""))
        self.identity_block_edit.blockSignals(False)
        
        # Load reference image prompt (if exists)
        self.ref_image_prompt_edit.blockSignals(True)
        self.ref_image_prompt_edit.setPlainText(metadata.get("reference_image_prompt", ""))
        self.ref_image_prompt_edit.blockSignals(False)

        # Load reference image thumbnail
        img_path = (metadata.get("image_path") or "").strip()
        if img_path:
            self.ref_thumb_label.setImageFromPath(img_path)
        else:
            self.ref_thumb_label.clearImage()
        
        # Environment extras (only for type environment)
        if metadata.get("type") == "environment":
            self.env_extras_group.setVisible(True)
            self.extras_present_check.blockSignals(True)
            self.extras_present_check.setChecked(bool(metadata.get("extras_present", False)))
            self.extras_present_check.blockSignals(False)
            self.extras_density_combo.blockSignals(True)
            density = metadata.get("extras_density", "sparse")
            idx = self.extras_density_combo.findText(density)
            if idx >= 0:
                self.extras_density_combo.setCurrentIndex(idx)
            self.extras_density_combo.blockSignals(False)
            self.extras_activities_edit.blockSignals(True)
            self.extras_activities_edit.setText(metadata.get("extras_activities", "") or "")
            self.extras_activities_edit.blockSignals(False)
            self.extras_depth_combo.blockSignals(True)
            depth = metadata.get("extras_depth", "background_only")
            idx = self.extras_depth_combo.findText(depth)
            if idx >= 0:
                self.extras_depth_combo.setCurrentIndex(idx)
            self.extras_depth_combo.blockSignals(False)
            self.foreground_zone_combo.blockSignals(True)
            fg = metadata.get("foreground_zone", "clear")
            idx_fg = self.foreground_zone_combo.findText(fg)
            if idx_fg >= 0:
                self.foreground_zone_combo.setCurrentIndex(idx_fg)
            self.foreground_zone_combo.blockSignals(False)
            self.is_primary_env_check.blockSignals(True)
            self.is_primary_env_check.setChecked(bool(metadata.get("is_primary_environment", True)))
            self.is_primary_env_check.blockSignals(False)
        else:
            self.env_extras_group.setVisible(False)

        # Group controls (only for type group)
        if metadata.get("type") == "group":
            self.group_controls_group.setVisible(True)
            self.group_member_count_spin.blockSignals(True)
            self.group_member_count_spin.setValue(int(metadata.get("member_count", 3)))
            self.group_member_count_spin.blockSignals(False)
            self.group_visible_count_spin.blockSignals(True)
            self.group_visible_count_spin.setValue(int(metadata.get("member_count_visible", 0)))
            self.group_visible_count_spin.blockSignals(False)
            self.group_formation_combo.blockSignals(True)
            formation = metadata.get("formation", "scattered")
            idx_f = self.group_formation_combo.findText(formation)
            if idx_f >= 0:
                self.group_formation_combo.setCurrentIndex(idx_f)
            self.group_formation_combo.blockSignals(False)
            self.group_individuality_combo.blockSignals(True)
            individuality = metadata.get("individuality", "identical")
            idx_i = self.group_individuality_combo.findText(individuality)
            if idx_i >= 0:
                self.group_individuality_combo.setCurrentIndex(idx_i)
            self.group_individuality_combo.blockSignals(False)
            self.group_uniform_edit.blockSignals(True)
            self.group_uniform_edit.setText(metadata.get("uniform_description", "") or "")
            self.group_uniform_edit.blockSignals(False)
        else:
            self.group_controls_group.setVisible(False)

        # Alias controls (character/group entities)
        etype = (metadata.get("type") or "").lower()
        if etype in ("character", "group"):
            self.alias_controls_group.setVisible(True)
            self._populate_alias_combo(entity_id, metadata)
        else:
            self.alias_controls_group.setVisible(False)

        # Update button states
        self.update_button_states()

        # Reset editor scroll to top when changing selection
        try:
            if hasattr(self, "editor_scroll_area") and self.editor_scroll_area:
                self.editor_scroll_area.verticalScrollBar().setValue(0)
        except Exception:
            pass
    
    def clear_editor(self):
        """Clear the editor fields."""
        self.current_entity_id = None
        self.entity_name_label.setText("(No entity selected)")
        self.entity_type_label.setText("")
        self.entity_scene_label.setText("")
        self.entity_status_label.setText("")
        self.user_notes_edit.clear()
        self.identity_block_edit.clear()
        self.ref_image_prompt_edit.clear()
        self.ref_thumb_label.clearImage()
        self.env_extras_group.setVisible(False)
        # Reset character-specific UI elements
        self.notes_group.setTitle("User Notes (Short Description)")
        self.notes_help.setText(
            "Provide a brief description of this entity. "
            "The AI will expand this into a detailed identity block."
        )
        self.wardrobe_scene_label.setVisible(False)
        self.user_notes_edit.setReadOnly(False)
        self.user_notes_edit.setPalette(self.palette())
        self.user_notes_edit.setMinimumHeight(100)
        self.user_notes_edit.setMaximumHeight(16777215)
        self.generate_btn.setVisible(True)
        self.block_group.setVisible(True)
        self.ref_image_group.setVisible(True)
        self.char_redirect_label.setVisible(False)
        self.update_button_states()

    def _upload_reference_image(self):
        """Upload a reference image for the current entity."""
        if not self.current_entity_id or not self.screenplay:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id, image_path=path)
        self.ref_thumb_label.setImageFromPath(path)
        self._show_status("Reference image uploaded.")

    def _clear_reference_image(self):
        """Clear the reference image for the current entity."""
        if not self.current_entity_id or not self.screenplay:
            return
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id, image_path="")
        self.ref_thumb_label.clearImage()
        self._show_status("Reference image cleared.")
    
    def _on_extras_options_changed(self):
        """Persist environment extras options to metadata."""
        if not self.current_entity_id or not self.screenplay:
            return
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        if not metadata or metadata.get("type") != "environment":
            return
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id,
            extras_present=self.extras_present_check.isChecked(),
            extras_density=self.extras_density_combo.currentText(),
            extras_activities=self.extras_activities_edit.text().strip(),
            extras_depth=self.extras_depth_combo.currentText(),
            foreground_zone=self.foreground_zone_combo.currentText(),
            is_primary_environment=self.is_primary_env_check.isChecked()
        )

    def _on_group_options_changed(self):
        """Persist group settings to metadata."""
        if not self.current_entity_id or not self.screenplay:
            return
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        if not metadata or metadata.get("type") != "group":
            return
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id,
            member_count=self.group_member_count_spin.value(),
            member_count_visible=self.group_visible_count_spin.value(),
            formation=self.group_formation_combo.currentText(),
            individuality=self.group_individuality_combo.currentText(),
            uniform_description=self.group_uniform_edit.text().strip(),
        )

    # ── Alias system UI methods ────────────────────────────────────

    def _populate_alias_combo(self, entity_id: str, metadata: dict):
        """Populate the alias combo box with eligible canonical entities."""
        self.alias_combo.blockSignals(True)
        self.alias_combo.clear()
        self.alias_combo.addItem("(none — this is the canonical identity)", "")

        current_alias_of = metadata.get("alias_of", "")
        selected_idx = 0

        if self.screenplay:
            for eid, m in self.screenplay.identity_block_metadata.items():
                if eid == entity_id:
                    continue
                etype = (m.get("type") or "").lower()
                if etype not in ("character", "group"):
                    continue
                ename = m.get("name", eid)
                self.alias_combo.addItem(f"{ename} ({eid[:8]}…)", eid)
                if eid == current_alias_of:
                    selected_idx = self.alias_combo.count() - 1

        self.alias_combo.setCurrentIndex(selected_idx)
        self.alias_combo.blockSignals(False)

        # Update status label
        if current_alias_of and self.screenplay:
            canon_meta = self.screenplay.identity_block_metadata.get(current_alias_of, {})
            canon_name = canon_meta.get("name", current_alias_of)
            self.alias_status_label.setText(
                f"✓ Linked as alias of {canon_name}"
            )
            self.alias_status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        else:
            aliases = metadata.get("aliases") or []
            if aliases and self.screenplay:
                alias_names = []
                for aid in aliases:
                    am = self.screenplay.identity_block_metadata.get(aid, {})
                    alias_names.append(am.get("name", aid))
                self.alias_status_label.setText(
                    f"Canonical identity — aliases: {', '.join(alias_names)}"
                )
                self.alias_status_label.setStyleSheet("color: #1565c0; font-weight: bold;")
            else:
                self.alias_status_label.setText("")
                self.alias_status_label.setStyleSheet("")

    def _on_alias_link(self):
        """Link current entity as an alias of the selected canonical entity."""
        if not self.current_entity_id or not self.screenplay:
            return
        canonical_id = self.alias_combo.currentData()
        if not canonical_id:
            QMessageBox.information(
                self, "No Target",
                "Select a canonical entity from the dropdown first."
            )
            return
        canon_meta = self.screenplay.identity_block_metadata.get(canonical_id, {})
        canon_name = canon_meta.get("name", canonical_id)
        cur_meta = self.screenplay.identity_block_metadata.get(self.current_entity_id, {})
        cur_name = cur_meta.get("name", self.current_entity_id)

        ok = self.screenplay.link_entity_alias(self.current_entity_id, canonical_id)
        if ok:
            QMessageBox.information(
                self, "Alias Linked",
                f"'{cur_name}' is now an alias of '{canon_name}'.\n\n"
                f"Both entities keep their own identity blocks (for disguise "
                f"appearances), but the system knows they are the same person."
            )
            self._populate_alias_combo(
                self.current_entity_id,
                self.screenplay.identity_block_metadata.get(self.current_entity_id, {})
            )
        else:
            QMessageBox.warning(self, "Error", "Failed to create alias link.")

    def _on_alias_unlink(self):
        """Remove the alias link from the current entity."""
        if not self.current_entity_id or not self.screenplay:
            return
        ok = self.screenplay.unlink_entity_alias(self.current_entity_id)
        if ok:
            self._populate_alias_combo(
                self.current_entity_id,
                self.screenplay.identity_block_metadata.get(self.current_entity_id, {})
            )
        else:
            QMessageBox.information(
                self, "Not an Alias",
                "This entity is not currently linked as an alias."
            )

    def _fit_notes_to_content(self):
        """Resize user_notes_edit to fit its text content with a small margin."""
        doc = self.user_notes_edit.document()
        doc.adjustSize()
        margins = self.user_notes_edit.contentsMargins()
        h = int(doc.size().height()) + margins.top() + margins.bottom() + 10
        h = max(h, 36)
        self.user_notes_edit.setFixedHeight(h)

    def _load_character_wardrobe(self, entity_id: str):
        """Load wardrobe text from the current scene into the user notes field (characters only)."""
        wardrobe_text = ""
        if self.screenplay and self.current_scene:
            scene_id = getattr(self.current_scene, "scene_id", None)
            if scene_id:
                wardrobe_text = self.screenplay.get_character_wardrobe_for_scene(scene_id, entity_id) or ""
        self.user_notes_edit.blockSignals(True)
        self.user_notes_edit.setPlainText(wardrobe_text)
        self.user_notes_edit.blockSignals(False)
    
    def _save_character_wardrobe(self, entity_id: str, wardrobe_text: str):
        """Save wardrobe text to the current scene's character_wardrobe (characters only)."""
        if not self.screenplay or not self.current_scene:
            return
        scene_id = getattr(self.current_scene, "scene_id", None)
        if scene_id:
            self.screenplay.set_character_wardrobe_for_scene(scene_id, entity_id, wardrobe_text)
    
    def on_notes_changed(self):
        """Handle user notes text change."""
        # For characters, auto-save wardrobe to current scene
        if self.current_entity_id and self.screenplay:
            metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
            if metadata and (metadata.get("type") or "").lower() == "character":
                wardrobe_text = self.user_notes_edit.toPlainText()
                self._save_character_wardrobe(self.current_entity_id, wardrobe_text)
        self.update_button_states()
    
    def on_block_changed(self):
        """Handle identity block text change."""
        self.update_button_states()
    
    def update_button_states(self):
        """Update button enabled states based on current state."""
        has_entity = self.current_entity_id is not None
        has_notes = len(self.user_notes_edit.toPlainText().strip()) > 0
        has_block = len(self.identity_block_edit.toPlainText().strip()) > 0
        has_ref_prompt = len(self.ref_image_prompt_edit.toPlainText().strip()) > 0
        
        # Check if entity is approved
        is_approved = False
        if has_entity and self.screenplay:
            metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
            if metadata:
                is_approved = metadata.get("status") == "approved"
        
        self.generate_btn.setEnabled(has_entity and has_notes and self.ai_generator is not None)
        self.approve_btn.setEnabled(has_entity and has_block)
        self.delete_btn.setEnabled(has_entity)
        
        # List-level action buttons (may not exist in older UI state)
        if hasattr(self, "remove_entity_btn"):
            self.remove_entity_btn.setEnabled(has_entity)
        if hasattr(self, "select_all_btn"):
            has_any = bool(self.screenplay and self.screenplay.identity_block_metadata)
            self.select_all_btn.setEnabled(has_any)
        
        # Reference image prompt buttons - only enabled for approved blocks
        self.generate_ref_prompt_btn.setEnabled(has_entity and is_approved and has_block and self.ai_generator is not None)
        self.generate_ref_prompt_btn.setText("Regenerate Image Prompt" if has_ref_prompt else "Generate Reference Image Prompt")
        self.copy_ref_prompt_btn.setEnabled(has_ref_prompt)

    def select_all_entities(self):
        """Select all entity items in the tree (skipping category headers)."""
        self.entity_tree.clearSelection()
        for i in range(self.entity_tree.topLevelItemCount()):
            category_item = self.entity_tree.topLevelItem(i)
            category_item.setExpanded(True)
            for j in range(category_item.childCount()):
                child = category_item.child(j)
                if not child.isHidden():
                    child.setSelected(True)
    
    def generate_identity_block(self):
        """Generate identity block from user notes using AI."""
        if not self.current_entity_id or not self.screenplay or not self.ai_generator:
            if not self.ai_generator:
                QMessageBox.warning(self, "No AI Generator", "AI Generator not initialized. Please check your settings.")
            return
        
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        if not metadata:
            return
        
        # For characters: use the Scene Wardrobe field as user_notes (clothing/accessories).
        #   wizard_physical_appearance is passed separately as supplementary context.
        # For non-characters: use the user_notes field as before.
        entity_type = (metadata.get("type") or "").lower()
        entity_name = metadata.get("name", "")
        wizard_physical_appearance = ""
        
        if entity_type == "character":
            # Get wizard physical_appearance (supplementary — passed separately)
            story_outline = getattr(self.screenplay, "story_outline", {}) or {}
            wizard_chars = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
            for wc in wizard_chars:
                if isinstance(wc, dict) and wc.get("name", "").strip().lower() == (entity_name or "").strip().lower():
                    wizard_physical_appearance = str(wc.get("physical_appearance", "") or "").strip()
                    break
            
            # For identity generation, use the Scene Wardrobe text
            user_notes = self.user_notes_edit.toPlainText().strip()
            if not user_notes:
                QMessageBox.warning(
                    self, "No Wardrobe",
                    "Please provide scene wardrobe details before generating.\n\n"
                    "Describe clothing, accessories, armor, or scene-specific appearance state."
                )
                return
        else:
            user_notes = self.user_notes_edit.toPlainText().strip()
            if not user_notes:
                QMessageBox.warning(self, "No Notes", "Please provide user notes before generating.")
                return
        
        # Get scene context
        scene_context = ""
        scene_id = metadata.get("scene_id", "")
        if scene_id:
            scene = self.screenplay.get_scene(scene_id)
            if scene and scene.description:
                scene_context = scene.description
        
        # If no scene context, use first scene with this entity mentioned
        if not scene_context:
            for scene in self.screenplay.get_all_scenes():
                if scene.description and metadata.get("name", "") in scene.description:
                    scene_context = scene.description
                    break
        
        # For environments: strip character actions/wardrobe/dialogue from scene context
        # so the AI only sees setting/location text.
        if entity_type == "environment" and scene_context and self.ai_generator:
            scene_context = self.ai_generator._extract_environment_only_context(
                scene_context, entity_name
            )

        # For environments: extract spatial layout implications from the full generated
        # scene content (character actions reveal architecture: freestanding furniture,
        # exits, passages, hidden doors, structural ceiling, etc.)
        if entity_type == "environment" and self.ai_generator:
            full_scene_text = ""
            _scene_id = metadata.get("scene_id", "")
            if _scene_id:
                _scene_obj = self.screenplay.get_scene(_scene_id)
                if _scene_obj:
                    _scene_meta = getattr(_scene_obj, "metadata", None) or {}
                    full_scene_text = _scene_meta.get("generated_content", "") or ""
            if not full_scene_text:
                for _s in self.screenplay.get_all_scenes():
                    if _s.description and metadata.get("name", "") in _s.description:
                        _s_meta = getattr(_s, "metadata", None) or {}
                        full_scene_text = _s_meta.get("generated_content", "") or ""
                        if full_scene_text:
                            break
            if full_scene_text:
                spatial_layout = self.ai_generator._extract_spatial_layout_from_actions(full_scene_text)
                if spatial_layout:
                    scene_context += (
                        "\n\nSPATIAL LAYOUT (derived from character movement in the scene — "
                        "must be reflected in the environment architecture and furniture arrangement):\n"
                        + spatial_layout
                    )

        # For environments: append passive entity names and an exclusion list of
        # non-passive entities so only passive items get baked into the description.
        if entity_type == "environment" and self.screenplay:
            passive_names = self.screenplay.get_passive_entity_names()
            if passive_names:
                scene_context += (
                    "\n\nPASSIVE SET DRESSING (include in the environment description): "
                    + ", ".join(passive_names)
                )

            non_passive = []
            meta_all = getattr(self.screenplay, "identity_block_metadata", {}) or {}
            for _eid, emeta in meta_all.items():
                etype = (emeta.get("type") or "").lower()
                if etype in ("character", "object", "vehicle") and emeta.get("status") != "passive":
                    ename = (emeta.get("name") or "").strip()
                    if ename:
                        non_passive.append(ename)
            if non_passive:
                scene_context += (
                    "\n\nDO NOT DESCRIBE THESE ENTITIES (they have their own identity blocks): "
                    + ", ".join(non_passive)
                )

        # Start generation thread
        self.generation_thread = IdentityBlockGenerationThread(
            self.ai_generator,
            entity_name,
            metadata.get("type", ""),
            user_notes,
            scene_context,
            self.screenplay,
            wizard_physical_appearance=wizard_physical_appearance
        )
        self.generation_thread.finished.connect(self.on_generation_finished)
        self.generation_thread.error.connect(self.on_generation_error)
        
        # Show progress dialog - make it more visible
        entity_type_display = metadata.get("type", "entity")
        progress = QProgressDialog(
            f"AI is generating identity block for {entity_name} ({entity_type_display})...\n\nPlease wait, this may take a moment.",
            None,  # No cancel button
            0, 
            0, 
            self
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)  # Application modal to ensure visibility
        progress.setMinimumDuration(0)  # Show immediately
        progress.setWindowTitle("Generating Identity Block")
        progress.setCancelButton(None)  # No cancel for now
        progress.setMinimum(0)
        progress.setMaximum(0)  # Indeterminate progress
        progress.setValue(0)
        
        # Ensure dialog is visible and on top
        progress.show()
        progress.raise_()
        progress.activateWindow()
        
        # Force the dialog to be processed and displayed
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Update status — do not overwrite user_notes for characters
        if entity_type == "character":
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="generating"
            )
        else:
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="generating",
                user_notes=user_notes
            )
        
        self.generation_thread.start()
        
        # Store progress dialog reference
        self.progress_dialog = progress
    
    def on_generation_finished(self, identity_block: str):
        """Handle successful identity block generation."""
        was_retry = getattr(self, '_identity_generation_retry', False)
        if was_retry:
            delattr(self, '_identity_generation_retry')
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            delattr(self, 'progress_dialog')
        
        # Update metadata first
        if self.current_entity_id and self.screenplay:
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="placeholder",  # Still needs approval
                identity_block=identity_block
            )
        
        # Block tree selection signals to prevent interference
        self.entity_tree.blockSignals(True)
        
        # Update UI elements directly and ensure they're visible
        self.identity_block_edit.setPlainText(identity_block)
        self.entity_status_label.setText("Placeholder")
        self.update_entity_status_in_tree("Placeholder")
        self.update_button_states()
        
        # Ensure the entity remains selected and visible
        self.ensure_entity_selected()
        
        # Unblock signals
        self.entity_tree.blockSignals(False)
        
        self._show_status("Identity block generated — review and click Approve", 5000)
    
    def on_generation_error(self, error_message: str):
        """Handle identity block generation error."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            delattr(self, 'progress_dialog')
        
        # Restore status
        if self.current_entity_id and self.screenplay:
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="placeholder"
            )
        
        # Update UI elements directly
        self.update_button_states()
        self.update_entity_status_in_tree("Placeholder")
        
        QMessageBox.critical(self, "Generation Error", 
                            f"Failed to generate identity block:\n\n{error_message}")
    
    def approve_identity_block(self):
        """Approve and save the identity block."""
        if not self.current_entity_id or not self.screenplay:
            return
        
        identity_block = self.identity_block_edit.toPlainText().strip()
        
        if not identity_block:
            QMessageBox.warning(self, "No Identity Block", 
                               "Please generate or enter an identity block before approving.")
            return
        
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        entity_type = (metadata.get("type") or "").lower() if metadata else ""
        
        if entity_type == "character":
            # For characters, do NOT write user_notes to identity block metadata
            # (wardrobe is stored per-scene via character_wardrobe)
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="approved",
                identity_block=identity_block
            )
        else:
            # Non-character: save user_notes in metadata as before
            user_notes = self.user_notes_edit.toPlainText().strip()
            self.screenplay.update_identity_block_metadata(
                self.current_entity_id,
                status="approved",
                user_notes=user_notes,
                identity_block=identity_block
            )
        
        # Block tree selection signals to prevent interference
        self.entity_tree.blockSignals(True)
        
        # Update UI elements directly and immediately
        self.entity_status_label.setText("Approved")
        self.update_entity_status_in_tree("Approved")
        self.update_button_states()
        
        # Auto-generate reference image prompt when AI is available
        ref_prompt_generated = False
        if self.ai_generator:
            metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
            if metadata and metadata.get("identity_block"):
                entity_name = metadata.get("name", "Unknown")
                entity_type = metadata.get("type", "object")
                scene_lighting = ""
                if entity_type == "environment":
                    scene_id = metadata.get("scene_id", "")
                    if scene_id:
                        source_scene = self.screenplay.get_scene(scene_id)
                        scene_lighting = self.ai_generator._extract_lighting_from_scene(source_scene)
                ss = getattr(self.screenplay, "story_settings", None) or {}
                vs_key = ss.get("visual_style") or "photorealistic"
                try:
                    ref_prompt = self.ai_generator.generate_reference_image_prompt(
                        entity_name=entity_name,
                        entity_type=entity_type,
                        identity_block=metadata.get("identity_block", ""),
                        metadata=metadata,
                        scene_lighting=scene_lighting,
                        visual_style=vs_key,
                        content_rating=ss.get("content_rating", ""),
                    )
                    if ref_prompt and ref_prompt.strip():
                        self.screenplay.update_identity_block_metadata(
                            self.current_entity_id,
                            reference_image_prompt=ref_prompt
                        )
                        self.ref_image_prompt_edit.setPlainText(ref_prompt)
                        ref_prompt_generated = True
                except Exception:
                    pass  # Non-blocking; user can generate manually later
        
        self.update_button_states()
        
        # Ensure the entity remains selected and visible BEFORE unblocking
        self.ensure_entity_selected()
        
        # Emit signals after UI update (while signals still blocked)
        self.identity_block_updated.emit(self.current_entity_id)
        self.identity_blocks_changed.emit()
        
        status_msg = "Identity block approved"
        if ref_prompt_generated:
            status_msg += " — reference prompt generated"
        self._show_status(status_msg, 4000)
        
        # Unblock signals LAST
        self.entity_tree.blockSignals(False)
    
    def _mark_passive_entity(self):
        """Mark selected object/vehicle entities as passive (name-only, no identity block needed)."""
        selected = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected or not self.screenplay:
            return
        count = 0
        for item in selected:
            entity_id = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.get_identity_block_metadata_by_id(entity_id) or {}
            if (meta.get("type") or "").lower() in ("object", "vehicle") and meta.get("status") != "passive":
                self.screenplay.update_identity_block_metadata(
                    entity_id, status="passive", identity_block=""
                )
                count += 1
        if count:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()
            label = "entity" if count == 1 else "entities"
            self._show_status(f"{count} {label} marked as passive (name only)")

    def _unmark_passive_entity(self):
        """Remove the passive label from selected entities, resetting to placeholder status."""
        selected = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected or not self.screenplay:
            return
        count = 0
        for item in selected:
            entity_id = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.get_identity_block_metadata_by_id(entity_id) or {}
            if (meta.get("type") or "").lower() in ("object", "vehicle") and meta.get("status") == "passive":
                self.screenplay.update_identity_block_metadata(
                    entity_id, status="placeholder"
                )
                count += 1
        if count:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()
            label = "entity" if count == 1 else "entities"
            self._show_status(f"Passive label removed from {count} {label}")

    def _approve_selected_identity_blocks(self):
        """Approve identity blocks for all selected entities that have a generated block."""
        if not self.screenplay:
            return
        selected = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected:
            return
        count = 0
        for item in selected:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.get_identity_block_metadata_by_id(eid) or {}
            if meta.get("identity_block") and meta.get("status") != "approved":
                entity_type = (meta.get("type") or "").lower()
                if entity_type == "character":
                    self.screenplay.update_identity_block_metadata(eid, status="approved")
                else:
                    self.screenplay.update_identity_block_metadata(
                        eid, status="approved",
                        user_notes=meta.get("user_notes", ""),
                        identity_block=meta.get("identity_block", "")
                    )
                count += 1
        if count:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()
            label = "block" if count == 1 else "blocks"
            self._show_status(f"{count} identity {label} approved")
        else:
            self._show_status("No unapproved blocks found in selection")

    def _generate_selected_identity_blocks(self):
        """Generate identity blocks for all selected object/vehicle entities."""
        if not self.screenplay or not self.ai_generator:
            return
        selected = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected:
            return

        items_to_generate = []
        for item in selected:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.get_identity_block_metadata_by_id(eid) or {}
            entity_type = (meta.get("type") or "").lower()
            if entity_type not in ("object", "vehicle"):
                continue
            user_notes = (meta.get("user_notes") or "").strip()
            if not user_notes:
                continue
            entity_name = meta.get("name", "")
            scene_context = ""
            scene_id = meta.get("scene_id", "")
            if scene_id:
                scene = self.screenplay.get_scene(scene_id)
                if scene and scene.description:
                    scene_context = scene.description
            if not scene_context:
                for scene in self.screenplay.get_all_scenes():
                    if scene.description and entity_name in scene.description:
                        scene_context = scene.description
                        break
            items_to_generate.append((eid, entity_name, entity_type, user_notes, scene_context))

        if not items_to_generate:
            self._show_status("No eligible items to generate (need user notes)")
            return

        progress = QProgressDialog(
            f"Generating identity blocks (0/{len(items_to_generate)})...",
            "Cancel", 0, len(items_to_generate), self
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setWindowTitle("Batch Generate Identity Blocks")
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        generated = 0
        for i, (eid, name, etype, notes, ctx) in enumerate(items_to_generate):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"Generating identity block for {name}... ({i+1}/{len(items_to_generate)})")
            progress.setValue(i)
            QApplication.processEvents()
            try:
                block = self.ai_generator.generate_identity_block_from_notes(
                    name, etype, notes, ctx, self.screenplay
                )
                self.screenplay.update_identity_block_metadata(
                    eid, status="placeholder", identity_block=block, user_notes=notes
                )
                generated += 1
            except Exception as e:
                _safe_print(f"WARNING: Failed to generate identity block for {name}: {e}")

        progress.setValue(len(items_to_generate))
        progress.close()

        if generated:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()
            label = "block" if generated == 1 else "blocks"
            self._show_status(f"{generated} identity {label} generated — review and approve")

    def _generate_selected_reference_prompts(self):
        """Generate reference image prompts for all selected approved entities."""
        if not self.screenplay or not self.ai_generator:
            return
        selected = [
            item for item in self.entity_tree.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole)
        ]
        if not selected:
            return

        items_to_generate = []
        for item in selected:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            meta = self.screenplay.get_identity_block_metadata_by_id(eid) or {}
            if meta.get("status") != "approved" or not meta.get("identity_block"):
                continue
            entity_name = meta.get("name", "Unknown")
            entity_type = meta.get("type", "object")
            scene_lighting = ""
            if entity_type == "environment":
                scene_id = meta.get("scene_id", "")
                if scene_id:
                    source_scene = self.screenplay.get_scene(scene_id)
                    scene_lighting = self.ai_generator._extract_lighting_from_scene(source_scene)
            items_to_generate.append((eid, entity_name, entity_type, meta, scene_lighting))

        if not items_to_generate:
            self._show_status("No approved entities in selection")
            return

        ss = getattr(self.screenplay, "story_settings", None) or {}
        vs_key = ss.get("visual_style") or "photorealistic"
        content_rating = ss.get("content_rating", "")

        progress = QProgressDialog(
            f"Generating reference prompts (0/{len(items_to_generate)})...",
            "Cancel", 0, len(items_to_generate), self
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setWindowTitle("Batch Generate Reference Prompts")
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        generated = 0
        for i, (eid, name, etype, meta, lighting) in enumerate(items_to_generate):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"Generating reference prompt for {name}... ({i+1}/{len(items_to_generate)})")
            progress.setValue(i)
            QApplication.processEvents()
            try:
                ref_prompt = self.ai_generator.generate_reference_image_prompt(
                    entity_name=name, entity_type=etype,
                    identity_block=meta.get("identity_block", ""),
                    metadata=meta, scene_lighting=lighting,
                    visual_style=vs_key, content_rating=content_rating,
                )
                self.screenplay.update_identity_block_metadata(eid, reference_image_prompt=ref_prompt)
                generated += 1
            except Exception as e:
                _safe_print(f"WARNING: Failed to generate reference prompt for {name}: {e}")

        progress.setValue(len(items_to_generate))
        progress.close()

        if generated:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()
            label = "prompt" if generated == 1 else "prompts"
            self._show_status(f"{generated} reference {label} generated")

    def delete_entity(self):
        """Delete the current entity."""
        if not self.current_entity_id or not self.screenplay:
            return
        
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        if not metadata:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the identity block for '{metadata.get('name', 'this entity')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from metadata
            del self.screenplay.identity_block_metadata[self.current_entity_id]
            
            # Remove from legacy storage
            if self.current_entity_id in self.screenplay.identity_blocks:
                del self.screenplay.identity_blocks[self.current_entity_id]
            
            # Remove ID mapping
            entity_key = f"{metadata.get('type', '')}:{metadata.get('name', '')}".lower()
            if entity_key in self.screenplay.identity_block_ids:
                del self.screenplay.identity_block_ids[entity_key]
            
            # Emit signal
            self.identity_blocks_changed.emit()
            
            # Clear editor and refresh list
            self.clear_editor()
            self.refresh_entity_list()
            
            self._show_status("Entity identity block deleted")
    
    def generate_reference_image_prompt(self):
        """Generate a reference image prompt for Higgsfield from the approved identity block."""
        if not self.current_entity_id or not self.screenplay or not self.ai_generator:
            if not self.ai_generator:
                QMessageBox.warning(self, "No AI Generator", "AI Generator not initialized. Please check your settings.")
            return
        
        metadata = self.screenplay.get_identity_block_metadata_by_id(self.current_entity_id)
        if not metadata:
            return
        
        # Check if approved
        if metadata.get("status") != "approved":
            QMessageBox.warning(
                self, 
                "Not Approved", 
                "Please approve the identity block before generating a reference image prompt."
            )
            return
        
        identity_block = metadata.get("identity_block", "")
        if not identity_block:
            QMessageBox.warning(self, "No Identity Block", "No identity block found. Please generate and approve one first.")
            return
        
        entity_name = metadata.get("name", "Unknown")
        entity_type = metadata.get("type", "object")
        
        # Extract scene lighting for environment entities
        scene_lighting = ""
        if entity_type == "environment":
            scene_id = metadata.get("scene_id", "")
            if scene_id:
                source_scene = self.screenplay.get_scene(scene_id)
                scene_lighting = self.ai_generator._extract_lighting_from_scene(source_scene)
        
        ss = getattr(self.screenplay, "story_settings", None) or {}
        vs_key = ss.get("visual_style") or "photorealistic"
        ref_prompt = self.ai_generator.generate_reference_image_prompt(
            entity_name=entity_name,
            entity_type=entity_type,
            identity_block=identity_block,
            metadata=metadata,
            scene_lighting=scene_lighting,
            visual_style=vs_key,
            content_rating=ss.get("content_rating", ""),
        )
        
        # Block tree selection signals to prevent interference
        self.entity_tree.blockSignals(True)
        
        # Save to screenplay metadata first
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id,
            reference_image_prompt=ref_prompt
        )
        
        # Update UI elements directly - ensure prompt is visible
        self.ref_image_prompt_edit.setPlainText(ref_prompt)
        self.update_button_states()
        
        # Ensure the entity remains selected and visible BEFORE unblocking
        self.ensure_entity_selected()
        
        # Emit change signal (while signals still blocked)
        self.identity_blocks_changed.emit()
        
        self._show_status(f"Reference image prompt generated for '{entity_name}'", 4000)
        
        # Unblock signals LAST
        self.entity_tree.blockSignals(False)
    
    def copy_reference_prompt_to_clipboard(self):
        """Copy the reference image prompt to clipboard."""
        ref_prompt = self.ref_image_prompt_edit.toPlainText().strip()
        if not ref_prompt:
            QMessageBox.warning(self, "No Prompt", "No reference image prompt to copy.")
            return
        
        # Copy to clipboard
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(ref_prompt)
        
        self._show_status("Reference image prompt copied to clipboard")
    
    def save_reference_image_prompt(self):
        """Save the edited reference image prompt to the identity block metadata."""
        if not self.current_entity_id or not self.screenplay:
            return
        ref_prompt = self.ref_image_prompt_edit.toPlainText().strip()
        self.screenplay.update_identity_block_metadata(
            self.current_entity_id,
            reference_image_prompt=ref_prompt
        )
        self.identity_blocks_changed.emit()
        self._show_status("Reference image prompt saved")

    def batch_regenerate_reference_prompts(self, visual_style: str = "") -> dict:
        """Regenerate all existing reference image prompts using the given visual style.

        Only entities that already have an approved identity block AND an existing
        reference image prompt are regenerated.  Wardrobe variant reference prompts
        on the screenplay are also regenerated.

        Args:
            visual_style: The style key from story settings (e.g. "comic_book").

        Returns:
            {"identity_count": int, "wardrobe_count": int, "errors": list[str]}
        """
        result = {"identity_count": 0, "wardrobe_count": 0, "errors": []}
        if not self.screenplay or not self.ai_generator:
            return result

        vs_key = visual_style or "photorealistic"
        _batch_ss = getattr(self.screenplay, "story_settings", None) or {}
        _batch_cr = _batch_ss.get("content_rating", "")

        for entity_id, meta in self.screenplay.identity_block_metadata.items():
            if meta.get("status") != "approved":
                continue
            ib_text = meta.get("identity_block", "").strip()
            old_rip = meta.get("reference_image_prompt", "").strip()
            if not ib_text or not old_rip:
                continue

            entity_name = meta.get("name", "Unknown")
            entity_type = meta.get("type", "object")
            scene_lighting = ""
            if entity_type == "environment":
                scene_id = meta.get("scene_id", "")
                if scene_id:
                    source_scene = self.screenplay.get_scene(scene_id)
                    if source_scene:
                        scene_lighting = self.ai_generator._extract_lighting_from_scene(source_scene)
            try:
                new_rip = self.ai_generator.generate_reference_image_prompt(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    identity_block=ib_text,
                    metadata=meta,
                    scene_lighting=scene_lighting,
                    visual_style=vs_key,
                    content_rating=_batch_cr,
                )
                if new_rip and new_rip.strip():
                    self.screenplay.update_identity_block_metadata(
                        entity_id, reference_image_prompt=new_rip.strip()
                    )
                    result["identity_count"] += 1
            except Exception as exc:
                result["errors"].append(f"{entity_name}: {exc}")

        wv = getattr(self.screenplay, "character_wardrobe_variants", {})
        for entity_id, variants in wv.items():
            ib_meta = self.screenplay.get_identity_block_metadata_by_id(entity_id)
            entity_name = ib_meta.get("name", "Unknown") if ib_meta else "Unknown"
            for v in variants:
                ib_text = v.get("identity_block", "").strip()
                old_rip = v.get("reference_image_prompt", "").strip()
                if not ib_text or not old_rip:
                    continue
                try:
                    new_rip = self.ai_generator.generate_reference_image_prompt(
                        entity_name=entity_name,
                        entity_type="character",
                        identity_block=ib_text,
                        visual_style=vs_key,
                        content_rating=_batch_cr,
                    )
                    if new_rip and new_rip.strip():
                        v["reference_image_prompt"] = new_rip.strip()
                        result["wardrobe_count"] += 1
                except Exception as exc:
                    label = v.get("label", v.get("variant_id", "?"))
                    result["errors"].append(f"{entity_name} wardrobe '{label}': {exc}")

        if result["identity_count"] > 0 or result["wardrobe_count"] > 0:
            self.identity_blocks_changed.emit()
            self.refresh_entity_list()

        return result