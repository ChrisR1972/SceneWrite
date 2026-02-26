"""
Scene Framework Editor dialog for editing scene framework details.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTextEdit,
    QPushButton, QLabel, QLineEdit, QComboBox, QGroupBox, QMessageBox,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List
from core.screenplay_engine import StoryScene, Screenplay
from core.ai_generator import AIGenerator
from core.spell_checker import enable_spell_checking

# Logger functions - temporarily disabled to prevent crashes
def log_exception(msg, exc):
    try:
        import traceback
        print(f"ERROR: {msg}: {exc}")
        traceback.print_exc()
    except:
        pass
def log_error(msg):
    try:
        print(f"ERROR: {msg}")
    except:
        pass
def log_info(msg):
    pass
def get_log_file_path():
    return "N/A"

class SceneFrameworkEditor(QDialog):
    """Dialog for editing scene framework details."""
    
    scene_saved = pyqtSignal(StoryScene)
    
    def __init__(self, scene: StoryScene, screenplay: Screenplay, ai_generator: Optional[AIGenerator], parent=None):
        super().__init__(parent)
        self.scene = scene
        self.screenplay = screenplay
        self.ai_generator = ai_generator
        self.init_ui()
        self.load_scene_data()
    
    def init_ui(self):
        """Initialize the editor UI."""
        self.setWindowTitle(f"Edit Scene: {self.scene.title}")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        
        # Basic info group
        basic_group = QGroupBox("Basic Information")
        basic_layout = QFormLayout()
        
        # Scene number
        basic_layout.addRow("Scene Number:", QLabel(str(self.scene.scene_number)))
        
        # Title
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Scene title...")
        basic_layout.addRow("Title:", self.title_edit)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Description
        desc_group = QGroupBox("Scene Description")
        desc_layout = QVBoxLayout()
        desc_hint = QLabel("3-5 sentences covering plot progression, character development, and key events")
        desc_hint.setWordWrap(True)
        desc_hint.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        desc_layout.addWidget(desc_hint)
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Enter scene description (3-5 sentences)...")
        self.description_edit.setMinimumHeight(120)
        desc_layout.addWidget(self.description_edit)
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Plot point
        plot_group = QGroupBox("Plot Point")
        plot_layout = QVBoxLayout()
        self.plot_point_combo = QComboBox()
        self.plot_point_combo.addItem("None", None)
        self.plot_point_combo.addItem("Inciting Incident", "Inciting Incident")
        self.plot_point_combo.addItem("First Plot Point", "First Plot Point")
        self.plot_point_combo.addItem("Midpoint", "Midpoint")
        self.plot_point_combo.addItem("Climax", "Climax")
        self.plot_point_combo.addItem("Resolution", "Resolution")
        plot_layout.addWidget(self.plot_point_combo)
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)
        
        # Character focus
        char_group = QGroupBox("Character Focus")
        char_layout = QVBoxLayout()
        char_hint = QLabel("Characters featured in this scene")
        char_hint.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        char_layout.addWidget(char_hint)
        
        char_input_layout = QHBoxLayout()
        self.character_input = QLineEdit()
        self.character_input.setPlaceholderText("Enter character name...")
        self.character_input.returnPressed.connect(self.add_character)
        char_input_layout.addWidget(self.character_input)
        
        add_char_btn = QPushButton("Add")
        add_char_btn.clicked.connect(self.add_character)
        char_input_layout.addWidget(add_char_btn)
        char_layout.addLayout(char_input_layout)
        
        self.character_list = QListWidget()
        self.character_list.setMaximumHeight(100)
        char_layout.addWidget(self.character_list)
        
        remove_char_btn = QPushButton("Remove Selected")
        remove_char_btn.clicked.connect(self.remove_character)
        char_layout.addWidget(remove_char_btn)
        
        char_group.setLayout(char_layout)
        layout.addWidget(char_group)
        
        # Pacing
        pacing_group = QGroupBox("Pacing")
        pacing_layout = QVBoxLayout()
        self.pacing_combo = QComboBox()
        self.pacing_combo.addItems(["Fast", "Medium", "Slow"])
        pacing_layout.addWidget(self.pacing_combo)
        pacing_group.setLayout(pacing_layout)
        layout.addWidget(pacing_group)
        
        # Estimated duration
        duration_group = QGroupBox("Estimated Duration")
        duration_layout = QVBoxLayout()
        duration_hint = QLabel("Approximate duration in seconds (0 = auto-calculate from storyboard items)")
        duration_hint.setWordWrap(True)
        duration_hint.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
        duration_layout.addWidget(duration_hint)
        from PyQt6.QtWidgets import QSpinBox
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(0)
        self.duration_spinbox.setMaximum(600)
        self.duration_spinbox.setSuffix(" seconds")
        duration_layout.addWidget(self.duration_spinbox)
        duration_group.setLayout(duration_layout)
        layout.addWidget(duration_group)
        
        # Regenerate button (if AI available)
        if self.ai_generator:
            regenerate_layout = QHBoxLayout()
            regenerate_layout.addStretch()
            self.regenerate_btn = QPushButton("Regenerate Scene with AI")
            self.regenerate_btn.clicked.connect(self.regenerate_scene)
            regenerate_layout.addWidget(self.regenerate_btn)
            layout.addLayout(regenerate_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_scene)
        self.save_button.setDefault(True)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        # Enable spell checking for editable text widgets
        # Note: QLineEdit doesn't support QSyntaxHighlighter directly, so we'll skip title_edit and character_input
        enable_spell_checking(self.description_edit)
    
    def load_scene_data(self):
        """Load scene data into the editor."""
        self.title_edit.setText(self.scene.title)
        self.description_edit.setPlainText(self.scene.description)
        
        # Plot point
        if self.scene.plot_point:
            index = self.plot_point_combo.findData(self.scene.plot_point)
            if index >= 0:
                self.plot_point_combo.setCurrentIndex(index)
        else:
            self.plot_point_combo.setCurrentIndex(0)
        
        # Character focus
        self.character_list.clear()
        for char in self.scene.character_focus:
            self.character_list.addItem(char)
        
        # Pacing
        pacing_index = self.pacing_combo.findText(self.scene.pacing)
        if pacing_index >= 0:
            self.pacing_combo.setCurrentIndex(pacing_index)
        
        # Duration
        self.duration_spinbox.setValue(self.scene.estimated_duration)
    
    def add_character(self):
        """Add a character to the focus list."""
        char_name = self.character_input.text().strip()
        if char_name:
            # Check if already exists
            for i in range(self.character_list.count()):
                if self.character_list.item(i).text() == char_name:
                    return
            self.character_list.addItem(char_name)
            self.character_input.clear()
    
    def remove_character(self):
        """Remove selected character from the list."""
        current_item = self.character_list.currentItem()
        if current_item:
            self.character_list.takeItem(self.character_list.row(current_item))
    
    def regenerate_scene(self):
        """Regenerate the scene using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        self.regenerate_btn.setEnabled(False)
        self.regenerate_btn.setText("Regenerating...")
        
        try:
            # For now, just show a message - full regeneration would require more complex logic
            QMessageBox.information(self, "Regeneration", 
                "Scene regeneration feature coming soon. For now, please edit manually.")
        except Exception as e:
            QMessageBox.critical(self, "Regeneration Failed", f"Failed to regenerate scene:\n{str(e)}")
        finally:
            self.regenerate_btn.setEnabled(True)
            self.regenerate_btn.setText("Regenerate Scene with AI")
    
    def save_scene(self):
        """Save the edited scene."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("save_scene() started")
        except:
            pass
        
        try:
            debug_log("Validating scene title...")
            # Validate
            title = self.title_edit.text().strip()
            if not title:
                QMessageBox.warning(self, "Invalid Input", "Scene title cannot be empty.")
                return
            
            debug_log("Validating scene description...")
            description = self.description_edit.toPlainText().strip()
            if not description:
                QMessageBox.warning(self, "Invalid Input", "Scene description cannot be empty.")
                return
            
            debug_log("Initializing scene fields...")
            # Ensure scene has required fields initialized
            if not hasattr(self.scene, 'metadata') or self.scene.metadata is None:
                self.scene.metadata = {}
            if not hasattr(self.scene, 'character_focus') or self.scene.character_focus is None:
                self.scene.character_focus = []
            if not hasattr(self.scene, 'storyboard_items') or self.scene.storyboard_items is None:
                self.scene.storyboard_items = []
            
            debug_log("Updating scene properties...")
            # Update scene
            self.scene.title = title
            self.scene.description = description
            self.scene.plot_point = self.plot_point_combo.currentData()
            self.scene.pacing = self.pacing_combo.currentText()
            self.scene.estimated_duration = self.duration_spinbox.value()
            
            debug_log("Updating character focus...")
            # Update character focus
            self.scene.character_focus = []
            for i in range(self.character_list.count()):
                item = self.character_list.item(i)
                if item:
                    self.scene.character_focus.append(item.text())
            
            debug_log("Setting updated timestamp...")
            from datetime import datetime
            self.scene.updated_at = datetime.now().isoformat()
            
            debug_log("Emitting scene_saved signal...")
            self.scene_saved.emit(self.scene)
            debug_log("Scene saved signal emitted")
            try:
                log_info(f"Scene saved successfully: {self.scene.scene_id} - {self.scene.title}")
            except:
                pass
            debug_log("Accepting dialog...")
            self.accept()
            debug_log("save_scene() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in save_scene()", e)
            except:
                pass
            try:
                log_exception("Error saving scene", e)
            except:
                import traceback
                print(f"Error saving scene: {e}")
                traceback.print_exc()
            # Show user-friendly message
            try:
                log_path = get_log_file_path()
            except:
                log_path = "N/A"
            QMessageBox.critical(self, "Save Error", 
                f"An error occurred while saving the scene. Please check the log file for details.\n\nLog file location: {log_path}")

