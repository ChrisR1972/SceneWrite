"""
Step 1: Story Length and Intent selection for the Story Creation Wizard.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox
)
from PyQt6.QtCore import pyqtSignal
from typing import Optional
from core.ai_generator import AIGenerator


class LengthIntentStepWidget(QWidget):
    """Step 1: Select story length and intent."""
    
    def __init__(self, ai_generator: Optional[AIGenerator] = None, parent=None):
        super().__init__(parent)
        self.ai_generator = ai_generator
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        from PyQt6.QtWidgets import QSizePolicy
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(size_policy)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        
        title_label = QLabel("Step 1: Select Story Length and Intent")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 0; padding: 0;")
        layout.addWidget(title_label)
        
        description = QLabel(
            "Choose the length and intent of your story. These choices determine which options appear in the next step."
        )
        description.setWordWrap(True)
        description.setStyleSheet("margin: 0; padding: 0;")
        layout.addWidget(description)
        
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Story Length:"))
        self.length_combo = QComboBox()
        self.length_combo.addItems([
            "Micro (1 act, 1-5 scenes)",
            "Short (3 acts, 9-15 scenes)",
            "Medium (3 acts, 15-24 scenes)",
            "Long (5 acts, 30-50 scenes)",
            "Custom (specify duration)"
        ])
        self.length_combo.setCurrentIndex(2)
        self.length_combo.setToolTip(
            "Micro: Atomic storytelling for ads, loops, single-scene narratives\n"
            "Short: Fast-paced, concise stories\n"
            "Medium: Balanced pacing with room for development\n"
            "Long: Epic stories with extensive character development and subplots\n"
            "Custom: Specify a target total duration; the AI determines the structure"
        )
        self.length_combo.currentIndexChanged.connect(self._on_length_changed)
        length_layout.addWidget(self.length_combo)
        length_layout.addStretch()
        layout.addLayout(length_layout)
        
        # Custom duration input (hidden by default)
        self.custom_duration_widget = QWidget()
        custom_layout = QHBoxLayout(self.custom_duration_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)
        custom_layout.addWidget(QLabel("Duration:"))
        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(0, 30)
        self.minutes_spin.setValue(2)
        self.minutes_spin.setSuffix(" min")
        custom_layout.addWidget(self.minutes_spin)
        self.seconds_spin = QSpinBox()
        self.seconds_spin.setRange(0, 59)
        self.seconds_spin.setValue(0)
        self.seconds_spin.setSuffix(" sec")
        custom_layout.addWidget(self.seconds_spin)
        custom_layout.addStretch()
        layout.addWidget(self.custom_duration_widget)
        
        self.custom_help_label = QLabel(
            "The AI will determine the act/scene structure to fit your target duration."
        )
        self.custom_help_label.setWordWrap(True)
        self.custom_help_label.setStyleSheet("color: #888; font-style: italic; margin: 0; padding: 0;")
        layout.addWidget(self.custom_help_label)
        
        self.custom_duration_widget.setVisible(False)
        self.custom_help_label.setVisible(False)
        
        intent_layout = QHBoxLayout()
        intent_layout.addWidget(QLabel("Story Intent:"))
        self.intent_combo = QComboBox()
        self.intent_combo.addItems([
            "General Story",
            "Advertisement / Brand Film",
            "Social Media / Short-form",
            "Visual Art / Abstract"
        ])
        self.intent_combo.setCurrentIndex(0)
        self.intent_combo.setToolTip(
            "Story Intent affects scene density, dialogue frequency, camera motion, and prompt style.\n"
            "General Story: Balanced approach for most narratives\n"
            "Advertisement / Brand Film: High visual impact, brand-focused, minimal dialogue\n"
            "Social Media / Short-form: Hook-first, punchy pacing, platform-optimised\n"
            "Visual Art / Abstract: Non-linear, artistic, mood-driven"
        )
        intent_layout.addWidget(self.intent_combo)
        intent_layout.addStretch()
        layout.addLayout(intent_layout)
    
    def _on_length_changed(self, index: int):
        """Show/hide custom duration inputs based on selection."""
        is_custom = (index == 4)
        self.custom_duration_widget.setVisible(is_custom)
        self.custom_help_label.setVisible(is_custom)
    
    def is_valid(self) -> bool:
        """Step is valid for presets; for custom, require duration >= 15 seconds."""
        if self.length_combo.currentIndex() == 4:
            return self.get_custom_duration_seconds() >= 15
        return True
    
    def get_length(self) -> str:
        """Get story length: micro, short, medium, long, or custom."""
        length_map = {0: "micro", 1: "short", 2: "medium", 3: "long", 4: "custom"}
        return length_map.get(self.length_combo.currentIndex(), "medium")
    
    def get_custom_duration_seconds(self) -> int:
        """Return the user-specified duration in seconds, or 0 if not custom."""
        if self.length_combo.currentIndex() != 4:
            return 0
        return self.minutes_spin.value() * 60 + self.seconds_spin.value()
    
    def set_custom_duration(self, total_seconds: int):
        """Pre-fill the custom duration fields and select the Custom option."""
        self.length_combo.setCurrentIndex(4)
        self.minutes_spin.setValue(total_seconds // 60)
        self.seconds_spin.setValue(total_seconds % 60)
    
    def get_intent(self) -> str:
        """Get story intent."""
        return self.intent_combo.currentText()
