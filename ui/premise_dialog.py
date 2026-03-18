"""
Premise input/generation dialog for SceneWrite.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTextEdit,
    QPushButton, QLabel, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QMessageBox, QWidget, QScrollArea, QProgressDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont
from typing import List, Optional
from core.ai_generator import AIGenerator
from core.spell_checker import enable_spell_checking

class PremiseGenerationThread(QThread):
    """Thread for generating premise to avoid blocking UI."""
    
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, genres, atmosphere, workflow_profile=None, brand_context=None, rejected_premises=None, series_premise=None, episode_number=0, total_episodes=0, episode_plan=None):
        super().__init__()
        self.ai_generator = ai_generator
        self.genres = genres
        self.atmosphere = atmosphere
        self.workflow_profile = workflow_profile
        self.brand_context = brand_context
        self.rejected_premises = rejected_premises or []
        self.series_premise = series_premise
        self.episode_number = episode_number
        self.total_episodes = total_episodes
        self.episode_plan = episode_plan
    
    def run(self):
        """Generate premise in background thread."""
        try:
            # Get raw output to display everything
            premise = self.ai_generator.generate_premise(
                self.genres, 
                self.atmosphere, 
                return_raw=True,
                workflow_profile=self.workflow_profile,
                brand_context=self.brand_context,
                rejected_premises=self.rejected_premises,
                series_premise=self.series_premise,
                episode_number=self.episode_number,
                total_episodes=self.total_episodes,
                episode_plan=self.episode_plan,
            )
            # Ensure premise is not None or empty
            if premise and premise.strip():
                self.finished.emit(premise.strip())
            else:
                # More detailed error message
                error_msg = "Generated premise is empty. "
                if not premise:
                    error_msg += "The AI returned None."
                elif not premise.strip():
                    error_msg += f"The AI returned only whitespace. Raw value: '{premise}'"
                error_msg += " Please check your AI settings and try again."
                self.error.emit(error_msg)
        except Exception as e:
            self.error.emit(str(e))

class PremiseDialog(QDialog):
    """Dialog for entering or generating a story premise."""
    
    premise_accepted = pyqtSignal(str, str, list, str)  # premise, title, genres, atmosphere
    
    GENRES = [
        "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror",
        "Mystery", "Romance", "Sci-Fi", "Thriller", "Western", "Crime",
        "Documentary", "Musical", "War", "Superhero"
    ]
    
    ATMOSPHERES = [
        "Suspenseful", "Lighthearted", "Dark", "Mysterious", "Epic",
        "Intimate", "Tense", "Whimsical", "Melancholic", "Energetic",
        "Somber", "Playful", "Gritty", "Ethereal", "Realistic"
    ]
    
    def __init__(self, parent=None, ai_generator: Optional[AIGenerator] = None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.generated_premise = ""
        self.premise_thread: Optional[PremiseGenerationThread] = None
        self.progress_dialog: Optional[QProgressDialog] = None
        self._rejected_premises: List[str] = []
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Create Story Premise")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        # Title input
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_input = QTextEdit()
        self.title_input.setMaximumHeight(30)
        self.title_input.setPlaceholderText("Enter story title (optional)")
        title_layout.addWidget(self.title_input)
        layout.addLayout(title_layout)
        
        # Tab widget for manual entry vs AI generation
        self.tabs = QTabWidget()
        
        # Tab 1: Manual Entry
        manual_tab = QWidget()
        manual_layout = QVBoxLayout(manual_tab)
        manual_layout.addWidget(QLabel("Enter your story premise:"))
        self.manual_premise_input = QTextEdit()
        self.manual_premise_input.setPlaceholderText(
            "Enter a compelling story premise that would work well as a video storyboard..."
        )
        manual_layout.addWidget(self.manual_premise_input)
        self.tabs.addTab(manual_tab, "Manual Entry")
        
        # Tab 2: AI Generation
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        
        # Genre selection
        genre_group = QGroupBox("Select Genres")
        genre_layout = QVBoxLayout()
        self.genre_checkboxes = []
        
        # Create checkboxes in a grid-like layout
        genres_per_row = 4
        current_row = QHBoxLayout()
        for i, genre in enumerate(self.GENRES):
            checkbox = QCheckBox(genre)
            self.genre_checkboxes.append(checkbox)
            current_row.addWidget(checkbox)
            
            if (i + 1) % genres_per_row == 0 or i == len(self.GENRES) - 1:
                genre_layout.addLayout(current_row)
                if i < len(self.GENRES) - 1:
                    current_row = QHBoxLayout()
        
        genre_group.setLayout(genre_layout)
        ai_layout.addWidget(genre_group)
        
        # Atmosphere selection
        atmosphere_layout = QFormLayout()
        self.atmosphere_combo = QComboBox()
        self.atmosphere_combo.addItems(self.ATMOSPHERES)
        self.atmosphere_combo.setCurrentText("Suspenseful")
        atmosphere_layout.addRow("Atmosphere/Tone:", self.atmosphere_combo)
        ai_layout.addLayout(atmosphere_layout)
        
        # Generate button
        self.generate_button = QPushButton("Generate Premise")
        self.generate_button.clicked.connect(self.generate_premise)
        ai_layout.addWidget(self.generate_button)
        
        # Generated premise display
        ai_layout.addWidget(QLabel("Generated Premise (showing raw AI output):"))
        self.generated_premise_display = QTextEdit()
        self.generated_premise_display.setReadOnly(False)  # Allow editing so user can see and copy the raw output
        self.generated_premise_display.setPlaceholderText(
            "Click 'Generate Premise' to create a story premise based on your selections. The raw AI output will be displayed here..."
        )
        self.generated_premise_display.setMinimumHeight(300)  # Make it larger to show more content
        ai_layout.addWidget(self.generated_premise_display)
        
        self.tabs.addTab(ai_tab, "AI Generation")
        
        layout.addWidget(self.tabs)
        
        # Enable spell checking for editable text widgets
        enable_spell_checking(self.title_input)
        enable_spell_checking(self.manual_premise_input)
        enable_spell_checking(self.generated_premise_display)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(self.accept_premise)
        self.accept_button.setDefault(True)
        button_layout.addWidget(self.accept_button)
        
        layout.addLayout(button_layout)
    
    def generate_premise(self):
        """Generate a premise using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.")
            return
        
        # Get selected genres
        selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
        if not selected_genres:
            QMessageBox.warning(self, "No Genres Selected", "Please select at least one genre.")
            return
        
        atmosphere = self.atmosphere_combo.currentText()
        
        # Track the current premise as rejected (if regenerating)
        current = self.generated_premise_display.toPlainText().strip()
        if current and current not in self._rejected_premises:
            self._rejected_premises.append(current)
        
        # Disable button during generation
        self.generate_button.setEnabled(False)
        self.generate_button.setText("Generating...")
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Generating premise with AI...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowTitle("Generating Premise")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # Process events to ensure dialog appears
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Clean up any existing thread
        if self.premise_thread and self.premise_thread.isRunning():
            self.premise_thread.terminate()
            self.premise_thread.wait()
        
        # Create and start generation thread with rejected premises
        self.premise_thread = PremiseGenerationThread(
            self.ai_generator, selected_genres, atmosphere,
            rejected_premises=list(self._rejected_premises),
        )
        self.premise_thread.finished.connect(self.on_premise_generated)
        self.premise_thread.error.connect(self.on_premise_error)
        self.premise_thread.start()
        
        # Ensure thread starts
        if not self.premise_thread.isRunning():
            QMessageBox.warning(self, "Thread Error", "Failed to start generation thread.")
            self.generate_button.setText("Generate Premise")
            self.generate_button.setEnabled(True)
            if self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
    
    def on_premise_generated(self, premise: str):
        """Handle successful premise generation."""
        # Close progress dialog first
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Ensure premise is not empty
        if not premise or not premise.strip():
            QMessageBox.warning(self, "Empty Premise", "The generated premise is empty. Please try again.")
            self.generate_button.setText("Generate Premise")
            self.generate_button.setEnabled(True)
            return
        
        # Set the premise
        self.generated_premise = premise.strip()
        
        # Clear any placeholder and set the text
        self.generated_premise_display.clear()
        self.generated_premise_display.setPlainText(self.generated_premise)
        
        # Verify the text was set
        displayed_text = self.generated_premise_display.toPlainText()
        if displayed_text != self.generated_premise:
            # If text didn't set properly, try again
            self.generated_premise_display.setPlainText(self.generated_premise)
        
        self.generate_button.setText("Generate Premise")
        self.generate_button.setEnabled(True)
        
        # Force UI update and repaint
        self.generated_premise_display.repaint()
        self.repaint()
        
        # Ensure we're on the AI Generation tab so user can see the result
        if self.tabs.currentIndex() != 1:
            self.tabs.setCurrentIndex(1)
    
    def on_premise_error(self, error_message: str):
        """Handle premise generation error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate premise:\n{error_message}")
        self.generate_button.setText("Generate Premise")
        self.generate_button.setEnabled(True)
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def accept_premise(self):
        """Accept the premise and emit signal."""
        title = self.title_input.toPlainText().strip()
        
        if self.tabs.currentIndex() == 0:
            # Manual entry
            premise = self.manual_premise_input.toPlainText().strip()
            if not premise:
                QMessageBox.warning(self, "No Premise", "Please enter a story premise.")
                return
            genres = []
            atmosphere = ""
        else:
            # AI generation
            premise = self.generated_premise_display.toPlainText().strip()
            if not premise:
                QMessageBox.warning(self, "No Premise", "Please generate a premise first.")
                return
            selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
            genres = selected_genres
            atmosphere = self.atmosphere_combo.currentText()
        
        self.premise_accepted.emit(premise, title, genres, atmosphere)
        self.accept()

