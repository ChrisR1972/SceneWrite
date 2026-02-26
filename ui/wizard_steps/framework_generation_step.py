"""
Step 4: Framework Generation Widget for the Story Creation Wizard.
Automatically generates the story framework after outline confirmation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QProgressDialog, QTextEdit, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from typing import Optional, Dict, Any, List
from core.ai_generator import AIGenerator
from core.screenplay_engine import Screenplay
from core.spell_checker import enable_spell_checking

# Reuse FrameworkGenerationThread from story_framework_view
from ..story_framework_view import FrameworkGenerationThread


class FrameworkGenerationStepWidget(QWidget):
    """Step 4: Framework generation with progress and summary."""
    
    framework_ready = pyqtSignal(Screenplay)  # Emits generated screenplay
    
    def __init__(self, ai_generator: Optional[AIGenerator] = None, parent=None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.framework_thread: Optional[FrameworkGenerationThread] = None
        self.progress_dialog: Optional[QProgressDialog] = None
        self.generated_screenplay: Optional[Screenplay] = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        from PyQt6.QtWidgets import QSizePolicy
        # Set size policy to prevent expansion
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(size_policy)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("Step 4: Generate Story Framework")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        description = QLabel(
            "The story framework will be automatically generated based on your premise and outline. "
            "This will create the act and scene structure for your screenplay."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Premise summary (shows original input from Step 2)
        premise_group = QGroupBox("Premise Summary")
        premise_layout = QVBoxLayout()
        self.premise_meta_label = QLabel("Title: — | Genres: — | Atmosphere: —")
        self.premise_meta_label.setStyleSheet("color: #666; font-size: 10px;")
        premise_layout.addWidget(self.premise_meta_label)
        self.premise_text = QTextEdit()
        self.premise_text.setReadOnly(True)
        self.premise_text.setMaximumHeight(120)
        self.premise_text.setPlaceholderText("Your premise from Step 2 will appear here...")
        premise_layout.addWidget(self.premise_text)
        premise_group.setLayout(premise_layout)
        layout.addWidget(premise_group)
        
        # Generation status
        self.status_label = QLabel("Ready to generate framework...")
        self.status_label.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(self.status_label)
        
        # Framework summary (shown after generation)
        summary_group = QGroupBox("Framework Summary")
        summary_layout = QVBoxLayout()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(200)
        self.summary_text.setPlaceholderText("Framework summary will appear here after generation...")
        summary_layout.addWidget(self.summary_text)
        summary_group.setLayout(summary_layout)
        summary_group.hide()  # Hide until framework is generated
        layout.addWidget(summary_group)
        self.summary_group = summary_group
        
        # Tab key moves focus (not indentation)
        self.premise_text.setTabChangesFocus(True)
        self.summary_text.setTabChangesFocus(True)
        
        layout.addStretch()
    
    def start_generation(self, premise: str, title: str, genres: List[str], atmosphere: str, story_outline: Dict[str, Any], length: str = "medium", intent: str = "General Story", brand_context=None):
        """Start framework generation."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        # Update summary display
        safe_title = title.strip() if title else "—"
        safe_genres = ", ".join(genres) if genres else "—"
        safe_atmosphere = atmosphere.strip() if atmosphere else "—"
        self.premise_meta_label.setText(f"Title: {safe_title} | Genres: {safe_genres} | Atmosphere: {safe_atmosphere}")
        self.premise_text.setPlainText(premise.strip() if premise else "")
        
        # Use the user-selected length (micro, short, medium, or long)
        # Validate length
        if length not in ["micro", "short", "medium", "long"]:
            length = "medium"  # Default to medium if invalid
        
        # Display length info
        length_descriptions = {
            "micro": "Micro (1 act, 1-5 scenes)",
            "short": "Short (3 acts, 9-15 scenes)",
            "medium": "Medium (3 acts, 15-24 scenes)",
            "long": "Long (5 acts, 30-50 scenes)"
        }
        length_desc = length_descriptions.get(length, "Medium (3 acts, 15-24 scenes)")
        self.status_label.setText(f"Generating framework ({length_desc})...")
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog("Generating story framework...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowTitle("Generating Framework")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # Process events
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Clean up any existing thread
        if self.framework_thread and self.framework_thread.isRunning():
            self.framework_thread.terminate()
            self.framework_thread.wait()
        
        # Create and start generation thread
        self.framework_thread = FrameworkGenerationThread(
            self.ai_generator, premise, title, length, atmosphere, genres, story_outline, intent, brand_context
        )
        self.framework_thread.finished.connect(self.on_framework_generated)
        self.framework_thread.error.connect(self.on_framework_error)
        self.framework_thread.start()
    
    def on_framework_generated(self, screenplay: Screenplay):
        """Handle successful framework generation."""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        self.generated_screenplay = screenplay
        
        # Ensure story_outline is preserved (it should already be set by generate_story_framework, but double-check)
        # The story_outline is passed to the generation thread and should be preserved
        
        # Update status
        total_acts = len(screenplay.acts)
        total_scenes = sum(len(act.scenes) for act in screenplay.acts)
        self.status_label.setText(f"Framework generated successfully! ({total_acts} acts, {total_scenes} scenes)")
        self.status_label.setStyleSheet("font-size: 12px; color: #006400; font-weight: bold;")
        
        # Generate summary
        summary_lines = [
            f"Title: {screenplay.title or 'Untitled'}",
            f"Acts: {total_acts}",
            f"Total Scenes: {total_scenes}",
            "",
            "Act Breakdown:"
        ]
        
        for act in screenplay.acts:
            summary_lines.append(f"  Act {act.act_number}: {act.title} ({len(act.scenes)} scenes)")
            if act.description:
                summary_lines.append(f"    {act.description[:100]}...")
        
        if screenplay.story_structure:
            summary_lines.append("")
            summary_lines.append("Story Structure:")
            if "overall_plot" in screenplay.story_structure:
                summary_lines.append(f"  {screenplay.story_structure['overall_plot'][:200]}...")
        
        self.summary_text.setPlainText("\n".join(summary_lines))
        self.summary_group.show()
        
        # Emit signal
        self.framework_ready.emit(screenplay)
    
    def on_framework_error(self, error_message: str):
        """Handle framework generation error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate story framework:\n{error_message}")
        self.status_label.setText("Framework generation failed. Please try again.")
        self.status_label.setStyleSheet("font-size: 12px; color: #cc0000;")
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

