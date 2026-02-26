"""
Step 1: Story Length and Intent selection for the Story Creation Wizard.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
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
            "Long (5 acts, 30-50 scenes)"
        ])
        self.length_combo.setCurrentIndex(2)
        self.length_combo.setToolTip(
            "Micro: Atomic storytelling for ads, loops, single-scene narratives\n"
            "Short: Fast-paced, concise stories\n"
            "Medium: Balanced pacing with room for development\n"
            "Long: Epic stories with extensive character development and subplots"
        )
        length_layout.addWidget(self.length_combo)
        length_layout.addStretch()
        layout.addLayout(length_layout)
        
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
    
    def is_valid(self) -> bool:
        """Step is always valid - user has made selections."""
        return True
    
    def get_length(self) -> str:
        """Get story length: micro, short, medium, or long."""
        length_map = {0: "micro", 1: "short", 2: "medium", 3: "long"}
        return length_map.get(self.length_combo.currentIndex(), "medium")
    
    def get_intent(self) -> str:
        """Get story intent."""
        return self.intent_combo.currentText()
