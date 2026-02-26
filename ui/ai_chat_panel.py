"""
AI Chat Panel for discussing story ideas and making changes.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QScrollArea, QMessageBox, QDialog, QDialogButtonBox,
    QGroupBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QTextCursor, QColor, QPalette
from typing import Optional, List, Dict, Any
from core.screenplay_engine import Screenplay, StoryScene, StoryboardItem
from core.ai_generator import AIGenerator


class ChatThread(QThread):
    """Thread for handling AI chat requests in the background."""
    
    response_received = pyqtSignal(dict)  # Emits response dict
    error = pyqtSignal(str)  # Emits error message
    
    def __init__(self, ai_generator: AIGenerator, user_message: str, context: dict):
        super().__init__()
        self.ai_generator = ai_generator
        self.user_message = user_message
        self.context = context
    
    def run(self):
        """Execute chat request in background."""
        try:
            response = self.ai_generator.chat_about_story(self.user_message, self.context)
            self.response_received.emit(response)
        except Exception as e:
            self.error.emit(str(e))


class ChangePreviewDialog(QDialog):
    """Dialog to preview changes before applying them."""
    
    def __init__(self, change_type: str, before_data: Any, after_data: Any, parent=None):
        try:
            super().__init__(parent)
            # Ensure we have valid data
            self.change_type = str(change_type) if change_type else "edit_scene"
            self.before_data = before_data if before_data is not None else "(No data)"
            self.after_data = after_data if after_data is not None else "(No data)"
            self.setWindowTitle("Preview Changes")
            self.setMinimumWidth(900)
            self.setMinimumHeight(600)
            self.init_ui()
        except Exception as e:
            # If initialization fails, try to create a minimal dialog
            try:
                super().__init__(parent)
                self.setWindowTitle("Preview Error")
                layout = QVBoxLayout(self)
                error_label = QLabel(f"Error initializing preview: {str(e)}")
                layout.addWidget(error_label)
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(self.reject)
                layout.addWidget(close_btn)
            except:
                # If even that fails, just raise the original error
                raise
    
    def init_ui(self):
        """Initialize the preview dialog UI."""
        try:
            layout = QVBoxLayout(self)
            
            # Description
            change_type_display = str(self.change_type).replace('_', ' ').title() if self.change_type else "Changes"
            desc_label = QLabel(f"Preview: {change_type_display}")
            desc_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            layout.addWidget(desc_label)
            
            # Before/After comparison
            comparison_layout = QHBoxLayout()
            
            # Before column
            before_group = QGroupBox("Before")
            before_layout = QVBoxLayout()
            before_text = QTextEdit()
            before_text.setReadOnly(True)
            before_text.setFont(QFont("Arial", 10))
            try:
                before_content = self._format_data(self.before_data)
                before_text.setPlainText(before_content if before_content else "(No content)")
            except Exception as e:
                before_text.setPlainText(f"(Error loading before data: {str(e)})")
            before_layout.addWidget(before_text)
            before_group.setLayout(before_layout)
            comparison_layout.addWidget(before_group)
            
            # After column
            after_group = QGroupBox("After (Suggested Changes)")
            after_layout = QVBoxLayout()
            after_text = QTextEdit()
            after_text.setReadOnly(True)
            after_text.setFont(QFont("Arial", 10))
            try:
                after_content = self._format_data(self.after_data)
                after_text.setPlainText(after_content if after_content else "(No content)")
            except Exception as e:
                after_text.setPlainText(f"(Error loading after data: {str(e)})")
            after_layout.addWidget(after_text)
            after_group.setLayout(after_layout)
            comparison_layout.addWidget(after_group)
            
            layout.addLayout(comparison_layout)
            
            # Info label
            info_label = QLabel("Review the changes above. Click 'Apply Changes' to accept or 'Cancel' to dismiss.")
            info_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
            layout.addWidget(info_label)
            
            # Buttons
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
            )
            apply_button = button_box.button(QDialogButtonBox.StandardButton.Apply)
            if apply_button:
                apply_button.setText("Apply Changes")
                # Apply button doesn't emit accepted signal in PyQt6 - connect its clicked signal directly
                apply_button.clicked.connect(self.accept)
            button_box.rejected.connect(self.reject)
            layout.addWidget(button_box)
        except Exception as e:
            # If UI initialization fails, show error in a simple dialog
            try:
                import traceback
                error_msg = f"Failed to initialize preview dialog: {str(e)}\n\n{traceback.format_exc()[:500]}"
                # Try to show message box, but if that fails, just create minimal UI
                try:
                    if hasattr(self, 'parent') and self.parent():
                        QMessageBox.critical(self.parent(), "Preview Error", error_msg)
                    else:
                        QMessageBox.critical(None, "Preview Error", error_msg)
                except:
                    pass  # If QMessageBox fails, continue with minimal UI
                
                # Still create a minimal dialog so it can be closed
                # Clear any existing layout first
                try:
                    existing_layout = self.layout()
                    if existing_layout:
                        while existing_layout.count():
                            child = existing_layout.takeAt(0)
                            if child.widget():
                                child.widget().deleteLater()
                except:
                    pass
                
                layout = QVBoxLayout(self)
                error_label = QLabel(f"Error: {str(e)}")
                error_label.setWordWrap(True)
                layout.addWidget(error_label)
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(self.reject)
                layout.addWidget(close_btn)
            except Exception as inner_e:
                # If even the error handling fails, just raise the original error
                # But wrap it so we know what happened
                raise Exception(f"Critical error in preview dialog initialization: {str(e)} (inner: {str(inner_e)})")
    
    def _format_data(self, data: Any) -> str:
        """Format data for display."""
        try:
            if data is None:
                return "(No content)"
            
            if isinstance(data, str):
                return data
            elif isinstance(data, dict):
                # Format dict items, handling complex values
                formatted_items = []
                for k, v in data.items():
                    try:
                        if isinstance(v, (list, dict)):
                            v_str = str(v)
                        else:
                            v_str = str(v) if v is not None else "(none)"
                        formatted_items.append(f"{k}: {v_str}")
                    except Exception:
                        formatted_items.append(f"{k}: (error formatting value)")
                return "\n".join(formatted_items) if formatted_items else "(No items)"
            elif isinstance(data, list):
                if len(data) == 0:
                    return "(No items)"
                # Format list of items nicely
                formatted_items = []
                for i, item in enumerate(data, 1):
                    try:
                        if isinstance(item, str):
                            formatted_items.append(f"Item {i}:\n{item}\n")
                        else:
                            formatted_items.append(f"Item {i}:\n{str(item)}\n")
                    except Exception:
                        formatted_items.append(f"Item {i}:\n(error formatting item)\n")
                return "\n".join(formatted_items)
            else:
                return str(data) if data else "(No content)"
        except Exception as e:
            # Fallback for any unexpected errors
            return f"(Error formatting data: {str(e)})"


class AIChatPanel(QWidget):
    """AI Chat panel for discussing story ideas and making changes."""
    
    # Signals
    changes_applied = pyqtSignal(str, dict)  # change_type, change_data
    context_requested = pyqtSignal()  # Request current context
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenplay: Optional[Screenplay] = None
        self.ai_generator: Optional[AIGenerator] = None
        self.current_scene: Optional[StoryScene] = None
        self.selected_items: List[StoryboardItem] = []
        self.chat_history: List[Dict[str, Any]] = []
        self.chat_thread: Optional[ChatThread] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the chat panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header_label = QLabel("AI Story Assistant")
        header_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(header_label)
        
        # Context indicator
        self.context_label = QLabel("Context: No selection")
        self.context_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        layout.addWidget(self.context_label)
        
        # Suggestions panel (collapsible)
        suggestions_group = QGroupBox("Suggestions")
        suggestions_group.setCheckable(True)
        suggestions_group.setChecked(True)
        suggestions_layout = QVBoxLayout()
        
        self.suggestions_list = QTextEdit()
        self.suggestions_list.setReadOnly(True)
        self.suggestions_list.setMaximumHeight(150)
        self.suggestions_list.setPlaceholderText("Suggestions will appear here...")
        suggestions_layout.addWidget(self.suggestions_list)
        
        refresh_suggestions_btn = QPushButton("Refresh Suggestions")
        refresh_suggestions_btn.clicked.connect(self.generate_suggestions)
        suggestions_layout.addWidget(refresh_suggestions_btn)
        
        suggestions_group.setLayout(suggestions_layout)
        layout.addWidget(suggestions_group)
        self.suggestions_group = suggestions_group
        
        # Chat history area - use scroll area with widget for better control
        chat_group = QGroupBox("Conversation")
        chat_layout = QVBoxLayout()
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)
        # Prevent horizontal scrollbars - force word wrapping
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setContentsMargins(5, 5, 5, 5)
        scroll_area.setWidget(self.chat_container)
        
        # Store reference for width updates
        self._scroll_area = scroll_area
        
        # Connect to viewport resize to adjust content width
        def on_viewport_resize(event):
            """Handle viewport resize."""
            from PyQt6.QtWidgets import QWidget
            QWidget.resizeEvent(scroll_area.viewport(), event)
            # Update container width after viewport resize
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(10, self._update_chat_container_width)
        
        scroll_area.viewport().resizeEvent = on_viewport_resize
        
        # Connect to scrollbar rangeChanged signal (fires when content size changes)
        # This will detect when scrollbar appears/disappears
        scroll_area.verticalScrollBar().rangeChanged.connect(self._update_chat_container_width)
        
        # Update on scroll area resize too
        def on_scroll_area_resize(event):
            """Handle scroll area resize."""
            from PyQt6.QtWidgets import QWidget
            QWidget.resizeEvent(scroll_area, event)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(10, self._update_chat_container_width)
        
        scroll_area.resizeEvent = on_scroll_area_resize
        
        chat_layout.addWidget(scroll_area)
        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)
        
        self.scroll_area = scroll_area
        
        # Initial width update after UI is ready
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._update_chat_container_width)
        
        # Input area
        input_layout = QHBoxLayout()
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Type your message here... (Press Ctrl+Enter to send)")
        self.message_input.setMaximumHeight(100)
        self.message_input.setMinimumHeight(60)
        # Add key press event handler for Enter key
        self.message_input.keyPressEvent = self.message_input_key_press
        input_layout.addWidget(self.message_input)
        
        self.send_button = QPushButton("Send")
        self.send_button.setFixedWidth(80)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setEnabled(False)
        # Make button always clickable even when focus is elsewhere
        self.send_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Ensure button can receive clicks even when other widgets have focus
        self.send_button.setAutoDefault(False)
        self.send_button.setDefault(False)
        input_layout.addWidget(self.send_button)
        
        layout.addLayout(input_layout)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self.clear_chat)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Enable send button when there's text
        self.message_input.textChanged.connect(self.on_input_changed)
    
    def message_input_key_press(self, event):
        """Handle key press events in message input."""
        # Check for Ctrl+Enter or Ctrl+Return to send
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+Enter sends the message
                if self.send_button.isEnabled():
                    self.send_message()
                event.accept()
                return
            # Regular Enter creates a new line (default behavior)
        
        # Call the original keyPressEvent for normal behavior
        QTextEdit.keyPressEvent(self.message_input, event)
    
    def on_input_changed(self):
        """Enable/disable send button based on input."""
        has_text = len(self.message_input.toPlainText().strip()) > 0
        can_send = has_text and self.ai_generator is not None
        self.send_button.setEnabled(can_send)
        # Also update button tooltip
        if can_send:
            self.send_button.setToolTip("Send message (Ctrl+Enter)")
        else:
            if not has_text:
                self.send_button.setToolTip("Enter a message to send")
            elif not self.ai_generator:
                self.send_button.setToolTip("AI generator not configured")
    
    def update_send_button_state(self):
        """Manually update send button state (useful when focus changes)."""
        self.on_input_changed()
    
    def set_screenplay(self, screenplay: Optional[Screenplay]):
        """Set the current screenplay."""
        self.screenplay = screenplay
        # Removed automatic chat clearing at startup
        self.update_context_label()
    
    def set_ai_generator(self, ai_generator: Optional[AIGenerator]):
        """Set the AI generator."""
        self.ai_generator = ai_generator
        self.on_input_changed()
    
    def set_context(self, scene: Optional[StoryScene] = None, items: Optional[List[StoryboardItem]] = None):
        """Update the current context."""
        if scene is not None:
            self.current_scene = scene
        if items is not None:
            self.selected_items = items
        self.update_context_label()
        # Generate suggestions when context changes
        if self.screenplay:
            self.generate_suggestions()
    
    def generate_suggestions(self):
        """Generate proactive suggestions based on screenplay analysis."""
        if not self.screenplay:
            self.suggestions_list.setPlainText("No screenplay loaded.")
            return
        
        suggestions = []
        
        # Analyze screenplay
        analysis = self._analyze_screenplay()
        
        # Generate suggestions based on analysis
        if analysis.get("high_cost_scenes"):
            suggestions.append(f"⚠️ {len(analysis['high_cost_scenes'])} scene(s) have high render cost. Consider simplifying.")
        
        if analysis.get("unused_characters"):
            suggestions.append(f"💡 Character(s) not used in recent scenes: {', '.join(analysis['unused_characters'][:3])}")
        
        if analysis.get("pacing_issues"):
            suggestions.append(f"📊 Pacing: {analysis['pacing_issues']}")
        
        if analysis.get("scene_optimization"):
            suggestions.append(f"⚡ {analysis['scene_optimization']}")
        
        if analysis.get("dialogue_heavy_scenes"):
            suggestions.append(f"💬 {len(analysis['dialogue_heavy_scenes'])} dialogue-heavy scene(s) could be cheaper as static shots.")
        
        if not suggestions:
            suggestions.append("✓ No suggestions at this time. Your screenplay looks good!")
        
        self.suggestions_list.setPlainText("\n".join(suggestions))
    
    def _analyze_screenplay(self) -> Dict[str, Any]:
        """Analyze the screenplay and return analysis results."""
        analysis = {
            "high_cost_scenes": [],
            "unused_characters": [],
            "pacing_issues": "",
            "scene_optimization": "",
            "dialogue_heavy_scenes": []
        }
        
        if not self.screenplay:
            return analysis
        
        # Analyze render costs
        all_scenes = self.screenplay.get_all_scenes()
        for scene in all_scenes:
            expensive_items = [item for item in scene.storyboard_items 
                             if getattr(item, "render_cost", "unknown") == "expensive"]
            if expensive_items:
                analysis["high_cost_scenes"].append(scene.title)
        
        # Analyze character usage
        if hasattr(self.screenplay, "story_outline") and isinstance(self.screenplay.story_outline, dict):
            characters = self.screenplay.story_outline.get("characters", [])
            if characters:
                character_names = [c.get("name", "") for c in characters if isinstance(c, dict) and c.get("name")]
                # Check last 3 scenes for character usage
                recent_scenes = all_scenes[-3:] if len(all_scenes) >= 3 else all_scenes
                used_characters = set()
                for scene in recent_scenes:
                    used_characters.update(getattr(scene, "character_focus", []) or [])
                unused = [name for name in character_names if name and name not in used_characters]
                if unused:
                    analysis["unused_characters"] = unused
        
        # Analyze pacing
        if all_scenes:
            pacing_counts = {"Fast": 0, "Medium": 0, "Slow": 0}
            for scene in all_scenes:
                pacing = getattr(scene, "pacing", "Medium") or "Medium"
                pacing_counts[pacing] = pacing_counts.get(pacing, 0) + 1
            
            if pacing_counts.get("Fast", 0) >= 3:
                analysis["pacing_issues"] = "Multiple fast scenes in a row - consider variation"
        
        # Scene optimization
        if self.current_scene:
            item_count = len(self.current_scene.storyboard_items)
            duration = getattr(self.current_scene, "estimated_duration", 0) or 0
            if item_count > duration // 5:  # More items than needed
                analysis["scene_optimization"] = f"This scene may benefit from fewer storyboard items ({item_count} items for {duration}s)"
        
        # Dialogue-heavy scenes
        for scene in all_scenes:
            dialogue_items = [item for item in scene.storyboard_items 
                            if getattr(item, "dialogue", "") and len(getattr(item, "dialogue", "")) > 50]
            if len(dialogue_items) > len(scene.storyboard_items) * 0.7:  # 70%+ dialogue
                analysis["dialogue_heavy_scenes"].append(scene.title)
        
        return analysis
    
    def update_context_label(self):
        """Update the context indicator label."""
        context_parts = []
        
        if self.current_scene:
            context_parts.append(f"Scene: {self.current_scene.title}")
        
        if self.selected_items:
            if len(self.selected_items) == 1:
                context_parts.append(f"Item: {self.selected_items[0].sequence_number}")
            else:
                context_parts.append(f"Items: {len(self.selected_items)} selected")
        
        if not context_parts:
            self.context_label.setText("Context: No selection")
        else:
            self.context_label.setText("Context: " + " | ".join(context_parts))
    
    def _update_chat_container_width(self):
        """Update chat container width to account for vertical scrollbar."""
        if not hasattr(self, '_scroll_area') or not self._scroll_area:
            return
        
        scrollbar = self._scroll_area.verticalScrollBar()
        viewport = self._scroll_area.viewport()
        
        if not viewport or not self.chat_container:
            return
        
        viewport_width = viewport.width()
        
        if scrollbar.isVisible():
            # Account for scrollbar width plus some padding
            scrollbar_width = scrollbar.width()
            max_width = viewport_width - scrollbar_width - 5
        else:
            # No scrollbar, use full width minus small padding
            max_width = viewport_width - 5
        
        # Set maximum width to prevent content from extending under scrollbar
        self.chat_container.setMaximumWidth(max_width)
    
    def send_message(self):
        """Send a message to the AI."""
        # Get message regardless of focus
        message = self.message_input.toPlainText().strip()
        if not message:
            return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.")
            return
        
        # Check if this is an instruction request (these work even without AI client)
        user_lower = message.lower()
        instruction_keywords = [
            "how to use", "how do i use", "instructions", "instruction", "tutorial", "guide", 
            "help me use", "show me how", "explain how", "walk me through", "step by step",
            "how does this work", "how does it work", "what can i do", "what does this do",
            "usage", "user guide", "getting started", "how to get started", "how to start",
            "tell me about", "explain the app", "app instructions", "app guide", "app tutorial"
        ]
        is_instruction_request = any(keyword in user_lower for keyword in instruction_keywords)
        
        # For instruction requests, proceed even if client isn't initialized
        # For other requests, check if client is available
        if not is_instruction_request and not self.ai_generator.client:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.\n\nNote: You can still ask for app usage instructions!")
            return
        
        # Re-validate button state in case it got out of sync
        self.update_send_button_state()
        if not self.send_button.isEnabled():
            # Button shouldn't be disabled if we have message and AI, but check anyway
            return
        
        # Add user message to chat
        self.add_message("user", message)
        
        # Store user message in history
        self.chat_history.append({
            "role": "user",
            "content": message
        })
        
        self.message_input.clear()
        self.send_button.setEnabled(False)
        
        # Build context
        context = self.build_context()
        
        # Start chat thread
        if self.chat_thread and self.chat_thread.isRunning():
            QMessageBox.warning(self, "Request in Progress", "Please wait for the current request to complete.")
            return
        
        self.chat_thread = ChatThread(self.ai_generator, message, context)
        self.chat_thread.response_received.connect(self.on_response_received)
        self.chat_thread.error.connect(self.on_chat_error)
        self.chat_thread.start()
        
        # Show thinking indicator
        self.add_message("ai", "Thinking...", is_thinking=True)
    
    def build_context(self) -> dict:
        """Build context dictionary for AI."""
        context = {
            "screenplay": self.screenplay,
            "current_scene": self.current_scene,
            "selected_items": self.selected_items,
            "chat_history": self.chat_history[-10:]  # Last 10 messages for context
        }
        return context
    
    def on_response_received(self, response: dict):
        """Handle AI response."""
        # Remove thinking indicator
        self.remove_thinking_indicator()
        
        # Add AI response to chat
        text_response = response.get("text", "")
        suggestions = response.get("suggestions", [])
        
        self.add_message("ai", text_response)
        
        # Add suggestions if any, storing the last user message for context
        if suggestions:
            last_user_message = self.chat_history[-1]["content"] if self.chat_history else ""
            for suggestion in suggestions:
                # Add user request to change_data for regenerate operations
                if "change_data" not in suggestion:
                    suggestion["change_data"] = {}
                if "user_request" not in suggestion["change_data"]:
                    suggestion["change_data"]["user_request"] = last_user_message
                self.add_suggestion(suggestion)
        
        # Update chat history (user message already added in send_message)
        self.chat_history.append({
            "role": "assistant",
            "content": text_response,
            "suggestions": suggestions
        })
    
    def on_chat_error(self, error_msg: str):
        """Handle chat error."""
        self.remove_thinking_indicator()
        self.add_message("ai", f"Error: {error_msg}", is_error=True)
        QMessageBox.critical(self, "Chat Error", f"Failed to get AI response:\n{error_msg}")
    
    def add_message(self, role: str, content: str, is_thinking: bool = False, is_error: bool = False):
        """Add a message to the chat display."""
        from PyQt6.QtWidgets import QSizePolicy
        
        message_frame = QFrame()
        message_frame.setFrameStyle(QFrame.Shape.Box)
        # Ensure frame respects container width and wraps content
        message_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        message_layout = QVBoxLayout(message_frame)
        # Add extra right margin to prevent text from being cut off by scrollbar
        message_layout.setContentsMargins(10, 5, 15, 5)
        
        label = QLabel(content)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Ensure label wraps and doesn't cause horizontal scrolling
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        if role == "user":
            message_frame.setStyleSheet("background-color: #e3f2fd; border-radius: 8px;")
            label.setText(f"<b>You:</b><br>{content}")
            message_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            color = "#ffebee" if is_error else "#f1f8e9"
            message_frame.setStyleSheet(f"background-color: {color}; border-radius: 8px;")
            label.setText(f"<b>AI:</b><br>{content}")
            message_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        message_layout.addWidget(label)
        self.chat_layout.addWidget(message_frame)
        
        # Update container width in case scrollbar appeared, then scroll to bottom
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, self._update_chat_container_width)
        QTimer.singleShot(100, lambda: self.scroll_to_bottom())
    
    def add_suggestion(self, suggestion: dict):
        """Add a suggestion with action buttons to the chat."""
        change_type = suggestion.get("change_type", "")
        description = suggestion.get("description", "")
        change_data = suggestion.get("change_data", {})
        
        # Store suggestion for later reference
        if not hasattr(self, '_suggestions'):
            self._suggestions = []
        suggestion_id = len(self._suggestions)
        # Make a deep copy of change_data to ensure it's preserved
        import copy
        stored_change_data = copy.deepcopy(change_data)
        self._suggestions.append({
            "change_type": change_type,
            "change_data": stored_change_data,
            "description": description,
            "id": suggestion_id
        })
        # Debug: Log what's being stored
        if change_type == "edit_character_outline":
            print(f"DEBUG add_suggestion: Storing character outline suggestion")
            print(f"DEBUG add_suggestion: change_data keys: {list(stored_change_data.keys())}")
            print(f"DEBUG add_suggestion: character_name: {stored_change_data.get('character_name')}")
            print(f"DEBUG add_suggestion: has_outline: {bool(stored_change_data.get('character_outline'))}")
            print(f"DEBUG add_suggestion: has_growth: {bool(stored_change_data.get('character_growth_arc'))}")
        
        # Create suggestion frame
        from PyQt6.QtWidgets import QSizePolicy
        suggestion_frame = QFrame()
        suggestion_frame.setFrameStyle(QFrame.Shape.Box)
        suggestion_frame.setStyleSheet("background-color: #fff3e0; border-left: 4px solid #ff9800; border-radius: 4px; padding: 10px;")
        # Ensure frame respects container width and wraps content
        suggestion_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        suggestion_layout = QVBoxLayout(suggestion_frame)
        # Add extra right margin to prevent text from being cut off by scrollbar
        suggestion_layout.setContentsMargins(10, 10, 15, 10)
        
        desc_label = QLabel(f"<b>Suggestion:</b> {description}")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        suggestion_layout.addWidget(desc_label)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 5px 15px; border-radius: 4px;")
        apply_btn.clicked.connect(lambda checked, sid=suggestion_id: self.handle_suggestion_action(sid, "apply"))
        button_layout.addWidget(apply_btn)
        
        preview_btn = QPushButton("Preview")
        preview_btn.setStyleSheet("background-color: #2196f3; color: white; padding: 5px 15px; border-radius: 4px;")
        preview_btn.clicked.connect(lambda checked, sid=suggestion_id: self.handle_suggestion_action(sid, "preview"))
        button_layout.addWidget(preview_btn)
        
        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setStyleSheet("background-color: #f44336; color: white; padding: 5px 15px; border-radius: 4px;")
        dismiss_btn.clicked.connect(lambda checked, sid=suggestion_id: self.handle_suggestion_action(sid, "dismiss"))
        button_layout.addWidget(dismiss_btn)
        
        suggestion_layout.addLayout(button_layout)
        self.chat_layout.addWidget(suggestion_frame)
        
        # Scroll to bottom after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.scroll_to_bottom())
    
    def scroll_to_bottom(self):
        """Scroll chat area to bottom."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def handle_suggestion_action(self, suggestion_id: int, action: str):
        """Handle action on a suggestion (apply, preview, dismiss)."""
        if not hasattr(self, '_suggestions') or suggestion_id >= len(self._suggestions):
            return
        
        try:
            suggestion = self._suggestions[suggestion_id]
            if not isinstance(suggestion, dict):
                QMessageBox.warning(self, "Error", "Invalid suggestion data.")
                return
            
            change_type = suggestion.get("change_type", "edit_scene")
            change_data = suggestion.get("change_data", {})
            
            # Debug: Log suggestion data
            print(f"DEBUG handle_suggestion_action: change_type={change_type}")
            print(f"DEBUG handle_suggestion_action: suggestion keys: {list(suggestion.keys())}")
            print(f"DEBUG handle_suggestion_action: change_data type: {type(change_data)}, keys={list(change_data.keys()) if isinstance(change_data, dict) else 'not a dict'}")
            if change_type == "edit_character_outline" and isinstance(change_data, dict):
                print(f"DEBUG handle_suggestion_action: character_name={change_data.get('character_name')}")
                print(f"DEBUG handle_suggestion_action: has_outline={bool(change_data.get('character_outline'))}")
                print(f"DEBUG handle_suggestion_action: has_growth={bool(change_data.get('character_growth_arc'))}")
                if change_data.get('character_outline'):
                    print(f"DEBUG handle_suggestion_action: outline preview: {change_data.get('character_outline')[:100]}...")
            
            if not isinstance(change_data, dict):
                QMessageBox.warning(self, "Error", f"Invalid change data. Type: {type(change_data)}")
                return
            
            # Make a deep copy to avoid modifying the original suggestion
            import copy
            change_data = copy.deepcopy(change_data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process suggestion: {str(e)}")
            return
        
        if action == "dismiss":
            # Just remove from display (could mark as dismissed)
            return
        elif action == "preview":
            # For preview, we need to generate the changes first if not already generated
            # Handle character outline edits specially - they don't need generation
            if change_type == "edit_character_outline":
                try:
                    before_data = self.get_before_data(change_type, change_data)
                    after_data = self.get_after_data(change_type, change_data)
                    
                    # Ensure before_data and after_data are valid
                    if before_data is None:
                        before_data = "(No data available)"
                    if after_data is None:
                        after_data = "(No data available)"
                    
                    # Show preview dialog
                    dialog = ChangePreviewDialog(change_type, before_data, after_data, self)
                    result = dialog.exec()
                    if result == QDialog.DialogCode.Accepted:
                        # Apply the change
                        self.apply_change(change_type, change_data)
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    QMessageBox.critical(
                        self, "Preview Error",
                        f"Failed to show preview dialog:\n{str(e)}\n\nDetails:\n{error_details[:500]}"
                    )
                return
            
            # First, check if this is actually a character_focus edit (even if change_type is wrong)
            try:
                edits = change_data.get("edits", {})
                # Ensure edits is a dict
                if not isinstance(edits, dict):
                    if edits is None:
                        edits = {}
                    else:
                        # Try to convert or create new dict
                        edits = {}
                        change_data["edits"] = edits
            except Exception:
                edits = {}
                change_data["edits"] = edits
            
            is_character_focus_edit = False
            
            # Check if edits contains character_focus
            if isinstance(edits, dict) and "character_focus" in edits:
                is_character_focus_edit = True
                # Convert to edit_scene if it's not already
                if change_type != "edit_scene":
                    change_type = "edit_scene"
                    suggestion["change_type"] = "edit_scene"
            
            # Also check description for character-related keywords (handle misclassified requests)
            if not is_character_focus_edit:
                description = suggestion.get("description", "").lower()
                user_request = change_data.get("user_request", "").lower()
                if ("character" in description or "character" in user_request) and self.current_scene:
                    # Check if this might be a character edit that was misclassified
                    if change_type in ["add_items", "edit_items"]:
                        # Likely should be edit_scene with character_focus
                        is_character_focus_edit = True
                        change_type = "edit_scene"
                        suggestion["change_type"] = "edit_scene"
                        # Move any relevant data to edits
                        if "edits" not in change_data or not isinstance(change_data.get("edits"), dict):
                            change_data["edits"] = {}
                        if "character_focus" not in change_data["edits"]:
                            # Try to extract character names from description or new_items
                            character_names = []
                            import re
                            # Look for character names in description/user_request (capitalized words)
                            words = re.findall(r'\b([A-Z][a-z]+)\b', description + " " + user_request)
                            # Filter out common words that aren't character names
                            common_words = ["Character", "The", "This", "That", "Scene", "Story", "Change", "Edit", "Add", "Remove"]
                            character_names = [w for w in words if w not in common_words and len(w) > 2]
                            if character_names:
                                change_data["edits"]["character_focus"] = list(set(character_names))  # Remove duplicates
                            else:
                                # If we can't extract, try to get from new_items if available
                                if "new_items" in change_data:
                                    new_items = change_data.get("new_items", [])
                                    # Try to infer from item content if available
                                    if new_items and isinstance(new_items, list):
                                        # For now, use a generic placeholder
                                        change_data["edits"]["character_focus"] = ["Character"]
                                    else:
                                        change_data["edits"]["character_focus"] = ["Character"]
                                else:
                                    # Fallback - use description or user request as is
                                    change_data["edits"]["character_focus"] = [description.split()[0].title()] if description.split() else ["Character"]
                            # Update edits reference
                            edits = change_data["edits"]
            
            before_data = self.get_before_data(change_type, change_data)
            
            # Track whether we generated content
            content_was_generated = False
            after_data = None  # Initialize after_data early
            
            # Handle character_focus edits specially - they don't need content generation
            if is_character_focus_edit and isinstance(edits, dict) and "character_focus" in edits:
                needs_generation = False
                character_focus = edits["character_focus"]
                try:
                    if isinstance(character_focus, list):
                        # Ensure all items are strings before joining
                        character_focus_strs = [str(cf).strip() for cf in character_focus if cf]
                        after_data = f"Character Focus: {', '.join(character_focus_strs) if character_focus_strs else '(none)'}"
                    elif isinstance(character_focus, str):
                        after_data = f"Character Focus: {character_focus.strip()}"
                    else:
                        after_data = f"Character Focus: {str(character_focus)}"
                except Exception as e:
                    # Fallback if there's any error formatting
                    after_data = f"Character Focus: {str(character_focus)}"
                # Mark as handled - we have after_data already
                content_was_generated = True
            elif change_type in ["regenerate_scene", "edit_scene"]:
                # Normal content edit path
                # Check if we need to generate the content
                needs_generation = False
                existing_new_content = change_data.get("new_content", "")
                # Also check edits field for edit_scene type
                if not existing_new_content and change_type == "edit_scene":
                    if isinstance(edits, dict):
                        existing_new_content = edits.get("new_content", "")
                    elif isinstance(edits, list):
                        # If edits is a list, convert to new_content format
                        existing_new_content = " ".join(str(e) for e in edits) if edits else ""
                
                # Check if this is a paragraph edit request
                user_request = change_data.get("user_request", "").lower()
                paragraph_index = change_data.get("paragraph_index")
                is_paragraph_edit = (
                    paragraph_index is not None or
                    any(keyword in user_request for keyword in [
                        "paragraph", "paragragh", "option", "options", "alternative", 
                        "alternatives", "version", "versions"
                    ])
                )
                
                # Check if new_content exists and is valid (non-empty)
                has_valid_content = existing_new_content and existing_new_content.strip()
                
                # For paragraph edits, check if we have a paragraph option from the suggestion
                # If we do, we should use it and merge it (don't regenerate, as that would give a different option)
                if is_paragraph_edit and has_valid_content and self.current_scene:
                    # Check if the new_content is likely a single paragraph option or full scene
                    import re
                    existing_content = ""
                    if self.current_scene.metadata and self.current_scene.metadata.get("generated_content"):
                        existing_content = self.current_scene.metadata["generated_content"]
                    else:
                        existing_content = self.current_scene.description
                    
                    if existing_content:
                        existing_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                        new_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', existing_new_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                        
                        # If new_content has fewer paragraphs, it's a paragraph option - use it, don't regenerate
                        if len(new_paragraphs) < len(existing_paragraphs) and len(existing_paragraphs) > 1:
                            # This is a paragraph option from the suggestion - use it and merge
                            needs_generation = False
                        elif len(new_paragraphs) == len(existing_paragraphs):
                            # Full scene already provided - use it directly
                            needs_generation = False
                        else:
                            # Content exists but seems incomplete - regenerate
                            needs_generation = True
                    else:
                        # No existing content - generate
                        needs_generation = True
                elif is_paragraph_edit:
                    # Paragraph edit but no content - generate
                    needs_generation = True
                else:
                    # Not a paragraph edit - only generate if content is missing or empty
                    needs_generation = not has_valid_content
            elif change_type == "regenerate_items":
                needs_generation = "new_items" not in change_data or not change_data.get("new_items")
            elif change_type == "add_items":
                # Handle add_items - might be misclassified character edit
                if is_character_focus_edit:
                    # This was misclassified as add_items but is actually a character edit
                    # Already handled above with after_data set, but set needs_generation to False
                    needs_generation = False
                else:
                    # Regular add_items - preview not supported, needs generation but won't generate
                    needs_generation = False
                    # Try to use get_after_data for preview
                    after_data = self.get_after_data(change_type, change_data)
                    if not after_data:
                        # No preview available for add_items
                        QMessageBox.information(
                            self, "Preview",
                            "Preview is not available for adding items. Click Apply to apply the changes directly."
                        )
                        return
            
            # Generate content if needed (skip if we already have after_data for character edits)
            if is_character_focus_edit and after_data:
                # We already have after_data for character edit, skip generation
                # content_was_generated is already True from above
                pass  # Skip to showing preview dialog
            elif needs_generation:
                if change_type in ["regenerate_scene", "edit_scene"] and self.current_scene and self.ai_generator:
                    try:
                        # Show progress
                        from PyQt6.QtWidgets import QProgressDialog
                        from PyQt6.QtCore import Qt
                        progress = QProgressDialog("Generating preview...", "Cancel", 0, 0, self)
                        progress.setWindowModality(Qt.WindowModality.WindowModal)
                        progress.setCancelButton(None)
                        progress.show()
                        
                        user_request = change_data.get("user_request", "")
                        # Extract paragraph_index early to ensure we can build the correct request
                        paragraph_index_from_data = change_data.get("paragraph_index")
                        
                        # If paragraph_index is not in change_data, try to extract it from user_request first
                        if paragraph_index_from_data is None:
                            import re
                            user_request_lower = user_request.lower()
                            para_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request_lower)
                            if para_match:
                                para_num = int(para_match.group(1) or para_match.group(2) or para_match.group(3))
                                paragraph_index_from_data = para_num - 1
                            elif "second" in user_request_lower or "paragraph 2" in user_request_lower or "2nd" in user_request_lower:
                                paragraph_index_from_data = 1
                            elif "third" in user_request_lower or "paragraph 3" in user_request_lower or "3rd" in user_request_lower:
                                paragraph_index_from_data = 2
                            elif "fourth" in user_request_lower or "paragraph 4" in user_request_lower or "4th" in user_request_lower:
                                paragraph_index_from_data = 3
                            elif "fifth" in user_request_lower or "paragraph 5" in user_request_lower or "5th" in user_request_lower:
                                paragraph_index_from_data = 4
                            elif "first" in user_request_lower or "paragraph 1" in user_request_lower or "1st" in user_request_lower:
                                paragraph_index_from_data = 0
                        
                        # Store it in change_data
                        if paragraph_index_from_data is not None:
                            change_data["paragraph_index"] = paragraph_index_from_data
                        
                        # Ensure user_request clearly specifies which paragraph when regenerating
                        if paragraph_index_from_data is not None:
                            para_num = paragraph_index_from_data + 1
                            # Check if request already clearly specifies the paragraph
                            has_para_ref = (
                                f"paragraph {para_num}" in user_request.lower() or
                                f"[{para_num}]" in user_request or
                                (para_num == 1 and "first" in user_request.lower()) or
                                (para_num == 2 and ("second" in user_request.lower() or "2nd" in user_request.lower())) or
                                (para_num == 3 and ("third" in user_request.lower() or "3rd" in user_request.lower())) or
                                (para_num == 4 and ("fourth" in user_request.lower() or "4th" in user_request.lower())) or
                                (para_num == 5 and ("fifth" in user_request.lower() or "5th" in user_request.lower()))
                            )
                            
                            if not has_para_ref and not user_request:
                                user_request = f"Edit paragraph {para_num}"
                            elif not has_para_ref:
                                # Prepend paragraph reference to make it clear
                                user_request = f"Edit paragraph {para_num}: {user_request}"
                        
                        # If user_request is empty or if change_type is edit_scene, try to build it from edits or description
                        if not user_request or change_type == "edit_scene":
                            edits = change_data.get("edits", {})
                            if isinstance(edits, dict) and "new_content" in edits:
                                # If edits has new_content, extract it but still process it (may need merging)
                                new_content = edits.get("new_content", "")
                                if new_content and new_content.strip():
                                    change_data["new_content"] = new_content
                                    # Don't set content_was_generated yet - let it go through merging logic below
                                else:
                                    # Build request from edits list or description
                                    if isinstance(edits, list):
                                        user_request = " ".join(str(e) for e in edits[:3])  # Use first 3 edits
                                    elif isinstance(edits, dict):
                                        # Try to extract meaningful request from edits dict
                                        edit_text = edits.get("description", "") or edits.get("text", "")
                                        if edit_text:
                                            user_request = edit_text
                            elif isinstance(edits, list) and edits:
                                # Convert edits list to request
                                user_request = "Apply these changes: " + " ".join(str(e) for e in edits[:2])
                            
                            # Fallback to description if still empty
                            if not user_request:
                                description = change_data.get("description", "")
                                if description:
                                    user_request = description
                                else:
                                    user_request = "Regenerate this scene"
                        
                        # Generate the new content if we don't already have it
                        # But for paragraph edits, if we have new_content from suggestion, use it (it's the selected option)
                        existing_new_content_in_data = change_data.get("new_content", "")
                        if not existing_new_content_in_data or not existing_new_content_in_data.strip():
                            # No content - generate it
                            new_content = self.ai_generator.regenerate_scene_content(
                                self.current_scene, user_request, self.screenplay
                            )
                            change_data["new_content"] = new_content
                            content_was_generated = True
                        else:
                            # We have content from suggestion - use it (it's the specific option the user wants to preview)
                            new_content = existing_new_content_in_data
                            content_was_generated = False  # We didn't generate, we're using the option from suggestion
                        
                        # For paragraph edits, ensure we have the full merged scene content
                        # Extract paragraph index before processing
                        paragraph_index = change_data.get("paragraph_index")
                        user_request_lower = user_request.lower()
                        is_paragraph_edit = (
                            paragraph_index is not None or
                            any(keyword in user_request_lower for keyword in [
                                "paragraph", "paragragh", "option", "options", "alternative",
                                "alternatives", "version", "versions"
                            ])
                        )
                        
                        # If paragraph_index is not set but we can extract it, do so now
                        if is_paragraph_edit and paragraph_index is None:
                            import re
                            para_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request_lower)
                            if para_match:
                                para_num = int(para_match.group(1) or para_match.group(2) or para_match.group(3))
                                paragraph_index = para_num - 1
                            elif "second" in user_request_lower or "paragraph 2" in user_request_lower or "2nd" in user_request_lower:
                                paragraph_index = 1
                            elif "third" in user_request_lower or "paragraph 3" in user_request_lower or "3rd" in user_request_lower:
                                paragraph_index = 2
                            elif "fourth" in user_request_lower or "paragraph 4" in user_request_lower or "4th" in user_request_lower:
                                paragraph_index = 3
                            elif "fifth" in user_request_lower or "paragraph 5" in user_request_lower or "5th" in user_request_lower:
                                paragraph_index = 4
                            elif "first" in user_request_lower or "paragraph 1" in user_request_lower or "1st" in user_request_lower:
                                paragraph_index = 0
                            
                            # Store it for later use
                            if paragraph_index is not None:
                                change_data["paragraph_index"] = paragraph_index
                        
                        # If we have paragraph_index now, ensure it's stored
                        if paragraph_index is not None:
                            change_data["paragraph_index"] = paragraph_index
                        
                        if is_paragraph_edit and self.current_scene:
                            # Verify the content is complete (has all paragraphs)
                            existing_content = ""
                            if self.current_scene.metadata and self.current_scene.metadata.get("generated_content"):
                                existing_content = self.current_scene.metadata["generated_content"]
                            else:
                                existing_content = self.current_scene.description
                            
                            if existing_content:
                                import re
                                existing_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                                new_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', new_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                                
                                # regenerate_scene_content should return the full scene with all paragraphs
                                # If it has the same number of paragraphs, use it directly
                                if len(new_paragraphs) == len(existing_paragraphs):
                                    # Full scene was generated - use it directly (regenerate_scene_content already merged correctly)
                                    new_content = '\n\n'.join(new_paragraphs)
                                elif len(new_paragraphs) < len(existing_paragraphs) and len(existing_paragraphs) > 1:
                                    # Only a single paragraph was returned - merge it into existing content at the correct index
                                    # paragraph_index should already be set above, but double-check it's valid
                                    if paragraph_index is None:
                                        # Try to extract it one more time
                                        paragraph_index = 0
                                        import re
                                        para_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request_lower)
                                        if para_match:
                                            para_num = int(para_match.group(1) or para_match.group(2) or para_match.group(3))
                                            paragraph_index = para_num - 1
                                        elif "second" in user_request_lower or "paragraph 2" in user_request_lower or "2nd" in user_request_lower:
                                            paragraph_index = 1
                                        elif "third" in user_request_lower or "paragraph 3" in user_request_lower or "3rd" in user_request_lower:
                                            paragraph_index = 2
                                        elif "fourth" in user_request_lower or "paragraph 4" in user_request_lower or "4th" in user_request_lower:
                                            paragraph_index = 3
                                        elif "fifth" in user_request_lower or "paragraph 5" in user_request_lower or "5th" in user_request_lower:
                                            paragraph_index = 4
                                    
                                    # Ensure paragraph_index is valid
                                    if paragraph_index < 0:
                                        paragraph_index = 0
                                    if paragraph_index >= len(existing_paragraphs):
                                        paragraph_index = len(existing_paragraphs) - 1
                                    
                                    # Merge: replace ONLY the specified paragraph with the new paragraph option
                                    reconstructed = existing_paragraphs.copy()
                                    replacement = new_paragraphs[0] if new_paragraphs else new_content.strip()
                                    if replacement and paragraph_index < len(reconstructed):
                                        # Replace the paragraph at the correct index
                                        reconstructed[paragraph_index] = replacement
                                    new_content = '\n\n'.join(reconstructed)
                                elif len(new_paragraphs) > len(existing_paragraphs):
                                    # More paragraphs than existing - use as is (might be expanded scene)
                                    new_content = '\n\n'.join(new_paragraphs)
                                # If same count, already handled above - use directly
                        
                        # Validate that we actually got content
                        if not new_content or not new_content.strip():
                            if 'progress' in locals():
                                progress.close()
                            QMessageBox.warning(
                                self, "Generation Error",
                                "The AI generated empty content. Please try again or check your AI settings."
                            )
                            return
                        
                        # Store it in change_data for later use
                        change_data["new_content"] = new_content
                        # Also set after_data directly since we just generated it
                        after_data = new_content
                        progress.close()
                    except Exception as e:
                        if 'progress' in locals():
                            progress.close()
                        import traceback
                        error_details = traceback.format_exc()
                        QMessageBox.critical(
                            self, "Error", 
                            f"Failed to generate preview:\n{str(e)}\n\nDetails:\n{error_details[:500]}"
                        )
                        return
                elif change_type == "regenerate_items" and self.selected_items and self.ai_generator and self.current_scene:
                    try:
                        # Show progress
                        from PyQt6.QtWidgets import QProgressDialog
                        from PyQt6.QtCore import Qt
                        progress = QProgressDialog("Generating preview...", "Cancel", 0, 0, self)
                        progress.setWindowModality(Qt.WindowModality.WindowModal)
                        progress.setCancelButton(None)
                        progress.show()
                        
                        user_request = change_data.get("user_request", "Regenerate these items")
                        new_items = self.ai_generator.regenerate_storyboard_items(
                            self.current_scene, self.selected_items, user_request, self.screenplay
                        )
                        change_data["new_items"] = new_items
                        progress.close()
                    except Exception as e:
                        if 'progress' in locals():
                            progress.close()
                        QMessageBox.critical(self, "Error", f"Failed to generate preview:\n{str(e)}")
                        return
                else:
                    QMessageBox.information(
                        self, "Preview",
                        "Preview is not available for this type of change. Click Apply to apply the changes directly."
                    )
                    return
            
            # Get after_data now that it's been generated (or merged)
            # If we just generated content, use it directly instead of calling get_after_data
            # But for character edits, we already have after_data, so skip
            if not content_was_generated and not is_character_focus_edit:
                after_data = self.get_after_data(change_type, change_data)
            
            # If after_data is still empty and we didn't generate (meaning we tried to merge), fall back to generation
            # But skip for character edits - they should already have after_data
            if (not after_data or (isinstance(after_data, str) and not after_data.strip())) and not content_was_generated and not is_character_focus_edit:
                # Merging failed or returned empty - generate instead
                if change_type in ["regenerate_scene", "edit_scene"] and self.current_scene and self.ai_generator:
                    try:
                        from PyQt6.QtWidgets import QProgressDialog
                        from PyQt6.QtCore import Qt
                        progress = QProgressDialog("Generating preview...", "Cancel", 0, 0, self)
                        progress.setWindowModality(Qt.WindowModality.WindowModal)
                        progress.setCancelButton(None)
                        progress.show()
                        
                        user_request = change_data.get("user_request", "Regenerate this scene")
                        new_content = self.ai_generator.regenerate_scene_content(
                            self.current_scene, user_request, self.screenplay
                        )
                        
                        # Validate content
                        if not new_content or not new_content.strip():
                            if 'progress' in locals():
                                progress.close()
                            QMessageBox.warning(
                                self, "Generation Error",
                                "The AI generated empty content. Please try again or check your AI settings."
                            )
                            return
                        
                        change_data["new_content"] = new_content
                        after_data = new_content
                        content_was_generated = True
                        progress.close()
                    except Exception as e:
                        if 'progress' in locals():
                            progress.close()
                        import traceback
                        error_details = traceback.format_exc()
                        QMessageBox.critical(
                            self, "Error", 
                            f"Failed to generate preview:\n{str(e)}\n\nDetails:\n{error_details[:500]}"
                        )
                        return
            
            # If after_data is still empty, try get_after_data as a fallback (especially for character edits)
            if not after_data or (isinstance(after_data, str) and not after_data.strip()):
                # Try get_after_data as fallback - this might help for character edits that weren't detected earlier
                fallback_after_data = self.get_after_data(change_type, change_data)
                if fallback_after_data and (isinstance(fallback_after_data, str) and fallback_after_data.strip()):
                    after_data = fallback_after_data
                    content_was_generated = True  # Mark as handled
            
            # Verify we have after_data before showing preview
            if not after_data or (isinstance(after_data, str) and not after_data.strip()):
                # Debug info
                debug_info = []
                debug_info.append(f"content_was_generated: {content_was_generated}")
                debug_info.append(f"needs_generation: {needs_generation}")
                debug_info.append(f"change_type: {change_type}")
                debug_info.append(f"is_character_focus_edit: {is_character_focus_edit}")
                debug_info.append(f"has edits in change_data: {'edits' in change_data}")
                if 'edits' in change_data:
                    edits_debug = change_data.get("edits", {})
                    if isinstance(edits_debug, dict):
                        debug_info.append(f"edits keys: {list(edits_debug.keys())}")
                        if "character_focus" in edits_debug:
                            debug_info.append(f"character_focus value: {edits_debug['character_focus']}")
                debug_info.append(f"has new_content in change_data: {'new_content' in change_data}")
                if 'new_content' in change_data:
                    new_content_val = change_data.get("new_content", "")
                    debug_info.append(f"new_content length: {len(new_content_val) if new_content_val else 0}")
                    debug_info.append(f"new_content preview: {new_content_val[:100] if new_content_val else 'empty'}")
                debug_info.append(f"has new_items in change_data: {'new_items' in change_data}")
                if 'new_items' in change_data:
                    new_items_val = change_data.get("new_items", [])
                    debug_info.append(f"new_items type: {type(new_items_val)}")
                    debug_info.append(f"new_items length: {len(new_items_val) if isinstance(new_items_val, list) else 'N/A'}")
                
                error_msg = "No content was generated for preview."
                if not content_was_generated:
                    error_msg += "\n\nGeneration was not attempted. This might indicate a problem with suggestion detection."
                else:
                    error_msg += "\n\nGeneration was attempted but returned empty content. Please check your AI settings."
                error_msg += f"\n\nDebug info: {'; '.join(debug_info)}"
                
                QMessageBox.warning(
                    self, "Preview Error",
                    error_msg
                )
                return
            
            # Ensure before_data and after_data are valid
            if before_data is None:
                before_data = "(No data available)"
            elif not isinstance(before_data, (str, dict, list)):
                # Convert to string if it's an unexpected type
                try:
                    before_data = str(before_data)
                except:
                    before_data = "(Unable to format before data)"
            
            if after_data is None:
                after_data = "(No data available)"
            elif not isinstance(after_data, (str, dict, list)):
                # Convert to string if it's an unexpected type
                try:
                    after_data = str(after_data)
                except:
                    after_data = "(Unable to format after data)"
            
            # Validate change_type
            if not change_type or not isinstance(change_type, str):
                change_type = "edit_scene"  # Default fallback
            
            # Show preview dialog
            try:
                # Ensure parent is valid
                parent_widget = self if self else None
                
                # Create dialog with error handling
                dialog = None
                try:
                    dialog = ChangePreviewDialog(change_type, before_data, after_data, parent_widget)
                except Exception as dialog_init_error:
                    import traceback
                    error_details = traceback.format_exc()
                    QMessageBox.critical(
                        self, "Preview Error",
                        f"Failed to create preview dialog:\n{str(dialog_init_error)}\n\nDetails:\n{error_details[:500]}"
                    )
                    return
                
                # Show dialog with error handling
                if dialog:
                    try:
                        result = dialog.exec()
                    except Exception as dialog_exec_error:
                        import traceback
                        error_details = traceback.format_exc()
                        QMessageBox.critical(
                            self, "Preview Error",
                            f"Failed to show preview dialog:\n{str(dialog_exec_error)}\n\nDetails:\n{error_details[:500]}"
                        )
                        return
                else:
                    QMessageBox.warning(self, "Preview Error", "Failed to create preview dialog.")
                    return
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                QMessageBox.critical(
                    self, "Preview Error",
                    f"Unexpected error showing preview:\n{str(e)}\n\nDetails:\n{error_details[:500]}"
                )
                return
            if result == QDialog.DialogCode.Accepted:
                # Apply the change (content is already generated and stored in change_data)
                # Make sure we have the data before applying
                if change_type in ["regenerate_scene", "edit_scene"]:
                    # Check if this is a character_focus edit - those don't need new_content
                    edits = change_data.get("edits", {})
                    is_char_focus_edit = isinstance(edits, dict) and "character_focus" in edits
                    
                    if not is_char_focus_edit and not change_data.get("new_content"):
                        QMessageBox.warning(self, "Error", "No content to apply. Please try again.")
                        return
                    # Verify the content looks complete (has multiple paragraphs if it should)
                    new_content = change_data.get("new_content", "")
                    if self.current_scene and self.current_scene.metadata:
                        existing_content = self.current_scene.metadata.get("generated_content", "")
                        if existing_content:
                            existing_paragraphs = [p.strip() for p in existing_content.split('\n\n') if p.strip()]
                            new_paragraphs = [p.strip() for p in new_content.split('\n\n') if p.strip()]
                            # If we have fewer paragraphs, the content might be incomplete
                            if len(new_paragraphs) < len(existing_paragraphs) and len(existing_paragraphs) > 1:
                                # This might be just the paragraph - we'll handle it in on_chat_changes_applied
                                pass
                elif change_type == "regenerate_items":
                    if not change_data.get("new_items"):
                        QMessageBox.warning(self, "Error", "No items to apply. Please try again.")
                        return
                
                # Apply the change
                self.apply_change(change_type, change_data)
        elif action == "apply":
            # Apply immediately (will generate if needed)
            reply = QMessageBox.question(
                self, "Apply Changes",
                f"Apply {change_type.replace('_', ' ')}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.apply_change(change_type, change_data)
    
    def get_before_data(self, change_type: str, change_data: dict) -> Any:
        """Get the current state before changes."""
        if change_type == "edit_character_outline":
            # Get current character outline
            character_name = change_data.get("character_name", "")
            if not character_name and self.screenplay and self.screenplay.story_outline:
                # Try to extract from context
                characters = self.screenplay.story_outline.get("characters", [])
                if characters and isinstance(characters, list):
                    # Use first character if available
                    for char in characters:
                        if isinstance(char, dict):
                            character_name = char.get("name", "")
                            break
            
            if character_name and self.screenplay and self.screenplay.story_outline:
                characters = self.screenplay.story_outline.get("characters", [])
                for char in characters:
                    if isinstance(char, dict) and char.get("name", "").strip() == character_name.strip():
                        outline = char.get("outline", "")
                        growth_arc = char.get("growth_arc", "")
                        result = f"Character: {character_name}\n\n"
                        if outline:
                            result += f"Current Outline:\n{outline}\n\n"
                        else:
                            result += "Current Outline: (none)\n\n"
                        if growth_arc:
                            result += f"Current Growth Arc:\n{growth_arc}"
                        else:
                            result += "Current Growth Arc: (none)"
                        return result
            return f"Character: {character_name if character_name else 'Unknown'}\n\n(No existing outline found)"
        elif change_type in ["regenerate_scene", "edit_scene"]:
            if self.current_scene:
                # Check if this is a character_focus edit
                edits = change_data.get("edits", {})
                if isinstance(edits, dict) and "character_focus" in edits:
                    # Return current character focus for preview
                    try:
                        if self.current_scene and self.current_scene.character_focus:
                            # Ensure all items are strings before joining
                            char_focus_strs = [str(cf).strip() for cf in self.current_scene.character_focus if cf]
                            return f"Character Focus: {', '.join(char_focus_strs) if char_focus_strs else '(none)'}"
                        else:
                            return "Character Focus: (none)"
                    except Exception as e:
                        # Fallback if there's any error
                        return f"Character Focus: {str(self.current_scene.character_focus) if self.current_scene and self.current_scene.character_focus else '(none)'}"
                
                # Get the existing generated content
                if self.current_scene.metadata and self.current_scene.metadata.get("generated_content"):
                    return self.current_scene.metadata.get("generated_content")
                # Fallback to description if no generated content
                return self.current_scene.description if self.current_scene.description else "(No content)"
            return "(No scene selected)"
        elif change_type in ["regenerate_items", "edit_items"]:
            return [item.prompt for item in self.selected_items] if self.selected_items else []
        return ""
    
    def get_after_data(self, change_type: str, change_data: dict) -> Any:
        """Get the proposed state after changes."""
        if change_type == "edit_character_outline":
            # Get proposed character outline
            character_name = change_data.get("character_name", "")
            new_outline = change_data.get("character_outline", "")
            new_growth_arc = change_data.get("character_growth_arc", "")
            
            result = f"Character: {character_name if character_name else 'Unknown'}\n\n"
            if new_outline:
                result += f"New Outline:\n{new_outline}\n\n"
            else:
                result += "New Outline: (unchanged)\n\n"
            if new_growth_arc:
                result += f"New Growth Arc:\n{new_growth_arc}"
            else:
                result += "New Growth Arc: (unchanged)"
            return result
        
        # Check if this is a character_focus edit (even if change_type is wrong)
        edits = change_data.get("edits", {})
        if isinstance(edits, dict) and "character_focus" in edits:
            character_focus = edits["character_focus"]
            try:
                if isinstance(character_focus, str):
                    return f"Character Focus: {character_focus.strip()}"
                elif isinstance(character_focus, list):
                    # Ensure all items are strings before joining
                    character_focus_strs = [str(cf).strip() for cf in character_focus if cf]
                    return f"Character Focus: {', '.join(character_focus_strs) if character_focus_strs else '(none)'}"
                else:
                    return f"Character Focus: {str(character_focus)}"
            except Exception as e:
                # Fallback if there's any error formatting
                return f"Character Focus: {str(character_focus)}"
        
        # Also check if change_type is add_items but might be a character edit
        if change_type == "add_items":
            # Check if new_items might contain character information
            new_items = change_data.get("new_items", [])
            if isinstance(new_items, list) and len(new_items) > 0:
                # Try to infer if this is character-related
                # For now, return a placeholder - preview might not be fully supported for add_items
                return f"Add {len(new_items)} item(s)"
            return "Add items"
        
        if change_type in ["regenerate_scene", "edit_scene"]:
            new_content = change_data.get("new_content", "")
            
            # For paragraph edits, ensure we return the full merged scene content for preview
            if new_content and self.current_scene:
                user_request = change_data.get("user_request", "").lower()
                paragraph_index = change_data.get("paragraph_index")
                is_paragraph_edit = (
                    paragraph_index is not None or
                    any(keyword in user_request for keyword in [
                        "paragraph", "paragragh", "option", "options", "alternative",
                        "alternatives", "version", "versions"
                    ])
                )
                
                if is_paragraph_edit:
                    # Get existing scene content
                    existing_content = ""
                    if self.current_scene.metadata and self.current_scene.metadata.get("generated_content"):
                        existing_content = self.current_scene.metadata["generated_content"]
                    else:
                        existing_content = self.current_scene.description
                    
                    if existing_content:
                        import re
                        existing_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                        new_paragraphs = [p.strip() for p in re.sub(r'^\[\d+\]\s+', '', new_content, flags=re.MULTILINE).split('\n\n') if p.strip()]
                        
                        # If new content has fewer paragraphs, it's likely just a paragraph option
                        # Merge it into the full scene content
                        if len(new_paragraphs) < len(existing_paragraphs) and len(existing_paragraphs) > 1:
                            # Extract paragraph index if not provided
                            if paragraph_index is None:
                                paragraph_index = 0
                                para_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request)
                                if para_match:
                                    para_num = int(para_match.group(1) or para_match.group(2) or para_match.group(3))
                                    paragraph_index = para_num - 1
                                elif "second" in user_request or "paragraph 2" in user_request:
                                    paragraph_index = 1
                                elif "third" in user_request or "paragraph 3" in user_request:
                                    paragraph_index = 2
                                elif "fourth" in user_request or "paragraph 4" in user_request:
                                    paragraph_index = 3
                                elif "fifth" in user_request or "paragraph 5" in user_request:
                                    paragraph_index = 4
                            
                            if paragraph_index < 0:
                                paragraph_index = 0
                            if paragraph_index >= len(existing_paragraphs):
                                paragraph_index = len(existing_paragraphs) - 1
                            
                            # Merge: replace only the specified paragraph
                            # If new_paragraphs has the same count, the content is already complete
                            if len(new_paragraphs) == len(existing_paragraphs):
                                # Full scene was provided - use it directly
                                return '\n\n'.join(new_paragraphs)
                            else:
                                # Only a single paragraph was provided - merge it into existing content
                                reconstructed = existing_paragraphs.copy()
                                replacement = new_paragraphs[0] if new_paragraphs else new_content.strip()
                                if replacement and paragraph_index < len(reconstructed):
                                    reconstructed[paragraph_index] = replacement
                                return '\n\n'.join(reconstructed)
            
            return new_content
        elif change_type == "regenerate_items":
            return change_data.get("new_items", [])
        return ""
    
    def apply_change(self, change_type: str, change_data: dict):
        """Apply a change to the screenplay."""
        try:
            # Handle character outline edits - they don't need generation
            if change_type == "edit_character_outline":
                # Verify we have the necessary data
                character_name = change_data.get("character_name", "")
                character_outline = change_data.get("character_outline", "")
                character_growth_arc = change_data.get("character_growth_arc", "")
                
                # Debug: Check if data exists
                if not character_name:
                    # Try to extract from user_request or description if available
                    user_request = change_data.get("user_request", "")
                    description = change_data.get("description", "")
                    
                    # Try to find character name from context
                    if self.screenplay and self.screenplay.story_outline:
                        characters = self.screenplay.story_outline.get("characters", [])
                        if characters and isinstance(characters, list):
                            # Look for character name in user request or description
                            import re
                            search_text = (user_request + " " + description).lower()
                            for char in characters:
                                if isinstance(char, dict):
                                    char_name = char.get("name", "").strip()
                                    if char_name and char_name.lower() in search_text:
                                        character_name = char_name
                                        change_data["character_name"] = character_name
                                        break
                
                if not character_name:
                    QMessageBox.warning(self, "Error", "No character name provided. Please specify which character's outline to edit.")
                    return
                
                if not character_outline and not character_growth_arc:
                    QMessageBox.warning(self, "Error", "No character outline or growth arc provided in the suggestion.")
                    return
                
                # Debug: Log what we're about to apply
                print(f"DEBUG apply_change: character_name={character_name}, outline_len={len(character_outline) if character_outline else 0}, growth_len={len(character_growth_arc) if character_growth_arc else 0}")
                print(f"DEBUG apply_change: change_data keys before emit: {list(change_data.keys())}")
                
                # Ensure all data is in change_data
                change_data["character_name"] = character_name
                if character_outline:
                    change_data["character_outline"] = character_outline
                if character_growth_arc:
                    change_data["character_growth_arc"] = character_growth_arc
                
                print(f"DEBUG apply_change: About to emit signal with change_type={change_type}")
                print(f"DEBUG apply_change: Final change_data keys: {list(change_data.keys())}")
                if character_outline:
                    print(f"DEBUG apply_change: character_outline preview: {character_outline[:100]}...")
                
                # Emit signal to apply the change (main window will handle it)
                self.changes_applied.emit(change_type, change_data)
                print(f"DEBUG apply_change: Signal emitted successfully")
                self.add_message("system", f"Character outline for {character_name} has been updated.")
                return
            
            # For regenerate operations, we need to call AI methods first if not already generated
            if change_type in ["regenerate_scene", "edit_scene"] and self.current_scene and self.ai_generator:
                # Only generate if not already generated (e.g., during preview)
                # If new_content exists, we'll let on_chat_changes_applied handle merging for paragraph edits
                if "new_content" not in change_data or not change_data.get("new_content"):
                    user_request = change_data.get("user_request", "")
                    # If user_request is empty, try to build it from edits or description
                    if not user_request or change_type == "edit_scene":
                        edits = change_data.get("edits", {})
                        if isinstance(edits, dict) and "new_content" in edits:
                            new_content = edits.get("new_content", "")
                            if new_content and new_content.strip():
                                change_data["new_content"] = new_content
                                user_request = f"Use this content: {new_content[:100]}"
                        elif isinstance(edits, list) and edits:
                            user_request = "Apply these changes: " + " ".join(str(e) for e in edits[:2])
                        
                        # Fallback to description if still empty
                        if not user_request:
                            description = change_data.get("description", "")
                            if description:
                                user_request = description
                            else:
                                user_request = "Edit this scene" if change_type == "edit_scene" else "Regenerate this scene"
                    
                    new_content = self.ai_generator.regenerate_scene_content(
                        self.current_scene, user_request, self.screenplay
                    )
                    change_data["new_content"] = new_content
            elif change_type == "regenerate_items" and self.selected_items and self.ai_generator and self.current_scene:
                # Only generate if not already generated (e.g., during preview)
                if "new_items" not in change_data or not change_data.get("new_items"):
                    user_request = change_data.get("user_request", "Regenerate these items")
                    new_items = self.ai_generator.regenerate_storyboard_items(
                        self.current_scene, self.selected_items, user_request, self.screenplay
                    )
                    change_data["new_items"] = new_items
            
            # Verify we have the necessary data before emitting
            if change_type == "edit_character_outline":
                # Already handled above
                pass
            elif change_type in ["regenerate_scene", "edit_scene"]:
                # Check if this is a character_focus edit - those don't need new_content
                edits = change_data.get("edits", {})
                is_char_focus_edit = isinstance(edits, dict) and "character_focus" in edits
                
                if not is_char_focus_edit and not change_data.get("new_content"):
                    QMessageBox.warning(self, "Error", "No content to apply. Please try again.")
                    return
            elif change_type == "regenerate_items":
                if not change_data.get("new_items"):
                    QMessageBox.warning(self, "Error", "No items to apply. Please try again.")
                    return
            
            # Emit signal to apply changes
            self.changes_applied.emit(change_type, change_data)
            self.add_message("system", f"Changes applied: {change_type.replace('_', ' ')}")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            QMessageBox.critical(self, "Error", f"Failed to apply changes:\n{str(e)}\n\nDetails:\n{error_details}")
            self.add_message("system", f"Error applying changes: {str(e)}", is_error=True)
    
    def remove_thinking_indicator(self):
        """Remove the 'Thinking...' indicator from chat."""
        # Remove last widget if it's a thinking indicator
        if self.chat_layout.count() > 0:
            last_item = self.chat_layout.itemAt(self.chat_layout.count() - 1)
            if last_item:
                widget = last_item.widget()
                if widget and isinstance(widget, QFrame):
                    label = widget.findChild(QLabel)
                    if label and "Thinking" in label.text():
                        self.chat_layout.removeWidget(widget)
                        widget.deleteLater()
    
    def clear_chat(self):
        """Clear the chat history."""
        reply = QMessageBox.question(
            self, "Clear Chat",
            "Clear all chat history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Collect all widgets first
                widgets_to_delete = []
                while self.chat_layout.count():
                    item = self.chat_layout.takeAt(0)
                    if item and item.widget():
                        widget = item.widget()
                        self.chat_layout.removeWidget(widget)
                        widgets_to_delete.append(widget)
                
                # Delete widgets safely
                for widget in widgets_to_delete:
                    widget.setParent(None)
                    widget.deleteLater()
                
                # Clear data
                self.chat_history.clear()
                if hasattr(self, '_suggestions'):
                    self._suggestions = []
            except Exception as e:
                # If something goes wrong, at least clear the data
                self.chat_history.clear()
                if hasattr(self, '_suggestions'):
                    self._suggestions = []
                # Show error but don't crash
                QMessageBox.warning(self, "Error", f"Error clearing chat display: {str(e)}")

