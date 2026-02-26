"""
Story Creation Wizard for MoviePrompterAI.
Guides users through premise creation, story outline, and framework generation.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QMessageBox, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Optional, Dict, Any, List
from core.ai_generator import AIGenerator
from core.screenplay_engine import Screenplay
from core.workflow_profile import WorkflowProfileManager, WorkflowProfile

from .wizard_steps.length_intent_step import LengthIntentStepWidget
from .wizard_steps.premise_step import PremiseStepWidget
from .wizard_steps.story_outline_step import StoryOutlineStepWidget
from .wizard_steps.framework_generation_step import FrameworkGenerationStepWidget


class StoryCreationWizard(QDialog):
    """Multi-step wizard for creating a new screenplay."""
    
    wizard_completed = pyqtSignal(Screenplay)  # Emits completed screenplay with framework
    
    def __init__(self, parent=None, ai_generator: Optional[AIGenerator] = None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.current_step = 0
        self.total_steps = 4
        
        # Wizard state
        self.premise: str = ""
        self.title: str = ""
        self.genres: List[str] = []
        self.atmosphere: str = ""
        self.length: str = "medium"  # Story length: micro, short, medium, or long
        self.intent: str = "General Story"  # Story intent (Advertisement, Horror Short, etc.)
        self.story_outline: Dict[str, Any] = {}
        self.brand_context = None  # BrandContext for promotional workflows
        self.generated_screenplay: Optional[Screenplay] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the wizard UI."""
        self.setWindowTitle("Story Creation Wizard")
        self.setModal(True)
        
        # Get available screen geometry (excludes taskbar) for bounds checking
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        
        # Use parent (main window) size for wizard dimensions
        if self.parent():
            # Use frame geometry to account for window borders and title bar
            parent_geom = self.parent().frameGeometry()
            parent_width = max(1, parent_geom.width())
            parent_height = max(1, parent_geom.height())
            parent_x = parent_geom.x()
            parent_y = parent_geom.y()
            # Prefer the screen the parent is on
            parent_screen = self.parent().windowHandle().screen() if self.parent().windowHandle() else None
            if parent_screen:
                screen = parent_screen.availableGeometry()
        else:
            parent_width = max(1, screen.width())
            parent_height = max(1, screen.height())
            parent_x = screen.x()
            parent_y = screen.y()
        
        # Compute max wizard size: match parent (main window) height
        max_width = max(300, parent_width - 160)
        max_height = max(300, parent_height)
        
        # Target size: match main window vertical size; width ~65% of parent
        initial_width = min(int(parent_width * 0.65), max_width, 560)
        initial_height = parent_height  # Match main window height
        
        # Clamp to minimums without exceeding parent bounds
        initial_width = min(max_width, max(480, initial_width))
        initial_height = min(max_height, max(260, initial_height))
        
        # Ensure it fits on screen with margins
        initial_width = min(initial_width, max(300, screen.width() - 40))
        initial_height = min(initial_height, max(300, screen.height() - 60))
        
        # Store full size for steps 2-4; Step 1 uses compact size
        self._full_width = initial_width
        self._full_height = initial_height
        
        # Set minimum size and allow resizing for scrolling
        self.setMinimumSize(initial_width, initial_height)
        self.resize(initial_width, initial_height)
        
        # Center window on parent horizontally, align to top of available screen vertically
        x = parent_x + (parent_width - initial_width) // 2
        y = screen.y()
        
        # Ensure window stays fully within screen bounds
        x = max(screen.x(), min(x, screen.x() + screen.width() - initial_width))
        y = max(screen.y(), min(y, screen.y() + screen.height() - initial_height))
        self.move(x, y)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # Progress indicator
        progress_label = QLabel(f"Step {self.current_step + 1} of {self.total_steps}")
        progress_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        progress_label.setMaximumHeight(30)
        layout.addWidget(progress_label)
        self.progress_label = progress_label
        
        # Content switcher: Step 1 shows length_intent directly (no scroll); Steps 2-4 use scroll area
        from PyQt6.QtWidgets import QSizePolicy
        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred))
        
        # Page 0: Step 1 - length/intent only, no scroll area
        self.length_intent_step = LengthIntentStepWidget(self.ai_generator)
        self.content_stack.addWidget(self.length_intent_step)
        
        # Page 1: Steps 2-4 - scroll area with premise, outline, framework
        self.stacked_widget = QStackedWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setWidget(self.stacked_widget)
        self.content_stack.addWidget(self.scroll_area)
        
        self.premise_step = PremiseStepWidget(self.ai_generator)
        self.premise_step.premise_ready.connect(self.on_premise_ready)
        self.stacked_widget.addWidget(self.premise_step)
        
        self.outline_step = StoryOutlineStepWidget(self.ai_generator)
        self.outline_step.outline_ready.connect(self.on_outline_ready)
        self.stacked_widget.addWidget(self.outline_step)
        
        self.framework_step = FrameworkGenerationStepWidget(self.ai_generator)
        self.framework_step.framework_ready.connect(self.on_framework_ready)
        self.stacked_widget.addWidget(self.framework_step)
        
        layout.addWidget(self.content_stack, 1)
        
        # Navigation buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)
        button_layout.addWidget(self.back_button)
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_next)
        self.next_button.setDefault(True)
        button_layout.addWidget(self.next_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.finish_button = QPushButton("Finish")
        self.finish_button.clicked.connect(self.finish_wizard)
        self.finish_button.setEnabled(False)
        self.finish_button.hide()
        button_layout.addWidget(self.finish_button)
        
        layout.addLayout(button_layout)
        
        # Update UI for first step
        self._show_step(0)
        self._resize_for_step(0)
        self.update_navigation()
    
    def _show_step(self, step_index: int):
        """Show the widget for the given step (0=length/intent, 1=premise, 2=outline, 3=framework)."""
        if step_index == 0:
            self.content_stack.setCurrentIndex(0)
        else:
            self.content_stack.setCurrentIndex(1)
            self.stacked_widget.setCurrentIndex(step_index - 1)
    
    def _resize_for_step(self, step_index: int):
        """Resize wizard window: compact for Step 1, full size for Steps 2-4."""
        if step_index == 0:
            self.setMinimumSize(420, 180)
            self.resize(540, 260)
        else:
            self.setMinimumSize(self._full_width, self._full_height)
            self.resize(self._full_width, self._full_height)
    
    def update_navigation(self):
        """Update navigation buttons based on current step."""
        self.progress_label.setText(f"Step {self.current_step + 1} of {self.total_steps}")
        
        # Back button
        self.back_button.setEnabled(self.current_step > 0)
        
        # Next/Finish buttons
        if self.current_step == self.total_steps - 1:
            # Last step
            self.next_button.hide()
            self.finish_button.show()
            self.finish_button.setEnabled(self.generated_screenplay is not None)
        else:
            # Not last step
            self.next_button.show()
            self.finish_button.hide()
            # Enable Next based on step validation
            self.next_button.setEnabled(self.validate_current_step())
    
    def validate_current_step(self) -> bool:
        """Validate the current step before allowing progression."""
        if self.current_step == 0:
            # Length/intent step
            return self.length_intent_step.is_valid()
        elif self.current_step == 1:
            # Premise step
            return self.premise_step.is_valid()
        elif self.current_step == 2:
            # Outline step - check if required
            if hasattr(self, 'length') and hasattr(self, 'intent'):
                workflow_profile = WorkflowProfileManager.get_profile(self.length, self.intent)
                if not WorkflowProfileManager.requires_story_outline(workflow_profile):
                    return True
            return self.outline_step.is_valid()
        elif self.current_step == 3:
            # Framework step
            return self.generated_screenplay is not None
        return False
    
    def go_back(self):
        """Navigate to previous step."""
        if self.current_step > 0:
            # When leaving outline step (step 3), push edited premise into premise step
            if self.current_step == 2:
                edited_premise = self.outline_step.premise_text.toPlainText().strip()
                if edited_premise:
                    self.premise = edited_premise
                    self.premise_step.generated_premise_display.setPlainText(edited_premise)
            self.current_step -= 1
            self._show_step(self.current_step)
            self._resize_for_step(self.current_step)
            self.update_navigation()
    
    def go_next(self):
        """Navigate to next step."""
        if not self.validate_current_step():
            QMessageBox.warning(self, "Validation Error", "Please complete the current step before proceeding.")
            return
        
        if self.current_step == 0:
            # Moving from length/intent to premise
            self.length = self.length_intent_step.get_length()
            self.intent = self.length_intent_step.get_intent()
            self.premise_step.set_length_intent(self.length, self.intent)
        
        elif self.current_step == 1:
            # Moving from premise to outline
            premise_data = self.premise_step.get_premise_data()
            self.premise = premise_data["premise"]
            self.title = premise_data["title"]
            self.genres = premise_data["genres"]
            self.atmosphere = premise_data["atmosphere"]
            self.length = premise_data.get("length", "medium")
            self.intent = premise_data.get("intent", "General Story")
            self.character_count = premise_data.get("character_count", 4)
            self.brand_context = premise_data.get("brand_context")
            
            workflow_profile = WorkflowProfileManager.get_profile(self.length, self.intent)
            
            if WorkflowProfileManager.requires_story_outline(workflow_profile):
                self.outline_step.set_premise(
                    self.premise,
                    self.title,
                    self.genres,
                    self.atmosphere,
                    self.character_count,
                    self.length,
                    self.intent
                )
            else:
                self.story_outline = {}
                self.current_step = 3
                self._show_step(3)
                self._resize_for_step(3)
                self.framework_step.start_generation(
                    self.premise, self.title, self.genres, self.atmosphere, self.story_outline, self.length, self.intent, self.brand_context
                )
                self.update_navigation()
                return
        
        elif self.current_step == 2:
            # Moving from outline to framework generation
            self._proceed_from_outline_to_framework()
            return
        
        self.current_step += 1
        self._show_step(self.current_step)
        self._resize_for_step(self.current_step)
        self.update_navigation()
    
    def _proceed_from_outline_to_framework(self):
        """Complete transition from outline step to framework generation. Generates missing physical appearances first if needed."""
        # Use outline's (possibly edited) premise
        edited_premise = self.outline_step.premise_text.toPlainText().strip()
        if edited_premise:
            self.premise = edited_premise
            self.premise_step.generated_premise_display.setPlainText(edited_premise)
        # Get outline data (syncs UI to outline_data)
        self.story_outline = self.outline_step.get_outline_data()

        def do_transition():
            # Re-fetch outline data (may have been updated by batch physical generation)
            self.story_outline = self.outline_step.get_outline_data()
            self.framework_step.start_generation(
                self.premise, self.title, self.genres, self.atmosphere,
                self.story_outline, self.length, self.intent, self.brand_context
            )
            self.current_step += 1
            self._show_step(self.current_step)
            self._resize_for_step(self.current_step)
            self.update_navigation()

        # If any characters are missing physical appearance, generate them first
        if self.outline_step.has_characters_missing_physical_appearance():
            self.outline_step.ensure_missing_physical_appearances(
                on_done=do_transition,
                on_error=lambda msg: QMessageBox.critical(
                    self, "Error",
                    f"Failed to generate character physical appearances:\n{msg}"
                )
            )
        else:
            do_transition()

    def on_premise_ready(self):
        """Handle premise step completion."""
        self.update_navigation()
    
    def on_outline_ready(self):
        """Handle outline step completion."""
        self.update_navigation()
    
    def on_framework_ready(self, screenplay: Screenplay):
        """Handle framework generation completion."""
        import re as _re

        self.generated_screenplay = screenplay
        # Store story outline in screenplay
        screenplay.story_outline = self.story_outline
        # Build and freeze Character Registry: single source of truth for characters.
        # Sanitize: remove corporations (e.g. NEUROTECH), merge surname-only duplicates (e.g. MAYFIELD → LUCILLE MAYFIELD).
        chars = screenplay.story_outline.get("characters", [])
        if self.ai_generator and chars:
            chars = self.ai_generator.sanitize_character_list_for_registry(chars)
            screenplay.story_outline["characters"] = chars
        # Tag all wizard-generated characters as main if not already tagged
        for c in chars:
            if isinstance(c, dict) and "role" not in c:
                c["role"] = "main"
        main_names_lower = {
            c["name"].lower() for c in chars
            if isinstance(c, dict) and c.get("name")
        }
        registry_names = [c["name"] for c in chars if isinstance(c, dict) and c.get("name")]
        # Add characters from scene character_focus that aren't in outline (e.g. AI AEON in body-swap stories)
        registry_lower = {n.lower() for n in registry_names}
        for act in (screenplay.acts or []):
            for scene in (act.scenes or []):
                for cf in (scene.character_focus or []):
                    name = (cf or "").strip()
                    if name and name.lower() not in registry_lower:
                        registry_names.append(name)
                        registry_lower.add(name.lower())

        # --- Extract minor characters from storyline + scene descriptions ---
        # Characters mentioned in FULL CAPS in the expanded storyline or scene
        # descriptions that are not already main characters get added as minor
        # characters with physical appearance only.
        minor_names_found = []
        if self.ai_generator:
            # Combine storyline text and scene descriptions into one block
            storyline_text_parts = []
            for key in ("main_storyline", "subplots", "conclusion"):
                val = self.story_outline.get(key, "") or ""
                if val.strip():
                    storyline_text_parts.append(val)
            for act in (screenplay.acts or []):
                for scene in (act.scenes or []):
                    if scene.description:
                        storyline_text_parts.append(scene.description)
            combined_text = "\n".join(storyline_text_parts)
            if combined_text.strip():
                all_caps_names = self.ai_generator._extract_first_n_characters_from_main_storyline(
                    combined_text, 100
                )
                for cap_name in all_caps_names:
                    cap_lower = cap_name.lower()
                    if cap_lower not in registry_lower and cap_lower not in main_names_lower:
                        minor_names_found.append(cap_name)
                        registry_names.append(cap_name)
                        registry_lower.add(cap_lower)

        # --- Clean registry names before freezing ---
        # 1. Strip leading articles ("A filmmaker" → "filmmaker")
        def _strip_leading_article(n: str) -> str:
            return _re.sub(r"^(?:A|An|The)\s+", "", n.strip(), flags=_re.IGNORECASE).strip() or n.strip()

        registry_names = [_strip_leading_article(n) for n in registry_names]

        # 2. Fold body-part entries ("filmmaker's hands" → "filmmaker")
        #    and drop non-person entities (interfaces, sequences, logos, etc.)
        cleaned = []
        cleaned_lower = set()
        body_part_method = getattr(AIGenerator, '_split_possessive_body_part', None)
        concept_filter = self.ai_generator._is_company_or_concept_entity if self.ai_generator else None
        for name in registry_names:
            # Body-part fold: extract owner from "X's hands"
            parts = body_part_method(name) if body_part_method else None
            if parts:
                name = _strip_leading_article(parts[0])

            # Filter non-person entities (software UI, abstract visuals, etc.)
            if concept_filter and concept_filter(name):
                continue

            if name.lower() not in cleaned_lower:
                # Check for confusing word overlap with already-accepted names
                name_words = set(name.upper().split())
                is_overlap = False
                if len(name_words) >= 2:
                    for accepted in cleaned:
                        accepted_words = set(accepted.upper().split())
                        if len(name_words & accepted_words) >= 2 and name.upper() != accepted.upper():
                            print(f"  [registry guard] Skipping '{name}' — overlaps with '{accepted}'")
                            is_overlap = True
                            break
                if not is_overlap:
                    cleaned.append(name)
                    cleaned_lower.add(name.lower())

        screenplay.character_registry = list(dict.fromkeys(cleaned))  # preserve order, dedupe
        screenplay.character_registry_frozen = True
        # Store length and intent for Premise tab / workflow profile
        screenplay.story_length = self.length
        screenplay.intent = self.intent
        # Store brand context in screenplay
        if self.brand_context:
            screenplay.brand_context = self.brand_context

        # --- Add minor characters to story_outline and generate physical appearance ---
        if minor_names_found and self.ai_generator:
            existing_chars = screenplay.story_outline.get("characters", [])
            existing_lower = {
                c.get("name", "").lower() for c in existing_chars if isinstance(c, dict)
            }
            storyline_text = self.story_outline.get("main_storyline", "") or ""
            for raw_name in minor_names_found:
                display_name = _strip_leading_article(raw_name).strip()
                if not display_name or len(display_name) < 3 or display_name.lower() in existing_lower:
                    continue
                phys = ""
                try:
                    result = self.ai_generator.regenerate_character_details(
                        premise=self.premise,
                        genres=self.genres,
                        atmosphere=self.atmosphere,
                        title=self.title,
                        main_storyline=storyline_text,
                        character_name=display_name,
                        regenerate_type="physical_appearance",
                        existing_characters=existing_chars,
                    )
                    phys = (result.get("physical_appearance", "") or "").strip()
                except Exception as e:
                    print(f"  Warning: could not generate appearance for minor character {display_name}: {e}")
                from core.ai_generator import infer_species_from_text
                char_context = ""
                for seg in storyline_text.split(". "):
                    if display_name.upper() in seg.upper():
                        char_context += seg + ". "
                minor_species = infer_species_from_text("", phys, char_context, display_name)
                existing_chars.append({
                    "name": display_name,
                    "role": "minor",
                    "species": minor_species,
                    "outline": "",
                    "growth_arc": "",
                    "physical_appearance": phys,
                })
                existing_lower.add(display_name.lower())
            screenplay.story_outline["characters"] = existing_chars

        self.update_navigation()
    
    def finish_wizard(self):
        """Complete the wizard and emit the screenplay."""
        if not self.generated_screenplay:
            QMessageBox.warning(self, "Incomplete", "Framework generation is not complete.")
            return
        
        self.wizard_completed.emit(self.generated_screenplay)
        self.accept()

