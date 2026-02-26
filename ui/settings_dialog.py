"""
Settings dialog for configuring AI and application preferences.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QLabel, QSpinBox, QComboBox, QCheckBox,
    QMessageBox, QTabWidget, QWidget, QTextEdit, QApplication,
    QSlider, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from typing import Optional
import urllib.request
import json
import urllib.error

from config import config

class SettingsDialog(QDialog):
    """Dialog for configuring application settings including AI configuration."""
    
    def __init__(self, parent=None, show_tab: str = "all"):
        """
        Initialize settings dialog.
        
        Args:
            parent: Parent widget
            show_tab: Which tab to show - "ai", "ui", or "all" (default: "all")
        """
        super().__init__(parent)
        self.show_tab = show_tab
        # Store base URLs per provider to restore when switching back
        self.provider_base_urls = {}
        # Flag to prevent updating stored URL when programmatically setting text
        self._updating_base_url = False
        # Set window title based on which tab to show
        if show_tab == "ai":
            self.setWindowTitle("AI Config")
        elif show_tab == "ui":
            self.setWindowTitle("UI Config")
        else:
            self.setWindowTitle("Settings")
        self.setModal(True)
        # Set window size based on which dialog is shown
        if show_tab == "ui":
            self.resize(450, 350)  # Smaller size for UI Config
        else:
            self.resize(600, 650)
        self.init_ui()
        self.load_current_settings()
        
        # Show specific tab if requested (only if using tabs for full Settings dialog)
        if self.show_tab == "all" and hasattr(self, 'tabs'):
            self.tabs.setCurrentIndex(0)  # AI Settings tab
    
    def init_ui(self):
        """Initialize the settings dialog UI."""
        layout = QVBoxLayout(self)
        
        # For AI Config or UI Config, add content directly without tabs
        if self.show_tab == "ai":
            # Create AI settings content directly
            self.create_ai_content(layout)
        elif self.show_tab == "ui":
            # Create UI settings content directly
            self.create_ui_content(layout)
        else:
            # Create tab widget for full Settings dialog (both tabs)
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)
            
            # AI Settings tab
            self.create_ai_tab()
            
            # UI Settings tab
            self.create_ui_tab()
            
            # Whitelists tab
            self.create_whitelists_tab()
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        # Test AI Connection button (only show if AI widgets exist)
        if self.show_tab != "ui":
            test_ai_btn = QPushButton("Test AI Connection")
            test_ai_btn.clicked.connect(self.test_ai_connection)
            buttons_layout.addWidget(test_ai_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setDefault(True)
        buttons_layout.addWidget(save_btn)
        
        layout.addLayout(buttons_layout)
    
    def _create_ai_widgets(self, parent_layout):
        """Create AI settings widgets and add them to the given layout."""
        # AI Provider Selection
        provider_group = QGroupBox("AI Provider")
        provider_layout = QFormLayout(provider_group)
        
        # Provider selection
        self.provider_combo = QComboBox()
        self.provider_combo.addItems([
            "OpenAI",
            "Anthropic",
            "Together AI",
            "OpenRouter",
            "Hugging Face",
            "Custom",
            "Ollama Cloud",
            "Local (Ollama/LM Studio)"
        ])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addRow("Provider:", self.provider_combo)
        
        # Base URL (for providers that need custom URLs)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://localhost:11434/v1 (Ollama default)")
        # Update stored base URL when user manually edits it
        self.base_url_edit.textChanged.connect(self.on_base_url_changed)
        provider_layout.addRow("Base URL:", self.base_url_edit)
        
        # Base URL help label
        self.base_url_help = QLabel("For Ollama: http://localhost:11434/v1\nFor LM Studio: http://localhost:1234/v1")
        self.base_url_help.setWordWrap(True)
        self.base_url_help.setStyleSheet("color: gray; font-size: 10pt;")
        provider_layout.addRow("", self.base_url_help)
        
        parent_layout.addWidget(provider_group)
        
        # AI Settings
        ai_settings_group = QGroupBox("AI Configuration")
        ai_settings_layout = QFormLayout(ai_settings_group)
        
        # API Key (optional for local)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter your API key (optional for local AI)")
        ai_settings_layout.addRow("API Key:", self.api_key_edit)
        
        # Show/Hide API Key button
        show_key_btn = QPushButton("Show/Hide")
        show_key_btn.clicked.connect(self.toggle_api_key_visibility)
        ai_settings_layout.addRow("", show_key_btn)
        
        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)  # Allow typing custom model names
        self.model_combo.addItems([
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "llama2",
            "llama3",
            "llama3.2",
            "mistral",
            "codellama",
            "phi",
            "qwen3",
            "deepseek-r1:14b",
            "deepseek-r1"
        ])
        
        # Model row with refresh button
        model_layout = QHBoxLayout()
        model_layout.addWidget(self.model_combo)
        
        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.setMaximumWidth(70)
        self.refresh_models_btn.clicked.connect(self.refresh_ollama_models)
        self.refresh_models_btn.setToolTip("Fetch available models from Ollama")
        model_layout.addWidget(self.refresh_models_btn)
        
        ai_settings_layout.addRow("Model:", model_layout)
        
        # Temperature
        self.temperature_spinbox = QSpinBox()
        self.temperature_spinbox.setRange(0, 100)
        self.temperature_spinbox.setValue(70)
        self.temperature_spinbox.setSuffix("%")
        ai_settings_layout.addRow("Temperature:", self.temperature_spinbox)
        
        # Max tokens (slider with 2000-token steps: 2000, 4000, 6000, ..., 60000)
        max_tokens_row = QHBoxLayout()
        self.max_tokens_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_tokens_slider.setMinimum(0)  # Index 0 = 2000 tokens
        self.max_tokens_slider.setMaximum(29)  # Index 29 = 60000 tokens (30 steps × 2000)
        self.max_tokens_slider.setSingleStep(1)   # One step = 2000 tokens
        self.max_tokens_slider.setPageStep(5)    # Page = 10000 tokens (5 steps)
        self.max_tokens_slider.setValue(0)  # Default to index 0 (2000 tokens)
        self.max_tokens_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.max_tokens_slider.setTickInterval(5)  # Show ticks every 5 steps (10000 tokens)
        self.max_tokens_slider.setMinimumWidth(200)
        self.max_tokens_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_tokens_slider.valueChanged.connect(self._on_max_tokens_slider_changed)
        max_tokens_row.addWidget(self.max_tokens_slider)
        self.max_tokens_value_label = QLabel("2000")
        self.max_tokens_value_label.setMinimumWidth(60)
        self.max_tokens_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        max_tokens_row.addWidget(self.max_tokens_value_label)
        ai_settings_layout.addRow("Max Tokens:", max_tokens_row)
        
        parent_layout.addWidget(ai_settings_group)
        
        # Video Model Capabilities (migrated to per-project Story Settings tab)
        video_cap_group = QGroupBox("Video Model Capabilities")
        video_cap_layout = QFormLayout(video_cap_group)
        video_cap_note = QLabel(
            "Multi-shot, max duration, aspect ratio and other cinematic controls "
            "are now per-project settings.\nConfigure them in the Story Settings tab."
        )
        video_cap_note.setWordWrap(True)
        video_cap_layout.addRow(video_cap_note)
        parent_layout.addWidget(video_cap_group)
        
        # Help text (dynamic based on provider)
        help_group = QGroupBox("Setup Help")
        help_layout = QVBoxLayout(help_group)
        
        self.help_text = QTextEdit()
        self.help_text.setMaximumHeight(180)
        self.help_text.setReadOnly(True)
        self.help_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # Show scrollbar when needed
        self.help_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # No horizontal scrollbar
        self.help_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)  # Enable text wrapping
        help_layout.addWidget(self.help_text)
        
        parent_layout.addWidget(help_group)
        
        # Test Connection
        test_group = QGroupBox("Connection Test")
        test_layout = QVBoxLayout(test_group)
        
        self.test_result_label = QLabel("Click 'Test AI Connection' to verify your settings")
        self.test_result_label.setWordWrap(True)
        test_layout.addWidget(self.test_result_label)
        
        parent_layout.addWidget(test_group)
        
        parent_layout.addStretch()
        
        # Initialize help text
        self.update_help_text()
    
    def create_ai_content(self, parent_layout):
        """Create AI settings content and add directly to parent layout (for AI Config without tabs)."""
        self._create_ai_widgets(parent_layout)
    
    def create_ai_tab(self):
        """Create the AI settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._create_ai_widgets(layout)
        self.tabs.addTab(tab, "AI Settings")
    
    def _create_ui_widgets(self, parent_layout):
        """Create UI settings widgets and add them to the given layout."""
        # Theme Settings
        theme_group = QGroupBox("Appearance")
        theme_layout = QFormLayout(theme_group)
        
        # Theme selection
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        theme_layout.addRow("Theme:", self.theme_combo)
        
        # Font size
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 24)
        self.font_size_spinbox.setValue(12)
        theme_layout.addRow("Font Size:", self.font_size_spinbox)
        
        # Show line numbers
        self.show_line_numbers_checkbox = QCheckBox("Show line numbers in editors")
        theme_layout.addRow("", self.show_line_numbers_checkbox)
        
        parent_layout.addWidget(theme_group)
        
        # Editor Settings
        editor_group = QGroupBox("Editor Settings")
        editor_layout = QFormLayout(editor_group)
        
        # Auto-save interval
        self.auto_save_spinbox = QSpinBox()
        self.auto_save_spinbox.setRange(60, 3600)
        self.auto_save_spinbox.setValue(300)
        self.auto_save_spinbox.setSuffix(" seconds")
        editor_layout.addRow("Auto-save Interval:", self.auto_save_spinbox)
        
        parent_layout.addWidget(editor_group)
    
    def create_ui_content(self, parent_layout):
        """Create UI settings content and add directly to parent layout (for UI Config without tabs)."""
        self._create_ui_widgets(parent_layout)
    
    def create_ui_tab(self):
        """Create the UI settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._create_ui_widgets(layout)
        self.tabs.addTab(tab, "UI Settings")
    
    def create_whitelists_tab(self):
        """Create the Whitelists management tab for custom Action verbs and SFX."""
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        from core.markup_whitelist import (
            load_action_whitelist, load_sfx_whitelist,
            remove_from_action_whitelist, remove_from_sfx_whitelist,
        )
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info label
        info_label = QLabel(
            "Manage user-added Action verbs and SFX. Built-in entries are not shown.\n"
            "Only user-added entries can be removed here."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
        layout.addWidget(info_label)
        
        # Two columns: Action Whitelist and SFX Whitelist
        columns_layout = QHBoxLayout()
        
        # ── Action Whitelist ──
        action_group = QGroupBox("Custom Action Verbs")
        action_layout = QVBoxLayout()
        
        self.action_whitelist_list = QListWidget()
        self.action_whitelist_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        action_layout.addWidget(self.action_whitelist_list)
        
        action_btn_layout = QHBoxLayout()
        remove_action_btn = QPushButton("Remove Selected")
        
        def on_remove_action():
            items = self.action_whitelist_list.selectedItems()
            for item in items:
                verb = item.text()
                remove_from_action_whitelist(verb)
            self._refresh_whitelist_lists()
        
        remove_action_btn.clicked.connect(on_remove_action)
        action_btn_layout.addWidget(remove_action_btn)
        action_btn_layout.addStretch()
        
        count_label_action = QLabel("")
        self._action_count_label = count_label_action
        action_btn_layout.addWidget(count_label_action)
        
        action_layout.addLayout(action_btn_layout)
        action_group.setLayout(action_layout)
        columns_layout.addWidget(action_group)
        
        # ── SFX Whitelist ──
        sfx_group = QGroupBox("Custom SFX")
        sfx_layout = QVBoxLayout()
        
        self.sfx_whitelist_list = QListWidget()
        self.sfx_whitelist_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        sfx_layout.addWidget(self.sfx_whitelist_list)
        
        sfx_btn_layout = QHBoxLayout()
        remove_sfx_btn = QPushButton("Remove Selected")
        
        def on_remove_sfx():
            items = self.sfx_whitelist_list.selectedItems()
            for item in items:
                sfx = item.text()
                remove_from_sfx_whitelist(sfx)
            self._refresh_whitelist_lists()
        
        remove_sfx_btn.clicked.connect(on_remove_sfx)
        sfx_btn_layout.addWidget(remove_sfx_btn)
        sfx_btn_layout.addStretch()
        
        count_label_sfx = QLabel("")
        self._sfx_count_label = count_label_sfx
        sfx_btn_layout.addWidget(count_label_sfx)
        
        sfx_layout.addLayout(sfx_btn_layout)
        sfx_group.setLayout(sfx_layout)
        columns_layout.addWidget(sfx_group)
        
        layout.addLayout(columns_layout)
        layout.addStretch()
        
        self.tabs.addTab(tab, "Whitelists")
        
        # Populate lists
        self._refresh_whitelist_lists()
    
    def _refresh_whitelist_lists(self):
        """Refresh the whitelist list widgets with current data from disk."""
        from core.markup_whitelist import load_action_whitelist, load_sfx_whitelist
        
        if hasattr(self, 'action_whitelist_list'):
            self.action_whitelist_list.clear()
            action_entries = sorted(load_action_whitelist())
            for entry in action_entries:
                self.action_whitelist_list.addItem(entry)
            if hasattr(self, '_action_count_label'):
                self._action_count_label.setText(f"{len(action_entries)} entries")
        
        if hasattr(self, 'sfx_whitelist_list'):
            self.sfx_whitelist_list.clear()
            sfx_entries = sorted(load_sfx_whitelist())
            for entry in sfx_entries:
                self.sfx_whitelist_list.addItem(entry)
            if hasattr(self, '_sfx_count_label'):
                self._sfx_count_label.setText(f"{len(sfx_entries)} entries")
    
    def toggle_api_key_visibility(self):
        """Toggle API key visibility."""
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    
    def on_base_url_changed(self, text: str):
        """Update stored base URL for current provider when user edits it."""
        # Only update if this is a user edit, not a programmatic change
        if self._updating_base_url:
            return
        if hasattr(self, '_current_provider') and self._current_provider and hasattr(self, 'provider_base_urls'):
            if text.strip():
                self.provider_base_urls[self._current_provider] = text.strip()
    
    def _on_max_tokens_slider_changed(self, value: int):
        """Update the max tokens value label when the slider moves.
        
        Slider uses index 0-29 representing 2000-60000 tokens in steps of 2000.
        """
        if hasattr(self, 'max_tokens_value_label'):
            actual_tokens = (value + 1) * 2000  # Index 0 = 2000, index 1 = 4000, ..., index 29 = 60000
            self.max_tokens_value_label.setText(str(actual_tokens))
    
    def on_provider_changed(self, provider_text: str):
        """Handle provider selection change."""
        # Only process if AI widgets exist (not in UI Config mode)
        if not hasattr(self, 'provider_combo') or not hasattr(self, 'base_url_edit'):
            return
        
        # Safety check: ensure provider_text is valid
        if not provider_text or not isinstance(provider_text, str):
            return
        
        # Store current base URL for the previous provider (if we have a previous provider)
        if hasattr(self, '_current_provider') and self._current_provider:
            current_url = self.base_url_edit.text().strip()
            if current_url:
                self.provider_base_urls[self._current_provider] = current_url
        
        # Update current provider
        self._current_provider = provider_text
        
        is_local = provider_text == "Local (Ollama/LM Studio)"
        is_ollama_cloud = provider_text == "Ollama Cloud"
        is_custom = provider_text == "Custom"
        is_openai = provider_text == "OpenAI"
        is_anthropic = provider_text == "Anthropic"
        needs_base_url = provider_text in ["Local (Ollama/LM Studio)", "Ollama Cloud", "Together AI", "OpenRouter", "Hugging Face", "Custom", "OpenAI", "Anthropic"]
        
        # Set base URLs for providers - use stored value if available, otherwise use default
        # Set flag to prevent textChanged from updating stored value during programmatic change
        self._updating_base_url = True
        try:
            if provider_text == "Anthropic":
                stored_url = self.provider_base_urls.get(provider_text, "https://api.anthropic.com")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("Anthropic API endpoint: https://api.anthropic.com")
            elif provider_text == "Together AI":
                stored_url = self.provider_base_urls.get(provider_text, "https://api.together.xyz/v1")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("Together AI API endpoint: https://api.together.xyz/v1")
            elif provider_text == "OpenRouter":
                stored_url = self.provider_base_urls.get(provider_text, "https://openrouter.ai/api/v1")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("OpenRouter API endpoint: https://openrouter.ai/api/v1")
            elif provider_text == "Hugging Face":
                stored_url = self.provider_base_urls.get(provider_text, "https://api-inference.huggingface.co/v1/")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("Hugging Face Inference API endpoint: https://api-inference.huggingface.co/v1/")
            elif is_custom:
                # For custom, use stored value or leave empty for user to enter
                stored_url = self.provider_base_urls.get(provider_text, "")
                if stored_url:
                    self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("Enter the base URL for your custom OpenAI-compatible API provider (e.g., https://api.example.com/v1)")
            elif is_ollama_cloud:
                # Ollama Cloud: raw base URL, do NOT include /v1
                stored_url = self.provider_base_urls.get(provider_text, "https://ollama.com/api")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("Ollama Cloud API endpoint: https://ollama.com/api")
            elif is_local:
                # For local, use stored value or default
                stored_url = self.provider_base_urls.get(provider_text)
                if stored_url:
                    self.base_url_edit.setText(stored_url)
                elif not self.base_url_edit.text().strip():
                    self.base_url_edit.setText("http://localhost:11434/v1")
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("For Ollama: http://localhost:11434/v1\nFor LM Studio: http://localhost:1234/v1")
            elif is_openai:
                # For OpenAI, use stored value or default
                stored_url = self.provider_base_urls.get(provider_text, "https://api.openai.com/v1")
                self.base_url_edit.setText(stored_url)
                if hasattr(self, 'base_url_help'):
                    self.base_url_help.setText("OpenAI default API endpoint: https://api.openai.com/v1")
        finally:
            self._updating_base_url = False
        
        # Enable/disable base URL field (after setting/clearing the value)
        self.base_url_edit.setEnabled(needs_base_url)
        
        # Show/hide refresh button (Local and Ollama Cloud can fetch model list from /api/tags)
        if hasattr(self, 'refresh_models_btn'):
            self.refresh_models_btn.setVisible(is_local or is_ollama_cloud)
        
        # Update API key placeholder
        if hasattr(self, 'api_key_edit'):
            if is_ollama_cloud:
                self.api_key_edit.setPlaceholderText("Optional (if your Ollama Cloud instance requires a key)")
            elif is_local:
                self.api_key_edit.setPlaceholderText("Optional (most local AI don't need a key)")
                # Auto-refresh models when switching to local
                if hasattr(self, 'refresh_ollama_models'):
                    self.refresh_ollama_models()
            elif is_custom:
                self.api_key_edit.setPlaceholderText("Enter your API key for the custom provider")
            elif provider_text == "Anthropic":
                self.api_key_edit.setPlaceholderText("Enter your Anthropic API key")
            elif provider_text == "Together AI":
                self.api_key_edit.setPlaceholderText("Enter your Together AI API key")
            elif provider_text == "OpenRouter":
                self.api_key_edit.setPlaceholderText("Enter your OpenRouter API key")
            elif provider_text == "Hugging Face":
                self.api_key_edit.setPlaceholderText("Enter your Hugging Face API key (HF_TOKEN)")
            else:
                self.api_key_edit.setPlaceholderText("Enter your OpenAI API key")
        
        # Update help text
        if hasattr(self, 'help_text'):
            self.update_help_text()
    
    def refresh_ollama_models(self):
        """Fetch available models from Ollama (local or Ollama Cloud) and update the dropdown."""
        # Only refresh if widgets exist (not in UI Config mode)
        if not hasattr(self, 'base_url_edit') or not hasattr(self, 'model_combo') or not hasattr(self, 'test_result_label'):
            return

        base_url = self.base_url_edit.text().strip()
        provider_text = self.provider_combo.currentText() if hasattr(self, 'provider_combo') else ""
        is_ollama_cloud = provider_text == "Ollama Cloud"
        if not base_url:
            base_url = "http://localhost:11434/v1" if not is_ollama_cloud else ""

        if is_ollama_cloud and not base_url:
            self.test_result_label.setText("❌ Enter your Ollama Cloud base URL first")
            return

        # Build tags URL: if base already ends with /api (e.g. https://ollama.com/api), use .../tags not .../api/tags
        ollama_url = base_url.rstrip("/") if is_ollama_cloud else base_url.replace("/v1", "").rstrip("/")
        if is_ollama_cloud and ollama_url.endswith("/api"):
            api_url = f"{ollama_url}/tags"
        else:
            api_url = f"{ollama_url}/api/tags"

        try:
            # Store current selection
            current_model = self.model_combo.currentText()

            if is_ollama_cloud:
                # Ollama Cloud: use requests so we can send API key and get clearer errors
                import requests as req_lib
                headers = {"Accept": "application/json"}
                api_key = self.api_key_edit.text().strip() if hasattr(self, 'api_key_edit') else ""
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = req_lib.get(api_url, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            else:
                # Local Ollama: urllib is sufficient
                req = urllib.request.Request(api_url, headers={'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())

            if "models" in data and data["models"]:
                # Get model names
                ollama_models = [model["name"] for model in data["models"]]
                
                # Keep OpenAI models at the top, add Ollama models
                openai_models = ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"]
                
                # Clear and repopulate
                self.model_combo.clear()
                self.model_combo.addItems(openai_models)
                self.model_combo.insertSeparator(len(openai_models))
                self.model_combo.addItems(ollama_models)
                
                # Restore selection if it exists, otherwise select first Ollama model
                index = self.model_combo.findText(current_model)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
                elif ollama_models:
                    # Select first Ollama model
                    self.model_combo.setCurrentText(ollama_models[0])
                
                self.test_result_label.setText(f"✅ Found {len(ollama_models)} Ollama model(s)")
            else:
                self.test_result_label.setText("⚠️ No models found in Ollama. Run 'ollama pull <model>'")

        except urllib.error.URLError as e:
            self.test_result_label.setText(f"❌ Cannot connect to Ollama at {ollama_url}")
        except Exception as e:
            err = str(e)
            if is_ollama_cloud:
                if "401" in err or "Unauthorized" in err or "authentication" in err.lower():
                    self.test_result_label.setText("❌ Ollama Cloud: check your API key in Settings.")
                elif "404" in err or "Not Found" in err:
                    self.test_result_label.setText(f"❌ Tags endpoint not found at {api_url}")
                elif "connection" in err.lower() or "timed out" in err.lower():
                    self.test_result_label.setText(f"❌ Cannot connect to {ollama_url}. Check URL and network.")
                else:
                    self.test_result_label.setText(f"❌ Error: {err[:60]}")
            else:
                self.test_result_label.setText(f"❌ Error fetching models: {err[:50]}")
    
    def update_help_text(self):
        """Update help text based on selected provider."""
        # Only update if widgets exist (not in UI Config mode)
        if not hasattr(self, 'provider_combo') or not hasattr(self, 'help_text'):
            return
        
        provider_text = self.provider_combo.currentText()
        if not provider_text:
            return
        
        is_local = provider_text == "Local (Ollama/LM Studio)"
        
        if is_local:
            html = """
            <h3>Local AI Setup (Ollama/LM Studio):</h3>
            <ol>
            <li><b>Install Ollama:</b> Download from <a href="https://ollama.ai">ollama.ai</a> or install LM Studio</li>
            <li><b>Start the server:</b> Ollama runs automatically. For LM Studio, enable "Local Server" in settings</li>
            <li><b>Download a model:</b> Run <code>ollama pull llama3</code> in terminal (or use LM Studio UI)</li>
            <li><b>Configure Base URL:</b> Default is <code>http://localhost:11434/v1</code> for Ollama</li>
            <li><b>Select model:</b> Choose the model you downloaded (e.g., llama3, mistral, deepseek-r1:14b)</li>
            </ol>
            <p><b>Note:</b> No API key needed for local AI. All processing happens on your computer.</p>
            """
        elif provider_text == "Together AI":
            html = """
            <h3>Together AI Setup:</h3>
            <ol>
            <li>Go to <a href="https://together.ai">together.ai</a></li>
            <li>Sign up or log in to your account</li>
            <li>Navigate to API Keys section</li>
            <li>Create a new API key</li>
            <li>Copy the key and paste it above</li>
            <li><b>Base URL:</b> Already set to <code>https://api.together.xyz/v1</code></li>
            <li><b>Models:</b> Use model names like <code>meta-llama/Llama-3-70b-hf</code>, <code>mistralai/Mixtral-8x7B-Instruct-v0.1</code></li>
            </ol>
            <p><b>Note:</b> Together AI provides access to many open-source models with fast inference.</p>
            """
        elif provider_text == "OpenRouter":
            html = """
            <h3>OpenRouter Setup:</h3>
            <ol>
            <li>Go to <a href="https://openrouter.ai">openrouter.ai</a></li>
            <li>Sign up or log in to your account</li>
            <li>Navigate to Keys section</li>
            <li>Create a new API key</li>
            <li>Copy the key and paste it above</li>
            <li><b>Base URL:</b> Already set to <code>https://openrouter.ai/api/v1</code></li>
            <li><b>Models:</b> Use model names like <code>openai/gpt-4</code>, <code>anthropic/claude-3-opus</code>, <code>meta-llama/llama-3-70b-instruct</code></li>
            </ol>
            <p><b>Note:</b> OpenRouter provides access to many AI models from different providers through one API.</p>
            """
        elif provider_text == "Hugging Face":
            html = """
            <h3>Hugging Face Setup:</h3>
            <ol>
            <li>Go to <a href="https://huggingface.co">huggingface.co</a></li>
            <li>Sign up or log in to your account</li>
            <li>Navigate to Settings → Access Tokens</li>
            <li>Create a new token with "Read" permissions</li>
            <li>Copy the token and paste it above</li>
            <li><b>Base URL:</b> Already set to <code>https://api-inference.huggingface.co/v1/</code></li>
            <li><b>Models:</b> Use model names like <code>meta-llama/Llama-3-8b</code>, <code>mistralai/Mistral-7B-Instruct-v0.2</code></li>
            </ol>
            <p><b>Note:</b> Hugging Face provides access to many open-source models. Some models may require you to accept terms on the model page first.</p>
            """
        elif provider_text == "Anthropic":
            html = """
            <h3>Anthropic (Claude) Setup:</h3>
            <ol>
            <li>Go to <a href="https://console.anthropic.com/">console.anthropic.com</a></li>
            <li>Sign up or log in to your account</li>
            <li>Navigate to API Keys section</li>
            <li>Create a new API key</li>
            <li>Copy the key and paste it above</li>
            <li><b>Base URL:</b> Already set to <code>https://api.anthropic.com</code> (change only if using a proxy)</li>
            <li><b>Models:</b> Use model names like <code>claude-sonnet-4-20250514</code>, <code>claude-3-5-sonnet-20241022</code>, <code>claude-3-5-haiku-20241022</code>, <code>claude-3-opus-20240229</code></li>
            </ol>
            <p><b>Note:</b> Anthropic provides the Claude family of models. Your API key is stored securely on your local machine.</p>
            """
        elif provider_text == "Ollama Cloud":
            html = """
            <h3>Ollama Cloud Setup:</h3>
            <ol>
            <li><b>Base URL:</b> Enter your Ollama Cloud base URL as provided (do not include <code>/v1</code>)</li>
            <li><b>API Key:</b> Optional — only if your Ollama Cloud instance requires authentication</li>
            <li><b>Model:</b> Enter the model name (e.g. llama3, mistral) available on your Ollama Cloud instance</li>
            </ol>
            <p><b>Note:</b> Ollama Cloud uses the native Ollama API. The app will call <code>/api/chat</code> on your base URL.</p>
            """
        elif provider_text == "Custom":
            html = """
            <h3>Custom Provider Setup:</h3>
            <ol>
            <li><b>Base URL:</b> Enter the base URL for your OpenAI-compatible API provider</li>
            <li><b>API Key:</b> Enter your API key for the custom provider</li>
            <li><b>Model:</b> Enter the model name/identifier used by your provider</li>
            </ol>
            <p><b>Note:</b> This option allows you to use any OpenAI-compatible API provider. The provider must support the OpenAI Chat Completions API format. Examples include Groq, Anyscale, DeepInfra, Azure OpenAI, and others.</p>
            <p><b>Base URL format:</b> Usually ends with <code>/v1</code> (e.g., <code>https://api.example.com/v1</code>)</p>
            """
        else:
            html = """
            <h3>OpenAI Setup:</h3>
            <ol>
            <li>Go to <a href="https://platform.openai.com/">platform.openai.com</a></li>
            <li>Sign up or log in to your account</li>
            <li>Navigate to the API section</li>
            <li>Create a new API key</li>
            <li>Copy the key and paste it above</li>
            </ol>
            <p><b>Note:</b> Your API key is stored securely on your local machine and never shared.</p>
            """
        
        self.help_text.setHtml(html)
    
    def load_current_settings(self):
        """Load current settings from config."""
        # AI Settings (only if AI widgets exist)
        if hasattr(self, 'api_key_edit'):
            api_key = config.get_openai_api_key()
            if api_key:
                self.api_key_edit.setText(api_key)
            
            model_settings = config.get_model_settings()
            
            # Load provider settings
            provider = model_settings.get("provider", "OpenAI")
            if hasattr(self, 'provider_combo'):
                if provider == "Local":
                    self.provider_combo.setCurrentText("Local (Ollama/LM Studio)")
                elif provider == "Ollama Cloud":
                    self.provider_combo.setCurrentText("Ollama Cloud")
                elif provider == "Anthropic":
                    self.provider_combo.setCurrentText("Anthropic")
                elif provider == "Together AI":
                    self.provider_combo.setCurrentText("Together AI")
                elif provider == "OpenRouter":
                    self.provider_combo.setCurrentText("OpenRouter")
                elif provider == "Hugging Face":
                    self.provider_combo.setCurrentText("Hugging Face")
                elif provider == "Custom":
                    self.provider_combo.setCurrentText("Custom")
                else:
                    self.provider_combo.setCurrentText("OpenAI")
            
            # Load base URL and store it for the current provider
            if hasattr(self, 'base_url_edit'):
                base_url = model_settings.get("base_url")
                # Set flag to prevent textChanged from updating stored value during load
                self._updating_base_url = True
                try:
                    if base_url:
                        self.base_url_edit.setText(base_url)
                        # Store it for the current provider
                        if hasattr(self, 'provider_combo'):
                            provider_text = self.provider_combo.currentText()
                            if provider_text:
                                self.provider_base_urls[provider_text] = base_url
                    elif provider == "Local":
                        # Set default for local if provider is Local and no base_url in config
                        default_url = "http://localhost:11434/v1"
                        self.base_url_edit.setText(default_url)
                        if hasattr(self, 'provider_combo'):
                            self.provider_base_urls["Local (Ollama/LM Studio)"] = default_url
                    elif provider == "Ollama Cloud":
                        default_url = "https://ollama.com/api"
                        self.base_url_edit.setText(default_url)
                        if hasattr(self, 'provider_combo'):
                            self.provider_base_urls["Ollama Cloud"] = default_url
                    elif provider == "Anthropic":
                        # Set default for Anthropic if no base_url in config
                        default_url = "https://api.anthropic.com"
                        self.base_url_edit.setText(default_url)
                        if hasattr(self, 'provider_combo'):
                            self.provider_base_urls["Anthropic"] = default_url
                    elif provider == "OpenAI":
                        # Set default for OpenAI if no base_url in config
                        default_url = "https://api.openai.com/v1"
                        self.base_url_edit.setText(default_url)
                        if hasattr(self, 'provider_combo'):
                            self.provider_base_urls["OpenAI"] = default_url
                finally:
                    self._updating_base_url = False
            
            # Initialize current provider tracking
            if hasattr(self, 'provider_combo'):
                self._current_provider = self.provider_combo.currentText()
            
            # Trigger provider change to update UI (only if widgets exist)
            if hasattr(self, 'provider_combo') and hasattr(self, 'base_url_edit'):
                current_text = self.provider_combo.currentText()
                if current_text:
                    self.on_provider_changed(current_text)
            
            if hasattr(self, 'model_combo'):
                self.model_combo.setCurrentText(model_settings.get("model", "gpt-4"))
            if hasattr(self, 'temperature_spinbox'):
                self.temperature_spinbox.setValue(int(model_settings.get("temperature", 0.7) * 100))
            if hasattr(self, 'max_tokens_slider'):
                val = model_settings.get("max_tokens", 2000)
                # Convert actual token value to slider index (0-29)
                # Index = (tokens / 2000) - 1, clamped to 0-29
                slider_index = max(0, min(29, (val // 2000) - 1))
                self.max_tokens_slider.blockSignals(True)
                self.max_tokens_slider.setValue(slider_index)
                self.max_tokens_slider.blockSignals(False)
                if hasattr(self, 'max_tokens_value_label'):
                    actual_tokens = (slider_index + 1) * 2000
                    self.max_tokens_value_label.setText(str(actual_tokens))
        
        # UI Settings (only if UI widgets exist)
        if hasattr(self, 'theme_combo'):
            ui_settings = config.get_ui_settings()
            self.theme_combo.setCurrentText(ui_settings["theme"].title())
            self.font_size_spinbox.setValue(ui_settings["font_size"])
            self.show_line_numbers_checkbox.setChecked(ui_settings["show_line_numbers"])
            self.auto_save_spinbox.setValue(ui_settings["auto_save_interval"])
    
    def save_settings(self):
        """Save settings to config."""
        try:
            # Save AI provider settings (only if AI widgets exist)
            if hasattr(self, 'provider_combo'):
                provider_text = self.provider_combo.currentText()
                # Map provider text to config value
                if provider_text == "Local (Ollama/LM Studio)":
                    provider = "Local"
                elif provider_text == "Ollama Cloud":
                    provider = "Ollama Cloud"
                elif provider_text == "Anthropic":
                    provider = "Anthropic"
                elif provider_text == "Together AI":
                    provider = "Together AI"
                elif provider_text == "OpenRouter":
                    provider = "OpenRouter"
                elif provider_text == "Hugging Face":
                    provider = "Hugging Face"
                elif provider_text == "Custom":
                    provider = "Custom"
                else:
                    provider = "OpenAI"

                # Get base URL for providers that need it (Ollama Cloud: raw URL, do not append /v1)
                needs_base_url = provider in ["Local", "Ollama Cloud", "Anthropic", "Together AI", "OpenRouter", "Hugging Face", "Custom", "OpenAI"]
                base_url = self.base_url_edit.text().strip() if needs_base_url else None
                
                # If base URL is empty for providers that need it, try to get it from config or use default
                if needs_base_url and not base_url:
                    model_settings = config.get_model_settings()
                    base_url = model_settings.get("base_url")
                    # If still empty, use defaults
                    if not base_url:
                        if provider == "Local":
                            base_url = "http://localhost:11434/v1"
                        elif provider == "Ollama Cloud":
                            base_url = "https://ollama.com/api"
                        elif provider == "Anthropic":
                            base_url = "https://api.anthropic.com"
                        elif provider == "Together AI":
                            base_url = "https://api.together.xyz/v1"
                        elif provider == "OpenRouter":
                            base_url = "https://openrouter.ai/api/v1"
                        elif provider == "Hugging Face":
                            base_url = "https://api-inference.huggingface.co/v1/"
                        elif provider == "OpenAI":
                            base_url = "https://api.openai.com/v1"
                    # Update the UI field so user can see what's being saved
                    self.base_url_edit.setText(base_url)
                
                # Validate base URL if needed
                if needs_base_url:
                    if not base_url:
                        QMessageBox.warning(self, "Validation Error", f"Please enter a Base URL for {provider_text}")
                        return
                    if not base_url.startswith("http://") and not base_url.startswith("https://"):
                        QMessageBox.warning(self, "Validation Error", "Base URL must start with http:// or https://")
                        return
                
                # Save API key (optional for local, required for Custom)
                api_key = self.api_key_edit.text().strip()
                if provider == "Custom" and not api_key:
                    QMessageBox.warning(self, "Validation Error", "Please enter an API key for Custom provider")
                    return
                if api_key:
                    success = config.set_openai_api_key(api_key)
                    if not success:
                        QMessageBox.warning(self, "Save Error", "Failed to save API key securely")
                        return
                
                model = self.model_combo.currentText()
                temperature = self.temperature_spinbox.value() / 100.0
                # Convert slider index to actual token value
                slider_index = self.max_tokens_slider.value()
                max_tokens = (slider_index + 1) * 2000  # Index 0 = 2000, index 1 = 4000, etc.
                config.set_model_settings(
                    model, temperature, max_tokens, provider, base_url,
                )
            
            # Save UI settings (only if UI widgets exist)
            if hasattr(self, 'theme_combo'):
                theme = self.theme_combo.currentText().lower()
                font_size = self.font_size_spinbox.value()
                show_line_numbers = self.show_line_numbers_checkbox.isChecked()
                auto_save_interval = self.auto_save_spinbox.value()
                config.set_ui_settings(theme, font_size, show_line_numbers, auto_save_interval)
                
                # Apply theme and font size immediately
                self.apply_ui_settings(theme, font_size)
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {str(e)}")
    
    def apply_ui_settings(self, theme: str, font_size: int):
        """Apply theme and font size to the application."""
        app = QApplication.instance()
        if app is None:
            return
        
        # Apply theme
        if theme == "dark":
            dark_stylesheet = """
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit, QTextEdit, QSpinBox, QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
            QCheckBox {
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                border-bottom: 2px solid #0078d4;
            }
            QMenuBar {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QMenuBar::item:selected {
                background-color: #404040;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
            QStatusBar {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QToolBar {
                background-color: #2b2b2b;
                border: none;
            }
            """
            app.setStyleSheet(dark_stylesheet)
        else:
            # Light theme - use default Fusion style
            app.setStyleSheet("")
        
        # Apply font size
        default_font = QFont()
        default_font.setPointSize(font_size)
        app.setFont(default_font)
    
    def test_ai_connection(self):
        """Test the AI connection with current settings."""
        import requests
        provider_text = self.provider_combo.currentText()
        is_local = provider_text == "Local (Ollama/LM Studio)"
        is_ollama_cloud = provider_text == "Ollama Cloud"
        is_anthropic = provider_text == "Anthropic"
        needs_base_url = provider_text in ["Local (Ollama/LM Studio)", "Ollama Cloud", "Anthropic", "Together AI", "OpenRouter", "Hugging Face", "Custom", "OpenAI"]
        base_url = self.base_url_edit.text().strip() if needs_base_url else None

        # If base URL is empty, try to get it from config
        if needs_base_url and not base_url:
            model_settings = config.get_model_settings()
            base_url = model_settings.get("base_url")
            # If still empty, use defaults (Ollama Cloud has no default)
            if not base_url:
                if is_local:
                    base_url = "http://localhost:11434/v1"
                elif is_anthropic:
                    base_url = "https://api.anthropic.com"
                elif provider_text == "Together AI":
                    base_url = "https://api.together.xyz/v1"
                elif provider_text == "OpenRouter":
                    base_url = "https://openrouter.ai/api/v1"
                elif provider_text == "Hugging Face":
                    base_url = "https://api-inference.huggingface.co/v1/"
                elif provider_text == "OpenAI":
                    base_url = "https://api.openai.com/v1"

        api_key = self.api_key_edit.text().strip()

        # For local and Ollama Cloud, API key is optional; for others it's required
        if not is_local and not is_ollama_cloud and not api_key:
            self.test_result_label.setText("❌ Please enter an API key first")
            return

        # For providers that need base URL, it's required
        if needs_base_url and not base_url:
            self.test_result_label.setText(f"❌ Please enter a Base URL for {provider_text}")
            return

        model = self.model_combo.currentText()

        # Ollama Cloud: native API; if base ends with /api use .../chat, else .../api/chat
        if is_ollama_cloud:
            try:
                self.test_result_label.setText("🔄 Testing connection...")
                base = base_url.rstrip("/")
                url = f"{base}/chat" if base.endswith("/api") else f"{base}/api/chat"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "Hello, this is a test message."}],
                    "stream": False,
                }
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get("message", {}).get("content") is not None:
                    self.test_result_label.setText(f"✅ Connection successful! Provider: Ollama Cloud, Model: {model}")
                else:
                    self.test_result_label.setText("❌ Connection failed: No response from API")
            except Exception as e:
                error_msg = str(e)
                if "Connection refused" in error_msg or "Failed to establish" in error_msg or "connection" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Cannot connect to {base_url}. Check your Ollama Cloud base URL.")
                elif "Model" in error_msg and "not found" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Model '{model}' not found on Ollama Cloud.")
                else:
                    self.test_result_label.setText(f"❌ Connection failed: {error_msg[:100]}")
            return

        # Anthropic: use the Anthropic SDK
        if is_anthropic:
            try:
                import anthropic
                self.test_result_label.setText("🔄 Testing connection...")
                client_kwargs = {"api_key": api_key}
                if base_url and base_url.strip() and base_url.strip() != "https://api.anthropic.com":
                    client_kwargs["base_url"] = base_url.strip().rstrip("/")
                client = anthropic.Anthropic(**client_kwargs)
                response = client.messages.create(
                    model=model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hello, this is a test message."}],
                )
                if response.content:
                    self.test_result_label.setText(f"✅ Connection successful! Provider: Anthropic, Model: {model}")
                else:
                    self.test_result_label.setText("❌ Connection failed: No response from API")
            except ImportError:
                self.test_result_label.setText("❌ Anthropic SDK not installed. Run: pip install anthropic")
            except Exception as e:
                error_msg = str(e)
                if "invalid x-api-key" in error_msg.lower() or "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    self.test_result_label.setText("❌ Invalid Anthropic API key")
                elif "not found" in error_msg.lower() or "model" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Model '{model}' not found or not available on Anthropic")
                elif any(indicator in error_msg.lower() for indicator in [
                    "quota exceeded", "rate limit", "billing", "usage limit"
                ]):
                    self.test_result_label.setText("⚠️ API quota/rate limit exceeded for Anthropic")
                else:
                    self.test_result_label.setText(f"❌ Connection failed: {error_msg[:100]}")
            return

        try:
            import openai

            # Create client with appropriate settings (OpenAI-compatible; base_url as provided)
            client = openai.OpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url
            )

            # Test with a simple request
            self.test_result_label.setText("🔄 Testing connection...")

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello, this is a test message."}],
                max_tokens=10
            )

            if response.choices:
                provider_name = provider_text
                self.test_result_label.setText(f"✅ Connection successful! Provider: {provider_name}, Model: {model}")
            else:
                self.test_result_label.setText("❌ Connection failed: No response from API")

        except Exception as e:
            error_msg = str(e)

            # Handle provider-specific errors
            if is_local:
                if "Connection refused" in error_msg or "Failed to establish" in error_msg:
                    self.test_result_label.setText(f"❌ Cannot connect to {base_url}. Make sure Ollama/LM Studio is running.")
                elif "Model" in error_msg and "not found" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Model '{model}' not found. Download it first (e.g., 'ollama pull {model}')")
                else:
                    self.test_result_label.setText(f"❌ Connection failed: {error_msg[:100]}")
            elif needs_base_url:
                # Together AI, OpenRouter, Hugging Face, Custom errors
                if "Invalid API key" in error_msg or "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Invalid API key for {provider_text}")
                elif "not found" in error_msg.lower() or "model" in error_msg.lower():
                    self.test_result_label.setText(f"❌ Model '{model}' not found or not available")
                elif any(indicator in error_msg.lower() for indicator in [
                    "quota exceeded", "rate limit", "billing limit", "usage limit"
                ]):
                    self.test_result_label.setText(f"⚠️ API quota/rate limit exceeded for {provider_text}")
                elif provider_text == "Custom":
                    self.test_result_label.setText(f"❌ Custom provider connection failed: {error_msg[:100]}")
                else:
                    self.test_result_label.setText(f"❌ Connection failed: {error_msg[:100]}")
            else:
                # OpenAI specific errors
                if "Invalid API key" in error_msg:
                    self.test_result_label.setText("❌ Invalid API key")
                elif any(indicator in error_msg.lower() for indicator in [
                    "insufficient_quota", "quota exceeded", "rate limit exceeded", 
                    "billing limit", "usage limit", "quota has been exceeded",
                    "rate limit hit", "billing quota", "usage quota"
                ]):
                    self.test_result_label.setText("⚠️ API quota exceeded - Check your OpenAI billing")
                elif "rate_limit" in error_msg:
                    self.test_result_label.setText("❌ Rate limit exceeded")
                else:
                    self.test_result_label.setText(f"❌ Connection failed: {error_msg[:100]}")

