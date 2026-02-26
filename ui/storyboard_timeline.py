"""
Timeline view widget for displaying storyboard items.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPalette
from typing import Optional, List
from core.screenplay_engine import Screenplay, StoryboardItem

class StoryboardItemCard(QFrame):
    """A card widget representing a single storyboard item."""
    
    clicked = pyqtSignal(str)  # Emits item_id when clicked
    edit_requested = pyqtSignal(str)  # Emits item_id when edit button clicked
    
    def __init__(self, item: StoryboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setMinimumWidth(250)
        self.setMaximumWidth(300)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Header with sequence number and duration
        header_layout = QHBoxLayout()
        sequence_label = QLabel(f"#{self.item.sequence_number}")
        sequence_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header_layout.addWidget(sequence_label)
        
        # Image prompt indicator
        if self.item.image_prompt:
            image_indicator = QLabel("🖼️")
            image_indicator.setToolTip("Has establishing image prompt")
            image_indicator.setStyleSheet("font-size: 14px; padding: 2px;")
            header_layout.addWidget(image_indicator)
        
        # Render cost indicator
        render_cost = getattr(self.item, "render_cost", "unknown")
        if render_cost == "easy":
            cost_indicator = QLabel("🟢")
            cost_indicator.setToolTip("Render Cost: Easy")
        elif render_cost == "moderate":
            cost_indicator = QLabel("🟡")
            cost_indicator.setToolTip("Render Cost: Moderate")
        elif render_cost == "expensive":
            cost_indicator = QLabel("🔴")
            cost_indicator.setToolTip("Render Cost: Expensive")
        else:
            cost_indicator = QLabel("⚪")
            cost_indicator.setToolTip("Render Cost: Unknown")
        cost_indicator.setStyleSheet("font-size: 14px; padding: 2px;")
        header_layout.addWidget(cost_indicator)
        
        # Identity drift warning indicator
        drift_warnings = getattr(self.item, "identity_drift_warnings", [])
        if drift_warnings:
            drift_indicator = QLabel("⚠️")
            drift_indicator.setToolTip(f"Identity Warnings: {len(drift_warnings)} issue(s)\n" + "\n".join(drift_warnings))
            drift_indicator.setStyleSheet("font-size: 14px; padding: 2px; color: #CC6600;")
            header_layout.addWidget(drift_indicator)
        
        header_layout.addStretch()
        
        duration_badge = QLabel(f"{self.item.duration}s")
        duration_badge.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-weight: bold;
        """)
        header_layout.addWidget(duration_badge)
        layout.addLayout(header_layout)
        
        # Scene type label
        scene_type_label = QLabel(self.item.scene_type.value.title())
        scene_type_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(scene_type_label)
        
        # Prompt preview (truncated)
        prompt_text = self.item.prompt or "(No prompt)"
        if len(prompt_text) > 150:
            prompt_text = prompt_text[:150] + "..."
        prompt_preview = QLabel(prompt_text)
        prompt_preview.setWordWrap(True)
        prompt_preview.setStyleSheet("font-size: 11px; padding: 5px;")
        prompt_preview.setMaximumHeight(80)
        layout.addWidget(prompt_preview)
        
        # Visual description preview
        desc_text = self.item.visual_description or "(No description)"
        if len(desc_text) > 100:
            desc_text = desc_text[:100] + "..."
        desc_preview = QLabel(desc_text)
        desc_preview.setWordWrap(True)
        desc_preview.setStyleSheet("font-size: 10px; color: #888; padding: 5px;")
        desc_preview.setMaximumHeight(60)
        layout.addWidget(desc_preview)
        
        # Edit button
        edit_button = QPushButton("Edit")
        edit_button.setMaximumWidth(80)
        edit_button.clicked.connect(lambda: self.edit_requested.emit(self.item.item_id))
        layout.addWidget(edit_button)
        
        layout.addStretch()
    
    def mousePressEvent(self, event):
        """Handle mouse click on card."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item.item_id)
        super().mousePressEvent(event)

class StoryboardTimeline(QWidget):
    """Timeline view widget for storyboard items."""
    
    item_clicked = pyqtSignal(str)  # Emits item_id
    item_edit_requested = pyqtSignal(str)  # Emits item_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenplay: Optional[Screenplay] = None
        self.item_cards: List[StoryboardItemCard] = []
        self.init_ui()
    
    def init_ui(self):
        """Initialize the timeline UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Scroll area for horizontal timeline
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container widget for cards
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(15)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.addStretch()
        
        scroll_area.setWidget(self.cards_container)
        layout.addWidget(scroll_area)
        
        # Summary label
        self.summary_label = QLabel("No storyboard loaded")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(self.summary_label)
    
    def set_screenplay(self, screenplay: Screenplay):
        """Set the screenplay to display."""
        self.screenplay = screenplay
        self.update_display()
    
    def update_display(self):
        """Update the timeline display with current screenplay."""
        # Clear existing cards
        for card in self.item_cards:
            card.setParent(None)
            card.deleteLater()
        self.item_cards.clear()
        
        if not self.screenplay or not self.screenplay.storyboard_items:
            self.summary_label.setText("No storyboard items")
            return
        
        # Create cards for each item
        for item in self.screenplay.storyboard_items:
            card = StoryboardItemCard(item)
            card.clicked.connect(self.item_clicked.emit)
            card.edit_requested.connect(self.item_edit_requested.emit)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)  # Insert before stretch
            self.item_cards.append(card)
        
        # Update summary
        total_duration = self.screenplay.get_total_duration_formatted()
        item_count = len(self.screenplay.storyboard_items)
        avg_dur = sum(item.duration for item in self.screenplay.storyboard_items) / max(item_count, 1)
        self.summary_label.setText(
            f"Total: {item_count} items | Duration: {total_duration} | "
            f"Avg: {avg_dur:.1f}s per item"
        )
    
    def refresh(self):
        """Refresh the display (useful after item edits)."""
        if self.screenplay:
            self.update_display()

