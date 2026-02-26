"""
Step 2: Premise / Profile Creation Widget for the Story Creation Wizard.
Receives length and intent from Step 1.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QMessageBox, QProgressDialog, QSpinBox, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from typing import List, Optional, Dict
import re
from core.ai_generator import AIGenerator
from core.spell_checker import enable_spell_checking
from core.workflow_profile import WorkflowProfileManager, WorkflowProfile

# Reuse PremiseGenerationThread from premise_dialog
from ..premise_dialog import PremiseGenerationThread


class PremiseStepWidget(QWidget):
    """Step 2: Premise creation with manual input or AI generation. Receives length/intent from Step 1."""
    
    premise_ready = pyqtSignal()  # Emitted when premise is valid
    
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
    
    def __init__(self, ai_generator: Optional[AIGenerator] = None, parent=None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.premise_thread: Optional[PremiseGenerationThread] = None
        self.progress_dialog: Optional[QProgressDialog] = None
        self._length = "medium"
        self._intent = "General Story"
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        from PyQt6.QtWidgets import QSizePolicy
        # Set size policy to prevent expansion
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(size_policy)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # Title
        title_label = QLabel("Step 2: Create Your Story Premise")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        description = QLabel(
            "Configure your story details based on the length and intent you selected. "
            "Enter a premise or generate one with AI."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        
        profile_layout = QVBoxLayout()
        profile_layout.setContentsMargins(0, 8, 0, 0)
        
        # Title input
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Story Title (optional):"))
        self.title_input = QTextEdit()
        self.title_input.setMaximumHeight(30)
        self.title_input.setPlaceholderText("Enter story title (optional)")
        title_layout.addWidget(self.title_input)
        profile_layout.addLayout(title_layout)
        
        # Brand / Product Context section (for promotional workflows)
        self.brand_context_group = QGroupBox("Brand / Product Context")
        brand_context_layout = QFormLayout()
        
        self.brand_name_input = QTextEdit()
        self.brand_name_input.setMaximumHeight(30)
        self.brand_name_input.setPlaceholderText("e.g., Acme Corp")
        brand_context_layout.addRow("Brand Name (Optional):", self.brand_name_input)
        
        self.product_name_input = QTextEdit()
        self.product_name_input.setMaximumHeight(30)
        self.product_name_input.setPlaceholderText("e.g., SuperWidget Pro")
        brand_context_layout.addRow("Product Name (Optional):", self.product_name_input)
        
        self.product_description_input = QTextEdit()
        self.product_description_input.setMinimumHeight(60)
        self.product_description_input.setMaximumHeight(100)
        self.product_description_input.setPlaceholderText("Describe the product in 1-2 sentences. What is it? What does it do?")
        brand_context_layout.addRow("What is the product? (Required):", self.product_description_input)
        
        self.core_benefit_input = QTextEdit()
        self.core_benefit_input.setMinimumHeight(60)
        self.core_benefit_input.setMaximumHeight(100)
        self.core_benefit_input.setPlaceholderText("What is the core benefit or promise? What problem does it solve?")
        brand_context_layout.addRow("Core Benefit / Promise (Required):", self.core_benefit_input)
        
        self.target_audience_input = QTextEdit()
        # 2-line height for better readability in wizard
        self.target_audience_input.setMinimumHeight(60)
        self.target_audience_input.setMaximumHeight(60)
        self.target_audience_input.setPlaceholderText("e.g., Young professionals, Parents, Tech enthusiasts")
        brand_context_layout.addRow("Target Audience (Optional):", self.target_audience_input)
        
        self.brand_personality_input = QTextEdit()
        # 2-line height for better readability in wizard
        self.brand_personality_input.setMinimumHeight(60)
        self.brand_personality_input.setMaximumHeight(60)
        self.brand_personality_input.setPlaceholderText("e.g., Innovative, Trustworthy, Playful (comma-separated)")
        brand_context_layout.addRow("Brand Personality (Optional):", self.brand_personality_input)
        
        self.mandatory_elements_input = QTextEdit()
        # 2-line height for better readability in wizard
        self.mandatory_elements_input.setMinimumHeight(60)
        self.mandatory_elements_input.setMaximumHeight(60)
        self.mandatory_elements_input.setPlaceholderText("e.g., logo reveal, product shot, tagline text (comma-separated)")
        brand_context_layout.addRow("Mandatory Inclusions (Optional):", self.mandatory_elements_input)
        
        # Emotional Anchor (advertisement mode)
        self.emotional_anchor_combo = QComboBox()
        self.emotional_anchor_combo.addItem("(Select emotional anchor)", "")
        from core.ad_framework import EMOTIONAL_ANCHORS
        for anchor in EMOTIONAL_ANCHORS:
            self.emotional_anchor_combo.addItem(anchor, anchor)
        self.emotional_anchor_combo.setToolTip(
            "The single emotional thread that runs through the entire commercial.\n"
            "Appears in premise, reinforces in emotional payoff, echoes in brand moment."
        )
        brand_context_layout.addRow("Emotional Anchor:", self.emotional_anchor_combo)
        
        # Distribution Platform (preparation layer)
        self.distribution_platform_combo = QComboBox()
        self.distribution_platform_combo.addItem("(Not specified)", "")
        from core.ad_framework import DISTRIBUTION_PLATFORMS
        for key, info in DISTRIBUTION_PLATFORMS.items():
            self.distribution_platform_combo.addItem(info["label"], key)
        self.distribution_platform_combo.setToolTip(
            "Target distribution platform (affects hook duration, CTA placement, pacing).\n"
            "This is a preparation field for future use."
        )
        brand_context_layout.addRow("Distribution Platform (Optional):", self.distribution_platform_combo)
        
        self.brand_context_group.setLayout(brand_context_layout)
        self.brand_context_group.setVisible(False)  # Shown only for promotional
        profile_layout.addWidget(self.brand_context_group)
        
        # Enable spell checking for brand context fields
        enable_spell_checking(self.brand_name_input)
        enable_spell_checking(self.product_name_input)
        enable_spell_checking(self.product_description_input)
        enable_spell_checking(self.core_benefit_input)
        enable_spell_checking(self.target_audience_input)
        enable_spell_checking(self.brand_personality_input)
        enable_spell_checking(self.mandatory_elements_input)
        
        # Narrative/Experimental options (genre + atmosphere + character count)
        self.narrative_options_widget = QWidget()
        narrative_options_layout = QVBoxLayout(self.narrative_options_widget)
        
        # Genre selection
        self.genre_group = QGroupBox("Select Genres")
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
        
        self.genre_group.setLayout(genre_layout)
        narrative_options_layout.addWidget(self.genre_group)
        profile_layout.addWidget(self.narrative_options_widget)
        
        # Atmosphere and character count (shown for all profiles; labels configured per profile)
        settings_layout = QFormLayout()
        self.atmosphere_combo = QComboBox()
        self.atmosphere_combo.addItems(self.ATMOSPHERES)
        self.atmosphere_combo.setCurrentText("Suspenseful")
        self.atmosphere_label = QLabel("Atmosphere/Tone:")
        settings_layout.addRow(self.atmosphere_label, self.atmosphere_combo)
        self.character_count_label = QLabel("Main Characters (up to):")
        self.character_count_spinbox = QSpinBox()
        self.character_count_spinbox.setMinimum(0)
        self.character_count_spinbox.setMaximum(10)
        self.character_count_spinbox.setValue(4)
        self.character_count_hint = QLabel("The AI will create the protagonist, companions, and antagonist — up to 4 main characters.")
        self.character_count_hint.setWordWrap(True)
        self.character_count_hint.setStyleSheet("color: #555; font-size: 10px;")
        self.character_count_spinbox.valueChanged.connect(self._update_character_count_hint)
        settings_layout.addRow(self.character_count_label, self.character_count_spinbox)
        settings_layout.addRow("", self.character_count_hint)
        profile_layout.addLayout(settings_layout)
        
        # Premise area
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        
        # Premise area: label and hint
        ai_layout.addWidget(QLabel("Premise:"))
        premise_hint = QLabel(
            "Type your own premise here, or use \"Generate Premise\" below to create one from your genre and atmosphere. "
            "When the premise is ready, click Next to continue."
        )
        premise_hint.setWordWrap(True)
        premise_hint.setStyleSheet("color: #555; font-size: 11px; margin-bottom: 4px;")
        ai_layout.addWidget(premise_hint)
        
        self.generated_premise_display = QTextEdit()
        self.generated_premise_display.setReadOnly(False)  # Allow editing
        self.generated_premise_display.setPlaceholderText(
            "Enter your story premise, or leave empty and click Generate Premise below..."
        )
        self.generated_premise_display.setMinimumHeight(80)
        self.generated_premise_display.setMaximumHeight(140)
        self.generated_premise_display.textChanged.connect(self.on_premise_changed)
        ai_layout.addWidget(self.generated_premise_display)
        
        # Generate button (below premise area)
        self.generate_button = QPushButton("Generate Premise")
        self.generate_button.clicked.connect(self.generate_premise)
        ai_layout.addWidget(self.generate_button)
        
        # Add AI generation widget to profile section
        profile_layout.addWidget(ai_tab)
        
        layout.addLayout(profile_layout)
        
        # Enable spell checking for editable text widgets
        enable_spell_checking(self.title_input)
        enable_spell_checking(self.generated_premise_display)
        
        # Tab key moves focus (not indentation) in form-style fields
        for w in (self.title_input, self.brand_name_input, self.product_name_input,
                  self.product_description_input, self.core_benefit_input, self.target_audience_input,
                  self.brand_personality_input, self.mandatory_elements_input, self.generated_premise_display):
            w.setTabChangesFocus(True)
        
        # Initialize UI based on current profile
        self.update_ui_for_profile()
    
    def set_length_intent(self, length: str, intent: str):
        """Set length and intent from Step 1. Call before showing this step."""
        self._length = length
        self._intent = intent
        self.update_ui_for_profile()
    
    def _update_character_count_hint(self, value: int):
        """Update the character count hint label when spinbox changes."""
        if value <= 0:
            self.character_count_hint.setText("No main characters will be generated.")
        else:
            self.character_count_hint.setText(
                f"The AI will create the protagonist, companions, and antagonist "
                f"— up to {value} main character{'s' if value != 1 else ''}. "
                f"Minor characters may appear later during scene generation."
            )
    
    def update_ui_for_profile(self):
        """Update UI elements based on current workflow profile (length/intent from Step 1)."""
        length = self._length
        intent = self._intent
        
        # Get workflow profile
        profile = WorkflowProfileManager.get_profile(length, intent)
        ui_config = WorkflowProfileManager.get_premise_ui_config(profile, intent)
        
        # Show/hide profile-specific sections
        is_promotional = profile == WorkflowProfile.PROMOTIONAL
        self.narrative_options_widget.setVisible(not is_promotional)
        self.brand_context_group.setVisible(is_promotional)
        
        # Show/hide genre group (hidden for promotional)
        genre_visible = ui_config.get("genre_visible", True)
        self.genre_group.setVisible(genre_visible)
        if genre_visible:
            if ui_config["genre_optional"]:
                self.genre_group.setTitle(f"Select Genres ({ui_config['genre_label']})")
            else:
                self.genre_group.setTitle("Select Genres")
        
        # Update atmosphere label
        self.atmosphere_label.setText(f"{ui_config['atmosphere_label']}:")
        
        # Update character count
        self.character_count_spinbox.setMinimum(0 if ui_config["character_count_optional"] else 2)
        self.character_count_spinbox.setMaximum(ui_config["character_count_max"])
        self.character_count_spinbox.setValue(ui_config["character_count_default"])
        self._update_character_count_hint(self.character_count_spinbox.value())
        
        if profile == WorkflowProfile.PROMOTIONAL:
            self.character_count_label.setText("Number of Main Characters (Optional):")
            self.character_count_spinbox.setToolTip(
                "Number of main characters (0-2 for promotional content).\n"
                "Set to 0 if no characters are needed."
            )
            self.generated_premise_display.setPlaceholderText(
                "Enter your brand concept, or leave empty and click Generate Premise below..."
            )
        elif profile == WorkflowProfile.EXPERIMENTAL:
            self.character_count_label.setText("Number of Characters (Optional):")
            self.character_count_spinbox.setToolTip(
                "Characters are optional visual elements in abstract/art content.\n"
                "Set to 0 for purely visual pieces with no characters."
            )
            self.generated_premise_display.setPlaceholderText(
                "Enter your visual concept, or leave empty and click Generate Premise below..."
            )
        else:
            self.character_count_label.setText("Number of Main Characters:")
            self.character_count_spinbox.setToolTip(
                "The expanded premise will introduce exactly this many main characters by name (protagonist first).\n"
                "Main characters get a full outline and growth arc and must be mentioned FIRST in the expanded storyline.\n"
                "They are used in Character Details and must NOT be replaced by other characters.\n"
                "Additional minor characters may appear in the storyline by name only (no outline/arc).\n"
                "2-3: Simple stories with focused character development\n"
                "4-6: Balanced stories with multiple perspectives\n"
                "7-10: Complex ensemble stories with rich character interactions"
            )
            self.generated_premise_display.setPlaceholderText(
                "Enter your story premise, or leave empty and click Generate Premise below..."
            )
    
    def on_premise_changed(self):
        """Handle premise text change."""
        self.premise_ready.emit()
    
    def get_workflow_profile(self) -> WorkflowProfile:
        """Get current workflow profile."""
        return WorkflowProfileManager.get_profile(self._length, self._intent)
    
    def generate_premise(self):
        """Generate a premise using AI."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.")
            return
        
        # Get selected genres
        selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
        
        # Get workflow profile
        profile = self.get_workflow_profile()
        ui_config = WorkflowProfileManager.get_premise_ui_config(profile, self._intent)
        
        # Validate brand context for promotional workflows
        if profile == WorkflowProfile.PROMOTIONAL:
            product_description = self.product_description_input.toPlainText().strip()
            core_benefit = self.core_benefit_input.toPlainText().strip()
            
            if not product_description:
                QMessageBox.warning(self, "Missing Information", "Please provide a product description for promotional content.")
                return
            
            if not core_benefit:
                QMessageBox.warning(self, "Missing Information", "Please provide the core benefit or promise for promotional content.")
                return
        
        # Genre is optional for promotional content
        if not ui_config["genre_optional"] and not selected_genres:
            QMessageBox.warning(self, "No Genres Selected", "Please select at least one genre.")
            return
        
        atmosphere = self.atmosphere_combo.currentText()
        
        # Use default genres for promotional if none selected
        if not selected_genres and ui_config["genre_optional"]:
            selected_genres = ["Documentary", "Lifestyle"]
        
        # Get brand context for promotional workflows
        brand_context = None
        if profile == WorkflowProfile.PROMOTIONAL:
            from core.screenplay_engine import BrandContext
            
            # Parse brand personality (comma-separated)
            personality_text = self.brand_personality_input.toPlainText().strip()
            brand_personality = [p.strip() for p in personality_text.split(",") if p.strip()] if personality_text else []
            
            # Parse mandatory elements (comma-separated)
            mandatory_text = self.mandatory_elements_input.toPlainText().strip()
            mandatory_elements = [e.strip() for e in mandatory_text.split(",") if e.strip()] if mandatory_text else []
            
            # Get emotional anchor and distribution platform
            emotional_anchor = self.emotional_anchor_combo.currentData() or ""
            distribution_platform = self.distribution_platform_combo.currentData() or ""
            
            brand_context = BrandContext(
                brand_name=self.brand_name_input.toPlainText().strip(),
                product_name=self.product_name_input.toPlainText().strip(),
                product_description=self.product_description_input.toPlainText().strip(),
                core_benefit=self.core_benefit_input.toPlainText().strip(),
                target_audience=self.target_audience_input.toPlainText().strip(),
                brand_personality=brand_personality,
                mandatory_elements=mandatory_elements,
                emotional_anchor=emotional_anchor,
                distribution_platform=distribution_platform,
            )
        
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
        
        # Create and start generation thread with workflow profile and brand context
        self.premise_thread = PremiseGenerationThread(
            self.ai_generator, 
            selected_genres, 
            atmosphere,
            workflow_profile=profile,
            brand_context=brand_context
        )
        self.premise_thread.finished.connect(self.on_premise_generated)
        self.premise_thread.error.connect(self.on_premise_error)
        self.premise_thread.start()
    
    def on_premise_generated(self, premise: str):
        """Handle successful premise generation."""
        # Close progress dialog
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
        self.generated_premise_display.setPlainText(premise.strip())
        self.generate_button.setText("Generate Premise")
        self.generate_button.setEnabled(True)
        
        self.on_premise_changed()
    
    def on_premise_error(self, error_message: str):
        """Handle premise generation error."""
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate premise:\n{error_message}")
        self.generate_button.setText("Generate Premise")
        self.generate_button.setEnabled(True)
        
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def is_valid(self) -> bool:
        """Check if premise step is valid."""
        # Only AI generation is available now
        premise = self.generated_premise_display.toPlainText().strip()
        return bool(premise)
    
    def get_premise_data(self) -> Dict:
        """Get premise data from this step."""
        title = self.title_input.toPlainText().strip()
        
        # Only AI generation is available now
        premise_raw = self.generated_premise_display.toPlainText().strip()
        
        # Extract premise from RAW AI OUTPUT -> CONTENT FIELD section
        # This ensures we get the complete, untruncated premise from the AI
        premise = premise_raw
        if premise_raw:
            # Strategy 1: Look for RAW AI OUTPUT section and extract from CONTENT FIELD
            if "=== RAW AI OUTPUT ===" in premise_raw and "CONTENT FIELD:" in premise_raw:
                # Extract the RAW AI OUTPUT section
                raw_section_match = re.search(
                    r"===\s*RAW\s+AI\s+OUTPUT\s*===\s*(.+?)(?:===\s*PROCESSED\s+PREMISE\s*===|$)",
                    premise_raw,
                    re.DOTALL | re.IGNORECASE
                )
                if raw_section_match:
                    raw_section = raw_section_match.group(1)
                    # Now extract from CONTENT FIELD to FINISH REASON within this section
                    content_match = re.search(
                        r"CONTENT\s+FIELD\s*:\s*(.+?)(?:REASONING\s+FIELD|FINISH\s+REASON|$)",
                        raw_section,
                        re.DOTALL | re.IGNORECASE
                    )
                    if content_match:
                        content = content_match.group(1).strip()
                        # Extract everything after "FINAL PREMISE:" from content
                        premise_match = re.search(
                            r"FINAL\s+PREMISE\s*:?\s*(.+)$",
                            content,
                            re.DOTALL | re.IGNORECASE
                        )
                        if premise_match:
                            premise = premise_match.group(1).strip()
            
            # Strategy 2: If RAW AI OUTPUT approach didn't work, try PROCESSED PREMISE section
            # BUT don't split on "===" which truncates content
            if premise == premise_raw and "=== PROCESSED PREMISE ===" in premise_raw:
                parts = premise_raw.split("=== PROCESSED PREMISE ===", 1)
                if len(parts) > 1:
                    premise = parts[1].strip()
            
            # Strategy 3: Simple extraction if no sections found
            elif premise == premise_raw:
                # Look for FINAL PREMISE marker anywhere in the text
                premise_match = re.search(
                    r"FINAL\s+PREMISE\s*:?\s*(.+)$",
                    premise_raw,
                    re.DOTALL | re.IGNORECASE
                )
                if premise_match:
                    premise = premise_match.group(1).strip()
            
            # Clean up any remaining markers from the extracted premise
            # Remove standalone marker lines but keep actual content
            lines = premise.split('\n')
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip section markers
                if stripped.startswith("===") and stripped.endswith("==="):
                    continue
                if stripped.startswith("CONTENT FIELD:") or stripped.startswith("FINISH REASON:"):
                    continue
                if stripped.startswith("REASONING FIELD:") or stripped.startswith("FULL RESPONSE:"):
                    continue
                cleaned_lines.append(line)
            premise = '\n'.join(cleaned_lines).strip()
        
        selected_genres = [cb.text() for cb in self.genre_checkboxes if cb.isChecked()]
        genres = selected_genres
        atmosphere = self.atmosphere_combo.currentText()
        character_count = self.character_count_spinbox.value()
        
        # Get brand context if promotional
        brand_context = None
        profile = self.get_workflow_profile()
        if profile == WorkflowProfile.PROMOTIONAL:
            from core.screenplay_engine import BrandContext
            
            # Parse brand personality (comma-separated)
            personality_text = self.brand_personality_input.toPlainText().strip()
            brand_personality = [p.strip() for p in personality_text.split(",") if p.strip()] if personality_text else []
            
            # Parse mandatory elements (comma-separated)
            mandatory_text = self.mandatory_elements_input.toPlainText().strip()
            mandatory_elements = [e.strip() for e in mandatory_text.split(",") if e.strip()] if mandatory_text else []
            
            # Get emotional anchor and distribution platform
            emotional_anchor = self.emotional_anchor_combo.currentData() or ""
            distribution_platform = self.distribution_platform_combo.currentData() or ""
            
            brand_context = BrandContext(
                brand_name=self.brand_name_input.toPlainText().strip(),
                product_name=self.product_name_input.toPlainText().strip(),
                product_description=self.product_description_input.toPlainText().strip(),
                core_benefit=self.core_benefit_input.toPlainText().strip(),
                target_audience=self.target_audience_input.toPlainText().strip(),
                brand_personality=brand_personality,
                mandatory_elements=mandatory_elements,
                emotional_anchor=emotional_anchor,
                distribution_platform=distribution_platform,
            )
        
        return {
            "premise": premise,
            "title": title,
            "genres": genres,
            "atmosphere": atmosphere,
            "length": self._length,
            "character_count": character_count,
            "intent": self._intent,
            "brand_context": brand_context
        }

