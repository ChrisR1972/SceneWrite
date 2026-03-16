"""
Main application window for SceneWrite.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMenuBar, QToolBar, QStatusBar, QMessageBox,
    QFileDialog, QInputDialog, QProgressDialog, QDialog,
    QLineEdit, QTextEdit, QFormLayout, QDialogButtonBox,
    QDockWidget, QToolButton, QMenu, QCheckBox, QComboBox, QGroupBox, QSpinBox,
    QApplication, QLabel
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QAction, QIcon, QFont
import json
import os
import re
import sys
import uuid
from typing import Optional, List
from datetime import datetime

from core.screenplay_engine import Screenplay, StoryboardItem, StoryScene, StoryAct
from core.ai_generator import AIGenerator
from core.higgsfield_exporter import HiggsfieldExporter
from .premise_dialog import PremiseDialog
from .storyboard_timeline import StoryboardTimeline
from .storyboard_item_editor import StoryboardItemEditor
from .story_framework_view import StoryFrameworkView, FrameworkGenerationThread
from .scene_framework_editor import SceneFrameworkEditor
from .settings_dialog import SettingsDialog
from .story_creation_wizard import StoryCreationWizard
from .ai_chat_panel import AIChatPanel
from .higgsfield_panel import HiggsfieldPanel
from .help_dialogs import InstructionsDialog, AboutDialog, LicenseDialog
from .update_dialog import UpdateCheckThread, UpdateAvailableDialog
from .activation_dialog import ActivationDialog, TrialExpiredDialog
from core.license_manager import (
    LicenseStatus, LicenseState, check_license, get_machine_id,
)
from config import config, get_app_directory, get_stories_directory

def _safe_print(*args, **kwargs):
    """Route output through debug_log instead of stdout (hidden in production)."""
    try:
        from debug_log import debug_log as _dl
        _dl(" ".join(str(a) for a in args))
    except Exception:
        pass

# Logger functions - temporarily disabled to prevent crashes
def log_exception(msg, exc):
    try:
        import traceback
        _safe_print(f"ERROR: {msg}: {exc}")
        traceback.print_exc()
    except:
        pass
def log_error(msg):
    try:
        _safe_print(f"ERROR: {msg}")
    except:
        pass
def log_info(msg):
    pass
def get_log_file_path():
    return "N/A"


class ManualStoryDialog(QDialog):
    """Simple dialog for creating a manual story with title and premise."""
    
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
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Story (Manual)")
        self.setMinimumWidth(600)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Form layout for inputs
        form_layout = QFormLayout()
        
        # Title field (required)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Enter story title...")
        self.title_edit.setMaxLength(200)
        form_layout.addRow("Title:", self.title_edit)
        
        # Premise field (optional)
        self.premise_edit = QTextEdit()
        self.premise_edit.setPlaceholderText("Enter story premise (optional)...")
        self.premise_edit.setMaximumHeight(150)
        form_layout.addRow("Premise:", self.premise_edit)
        
        layout.addLayout(form_layout)
        
        # Genre selection (for reference)
        genre_group = QGroupBox("Genres (for reference)")
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
        layout.addWidget(genre_group)
        
        # Atmosphere selection (for reference)
        atmosphere_layout = QFormLayout()
        self.atmosphere_combo = QComboBox()
        self.atmosphere_combo.addItems(self.ATMOSPHERES)
        self.atmosphere_combo.setCurrentText("Suspenseful")
        atmosphere_layout.addRow("Atmosphere/Tone (for reference):", self.atmosphere_combo)
        layout.addLayout(atmosphere_layout)
        
        # Structure setup fields
        structure_group = QGroupBox("Structure Setup (Creates Placeholders)")
        structure_layout = QFormLayout()
        
        # Number of characters
        self.num_characters_spin = QSpinBox()
        self.num_characters_spin.setMinimum(0)
        self.num_characters_spin.setMaximum(20)
        self.num_characters_spin.setValue(3)
        structure_layout.addRow("Number of Characters:", self.num_characters_spin)
        
        # Number of acts
        self.num_acts_spin = QSpinBox()
        self.num_acts_spin.setMinimum(1)
        self.num_acts_spin.setMaximum(10)
        self.num_acts_spin.setValue(3)
        structure_layout.addRow("Number of Acts:", self.num_acts_spin)
        
        # Number of scenes per act
        self.num_scenes_per_act_spin = QSpinBox()
        self.num_scenes_per_act_spin.setMinimum(1)
        self.num_scenes_per_act_spin.setMaximum(20)
        self.num_scenes_per_act_spin.setValue(3)
        structure_layout.addRow("Scenes per Act:", self.num_scenes_per_act_spin)
        
        structure_group.setLayout(structure_layout)
        layout.addWidget(structure_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus to title field
        self.title_edit.setFocus()
    
    def get_values(self):
        """Get the entered title, premise, genres, atmosphere, and structure info."""
        # Get selected genres
        selected_genres = [genre for i, genre in enumerate(self.GENRES) 
                          if self.genre_checkboxes[i].isChecked()]
        # Get selected atmosphere
        atmosphere = self.atmosphere_combo.currentText()
        # Get structure info
        num_characters = self.num_characters_spin.value()
        num_acts = self.num_acts_spin.value()
        num_scenes_per_act = self.num_scenes_per_act_spin.value()
        return (self.title_edit.text(), self.premise_edit.toPlainText(), 
                selected_genres, atmosphere, num_characters, num_acts, num_scenes_per_act)
    
    def accept(self):
        """Validate and accept the dialog."""
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Invalid Input", "Title cannot be empty.")
            return
        super().accept()


class StoryboardGenerationThread(QThread):
    """Thread for generating storyboard to avoid blocking UI."""
    
    finished = pyqtSignal(Screenplay)
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, length, atmosphere=""):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.length = length
        self.atmosphere = atmosphere
    
    def run(self):
        """Generate storyboard in background thread."""
        try:
            screenplay = self.ai_generator.generate_storyboard(
                self.premise, self.title, self.length, self.atmosphere
            )
            self.finished.emit(screenplay)
        except Exception as e:
            self.error.emit(str(e))

class NovelImportThread(QThread):
    """Thread for converting imported novel text into a screenplay."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(Screenplay)
    error = pyqtSignal(str)

    def __init__(self, ai_generator, text, length, intent):
        super().__init__()
        self.ai_generator = ai_generator
        self.text = text
        self.length = length
        self.intent = intent

    def run(self):
        try:
            from core.workflow_profile import WorkflowProfileManager, WorkflowProfile

            # Stage 1: Analyse the novel text
            self.progress.emit("Analysing text...")
            analysis = self.ai_generator.analyse_novel_text(
                self.text, self.length,
                progress_callback=lambda msg: self.progress.emit(msg)
            )

            title = analysis.get("title", "")
            premise = analysis.get("premise", "")
            genres = analysis.get("genres", ["Drama"])
            atmosphere = analysis.get("atmosphere", "Realistic")
            characters = analysis.get("characters", [])
            locations = analysis.get("locations", [])
            plot_summary = analysis.get("plot_summary", "")

            if not premise:
                raise Exception("AI analysis did not produce a premise. The text may be too short or unclear.")

            # Stage 2: Generate story outline (for NARRATIVE profiles)
            profile = WorkflowProfileManager.get_profile(self.length, self.intent)
            story_outline = {}

            if WorkflowProfileManager.requires_story_outline(profile):
                self.progress.emit("Generating story outline...")

                # Build enriched premise that includes the analysis context
                enriched_premise = premise
                if plot_summary:
                    enriched_premise += f"\n\nSource material plot summary:\n{plot_summary}"

                story_outline = self.ai_generator.generate_story_outline(
                    premise=enriched_premise,
                    genres=genres,
                    atmosphere=atmosphere,
                    title=title,
                    workflow_profile=profile,
                    character_count=len(characters) if characters else None,
                    length=self.length
                )

                # Inject character details from novel analysis into the outline
                if characters and isinstance(story_outline, dict):
                    outline_chars = story_outline.get("characters", [])
                    if not outline_chars or len(outline_chars) == 0:
                        story_outline["characters"] = [
                            {
                                "name": c.get("name", "Unknown"),
                                "outline": c.get("description", ""),
                                "growth_arc": c.get("arc", ""),
                            }
                            for c in characters
                        ]

                # Inject locations from novel analysis
                if locations and isinstance(story_outline, dict):
                    outline_locs = story_outline.get("locations", [])
                    if not outline_locs:
                        story_outline["locations"] = [
                            loc.get("name", loc) if isinstance(loc, dict) else str(loc)
                            for loc in locations
                        ]

            # Stage 3: Generate framework
            self.progress.emit("Building screenplay framework...")
            screenplay = self.ai_generator.generate_story_framework(
                premise=premise,
                title=title,
                length=self.length,
                atmosphere=atmosphere,
                genres=genres,
                story_outline=story_outline,
                intent=self.intent,
            )

            # Store the import source info in metadata
            screenplay.metadata = screenplay.metadata or {}
            screenplay.metadata["imported_from"] = "novel_text"
            screenplay.intent = self.intent
            screenplay.story_length = self.length

            self.progress.emit("Done!")
            self.finished.emit(screenplay)

        except Exception as e:
            self.error.emit(str(e))


class _ToastOverlay(QLabel):
    """Lightweight overlay for status notifications that auto-hides."""

    def __init__(self, text: str, parent: QMainWindow, duration_ms: int = 4000):
        super().__init__(text, parent)
        self.setStyleSheet(
            "background-color: rgba(40, 120, 60, 220); color: #ffffff; "
            "padding: 10px 24px; border-radius: 6px; font-size: 13px; font-weight: bold;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()
        pw = parent.width()
        self.move((pw - self.width()) // 2, 30)
        self.raise_()
        self.show()
        QTimer.singleShot(duration_ms, self._dismiss)

    def _dismiss(self):
        self.hide()
        self.deleteLater()


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        try:
            from debug_log import debug_log, debug_exception
            debug_log("MainWindow.__init__ started")
        except:
            pass
        
        try:
            debug_log("Calling super().__init__()...")
            super().__init__()
            debug_log("super().__init__() completed")
        except Exception as e:
            debug_exception("Error in super().__init__()", e)
            raise
        
        try:
            debug_log("Initializing MainWindow attributes...")
            self.current_screenplay: Optional[Screenplay] = None
            self.current_filename: Optional[str] = None
            self._has_unsaved_changes: bool = False
            self.ai_generator: Optional[AIGenerator] = None
            self._pending_story_settings: Optional[dict] = None
            debug_log("Creating HiggsfieldExporter...")
            self.exporter = HiggsfieldExporter()
            debug_log("HiggsfieldExporter created")
            self.generation_thread: Optional[StoryboardGenerationThread] = None
            self._license_state: Optional[LicenseState] = None
            
            # UI components
            self.framework_view: Optional[StoryFrameworkView] = None
            self.timeline_view: Optional[StoryboardTimeline] = None  # Keep for backward compatibility
            self.status_bar: Optional[QStatusBar] = None
            self.framework_thread: Optional[FrameworkGenerationThread] = None
            
            # Auto-save timer
            debug_log("Creating auto-save timer...")
            self.auto_save_timer = QTimer()
            self.auto_save_timer.timeout.connect(self.auto_save)
            debug_log("Auto-save timer created")
            
            # Initialize AI generator before UI so chat panel can use it
            debug_log("Initializing AI generator...")
            self.init_ai_generator()
            debug_log("AI generator initialized")
            
            debug_log("Initializing UI...")
            self.init_ui()
            debug_log("UI initialized")
            
            debug_log("Setting up auto-save...")
            self.setup_auto_save()
            debug_log("Auto-save setup complete")

            debug_log("Scheduling background update check...")
            QTimer.singleShot(3000, self.start_update_check)

            debug_log("MainWindow.__init__ completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in MainWindow.__init__", e)
            except:
                pass
            raise
    
    def init_ui(self):
        """Initialize the user interface."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("init_ui() started")
        except:
            pass
        
        try:
            debug_log("Setting window title...")
            self.setWindowTitle("SceneWrite")
            
            # Get screen size and set reasonable window size
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            # Use 90% of screen size, but cap at 1400x800 max
            max_width = min(1400, int(screen.width() * 0.9))
            max_height = min(800, int(screen.height() * 0.9))
            # Ensure minimum usable size
            min_width = 800
            min_height = 600
            
            # Set initial size based on screen, but ensure it fits
            initial_width = min(max_width, 1200)
            initial_height = min(max_height, 700)
            
            self.setMinimumSize(min_width, min_height)
            self.resize(initial_width, initial_height)
            
            # Center window on screen
            x = (screen.width() - initial_width) // 2
            y = (screen.height() - initial_height) // 2
            self.move(x, y)
            
            # Create central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            
            # Create main layout
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(0, 0, 0, 0)
            
            # Create framework view (new two-phase approach)
            debug_log("Creating StoryFrameworkView...")
            self.framework_view = StoryFrameworkView()
            debug_log("StoryFrameworkView created")
            debug_log("Connecting signals...")
            self.framework_view.scene_selected.connect(self.on_scene_selected)
            self.framework_view.scene_edit_requested.connect(self.on_scene_edit_requested)
            self.framework_view.storyboard_item_edit_requested.connect(self.on_storyboard_item_edit_requested)
            self.framework_view.storyboard_items_selected.connect(self.on_storyboard_items_selected)
            self.framework_view.data_changed.connect(self._mark_unsaved)
            self.framework_view.data_changed.connect(self.save_screenplay)
            debug_log("Signals connected")
            debug_log("Adding framework_view to layout...")
            main_layout.addWidget(self.framework_view)
            debug_log("framework_view added to layout")
            
            # Keep timeline view for backward compatibility (legacy storyboard_items)
            self.timeline_view = StoryboardTimeline()
            self.timeline_view.item_clicked.connect(self.on_item_clicked)
            self.timeline_view.item_edit_requested.connect(self.on_item_edit_requested)
            self.timeline_view.hide()  # Hide by default, show only for legacy files
            
            # Create menu bar
            debug_log("Creating menu bar...")
            self.create_menu_bar()
            debug_log("Menu bar created")
            
            # Create toolbar
            debug_log("Creating toolbar...")
            self.create_toolbar()
            debug_log("Toolbar created")
            
            # Create status bar
            debug_log("Creating status bar...")
            self.status_bar = QStatusBar()
            self.setStatusBar(self.status_bar)
            self.update_status_bar()
            debug_log("Status bar created")
            
            # Create AI chat panel as dock widget
            debug_log("Creating chat panel...")
            self.create_chat_panel()
            debug_log("Chat panel created")
            
            # Create Higgsfield API panel as dock widget
            debug_log("Creating Higgsfield panel...")
            self.create_higgsfield_panel()
            debug_log("Higgsfield panel created")
            debug_log("init_ui() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in init_ui()", e)
            except:
                pass
            import traceback
            error_msg = f"Error initializing UI: {str(e)}\n\n{traceback.format_exc()}"
            _safe_print(error_msg)
            QMessageBox.critical(None, "Initialization Error", error_msg)
            raise
    
    def create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        new_action = QAction("New Story (AI Generated)", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_screenplay)
        file_menu.addAction(new_action)
        
        new_manual_action = QAction("New Story (Manual)", self)
        new_manual_action.triggered.connect(self.new_screenplay_manual)
        file_menu.addAction(new_manual_action)
        
        quick_micro_action = QAction("Quick Micro Story", self)
        quick_micro_action.setShortcut("Ctrl+M")
        quick_micro_action.triggered.connect(self.quick_micro_story)
        file_menu.addAction(quick_micro_action)
        
        file_menu.addSeparator()
        
        open_action = QAction("Open...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_screenplay)
        file_menu.addAction(open_action)
        
        import_text_action = QAction("Import Story from Text...", self)
        import_text_action.setShortcut("Ctrl+I")
        import_text_action.triggered.connect(self.import_story_from_text)
        file_menu.addAction(import_text_action)
        
        # Recent Stories submenu
        self.recent_files_menu = file_menu.addMenu("Recent Stories")
        self._update_recent_files_menu()
        
        file_menu.addSeparator()
        
        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_screenplay)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_screenplay_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        chat_toggle_action = QAction("Show AI Chat", self)
        chat_toggle_action.setCheckable(True)
        chat_toggle_action.triggered.connect(self.toggle_chat_panel)
        view_menu.addAction(chat_toggle_action)
        self.chat_toggle_action = chat_toggle_action
        
        hf_toggle_action = QAction("Show Higgsfield API", self)
        hf_toggle_action.setCheckable(True)
        hf_toggle_action.triggered.connect(self.toggle_higgsfield_panel)
        view_menu.addAction(hf_toggle_action)
        self.hf_toggle_action = hf_toggle_action
        
        file_menu.addSeparator()
        
        export_menu = file_menu.addMenu("Export")
        
        export_json_action = QAction("Export as JSON...", self)
        export_json_action.triggered.connect(lambda: self.export_screenplay("json"))
        export_menu.addAction(export_json_action)
        
        export_csv_action = QAction("Export as CSV...", self)
        export_csv_action.triggered.connect(lambda: self.export_screenplay("csv"))
        export_menu.addAction(export_csv_action)
        
        export_higgsfield_action = QAction("Export for Higgsfield API...", self)
        export_higgsfield_action.triggered.connect(lambda: self.export_screenplay("higgsfield"))
        export_menu.addAction(export_higgsfield_action)
        
        export_prompts_action = QAction("Export Prompts Only...", self)
        export_prompts_action.triggered.connect(lambda: self.export_screenplay("prompts"))
        export_menu.addAction(export_prompts_action)

        export_menu.addSeparator()

        export_platform_action = QAction("Export Prompts for Platform...", self)
        export_platform_action.triggered.connect(self.export_for_platform)
        export_menu.addAction(export_platform_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Series menu (Episodic Series System)
        series_menu = menubar.addMenu("Series")

        new_series_action = QAction("New Series...", self)
        new_series_action.triggered.connect(self.new_series)
        series_menu.addAction(new_series_action)

        new_episode_action = QAction("New Episode...", self)
        new_episode_action.triggered.connect(self.new_episode)
        series_menu.addAction(new_episode_action)

        series_menu.addSeparator()

        open_series_action = QAction("Open Series Dashboard...", self)
        open_series_action.triggered.connect(self.open_series_dashboard)
        series_menu.addAction(open_series_action)

        edit_bible_action = QAction("Edit Series Bible...", self)
        edit_bible_action.triggered.connect(self.edit_series_bible)
        series_menu.addAction(edit_bible_action)

        series_menu.addSeparator()

        convert_action = QAction("Convert Current Story to Series...", self)
        convert_action.triggered.connect(self.convert_to_series)
        series_menu.addAction(convert_action)

        series_menu.addSeparator()

        finalize_action = QAction("Finalize Episode...", self)
        finalize_action.triggered.connect(self.finalize_episode)
        series_menu.addAction(finalize_action)

        self.series_menu = series_menu

        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        
        ai_config_action = QAction("AI Config", self)
        ai_config_action.triggered.connect(self.show_ai_settings)
        settings_menu.addAction(ai_config_action)
        
        ui_config_action = QAction("UI Config", self)
        ui_config_action.triggered.connect(self.show_ui_settings)
        settings_menu.addAction(ui_config_action)

        settings_menu.addSeparator()

        story_settings_action = QAction("Story Settings", self)
        story_settings_action.triggered.connect(self.show_story_settings)
        settings_menu.addAction(story_settings_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        
        instructions_action = QAction("Instructions", self)
        instructions_action.triggered.connect(self.show_instructions)
        help_menu.addAction(instructions_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        license_action = QAction("License", self)
        license_action.triggered.connect(self.show_license)
        help_menu.addAction(license_action)

        help_menu.addSeparator()

        enter_key_action = QAction("Enter License Key...", self)
        enter_key_action.triggered.connect(self.show_activation_dialog)
        help_menu.addAction(enter_key_action)

        help_menu.addSeparator()

        update_action = QAction("Check for Updates...", self)
        update_action.triggered.connect(self.check_for_updates_manual)
        help_menu.addAction(update_action)
    
    def create_toolbar(self):
        """Create the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Create "New" button (no menu)
        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_screenplay)
        toolbar.addAction(new_action)
        
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_screenplay)
        toolbar.addAction(open_action)
        
        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_screenplay)
        toolbar.addAction(save_action)
        
        toolbar.addSeparator()
        
        export_action = QAction("Export", self)
        export_action.triggered.connect(lambda: self.export_screenplay("higgsfield"))
        toolbar.addAction(export_action)
    
    # -- Recent files helpers ------------------------------------------------

    def _update_recent_files_menu(self):
        """Rebuild the Recent Stories submenu from the config."""
        menu = self.recent_files_menu
        menu.clear()

        recent = config.get_recent_files()
        if recent:
            for i, filepath in enumerate(recent, start=1):
                display = os.path.basename(filepath)
                action = QAction(f"&{i}  {display}", self)
                action.setToolTip(filepath)
                action.setData(filepath)
                action.triggered.connect(lambda checked, p=filepath: self._open_recent_file(p))
                menu.addAction(action)

            menu.addSeparator()
            clear_action = QAction("Clear Recent Stories", self)
            clear_action.triggered.connect(self._clear_recent_files)
            menu.addAction(clear_action)
        else:
            empty_action = QAction("(No recent stories)", self)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)

    def _open_recent_file(self, filepath: str):
        """Open a story from the recent-files list."""
        # Warn about unsaved changes before replacing the current story
        if self.current_screenplay and self._has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Open a different story anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        if not os.path.isfile(filepath):
            QMessageBox.warning(
                self, "File Not Found",
                f"The file no longer exists:\n{filepath}"
            )
            # Remove the stale entry and refresh the menu
            recent = config.get_recent_files()  # already prunes missing files
            self._update_recent_files_menu()
            return

        try:
            screenplay = Screenplay.load_from_file(filepath)
            self.current_screenplay = screenplay
            self.current_filename = filepath
            self._mark_saved()

            if screenplay.acts:
                self.framework_view.set_screenplay(screenplay)
                self.framework_view.set_ai_generator(self.ai_generator)
                self.framework_view.show()
                self.timeline_view.hide()
            else:
                self.timeline_view.set_screenplay(screenplay)
                self.timeline_view.show()
                self.framework_view.hide()

            self.update_status_bar()
            self.setWindowTitle(f"SceneWrite - {os.path.basename(filepath)}")

            if self.chat_panel:
                self.chat_panel.set_screenplay(screenplay)
                self.chat_panel.set_ai_generator(self.ai_generator)
            if hasattr(self, 'hf_panel') and self.hf_panel:
                self.hf_panel.set_screenplay(screenplay)

            # Bump this file to the top of the list
            config.add_recent_file(filepath)
            self._update_recent_files_menu()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{str(e)}")

    def _clear_recent_files(self):
        """Clear all recent-file entries after confirmation."""
        reply = QMessageBox.question(
            self, "Clear Recent Stories",
            "Remove all entries from the recent stories list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            config.clear_recent_files()
            self._update_recent_files_menu()

    # -----------------------------------------------------------------------

    def init_ai_generator(self):
        """Initialize the AI generator."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("init_ai_generator() started")
        except:
            pass
        
        try:
            debug_log("Creating AIGenerator instance...")
            self.ai_generator = AIGenerator()
            debug_log("AIGenerator created")
            # Keep the AI generator object even if client isn't initialized
            # This allows instruction requests to work via chat_about_story
            # Set AI generator in framework view
            debug_log("Setting AI generator in framework view...")
            if self.framework_view:
                self.framework_view.set_ai_generator(self.ai_generator)
                debug_log("AI generator set in framework view")
        except Exception as e:
            try:
                debug_exception("Error creating AIGenerator", e)
            except:
                pass
            # Don't show warning on startup - user can configure later
            # Still try to create the object so instruction requests can work
            # Even if client init fails, the object can still handle instruction requests
            try:
                debug_log("Retrying AIGenerator creation...")
                self.ai_generator = AIGenerator()
                debug_log("AIGenerator created on retry")
            except Exception as e2:
                try:
                    debug_exception("Failed to create AIGenerator on retry", e2)
                except:
                    pass
                # If we can't create it at all, set to None
                self.ai_generator = None
                debug_log("AIGenerator set to None")
            if self.framework_view:
                self.framework_view.set_ai_generator(self.ai_generator)
                debug_log("AI generator set in framework view (fallback)")
            if self.chat_panel:
                self.chat_panel.set_ai_generator(self.ai_generator)
    
    def setup_auto_save(self):
        """Setup auto-save functionality."""
        interval = config.get_ui_settings().get("auto_save_interval", 300) * 1000  # Convert to milliseconds
        self.auto_save_timer.start(interval)
    
    def auto_save(self):
        """Auto-save current screenplay."""
        if self.current_screenplay and self.current_filename:
            try:
                # Sync any pending UI edits before auto-saving
                if self.framework_view and hasattr(self.framework_view, 'sync_current_scene_to_model'):
                    self.framework_view.sync_current_scene_to_model()
                self.current_screenplay.save_to_file(self.current_filename)
                self._mark_saved()
            except Exception:
                pass  # Silently fail for auto-save
    
    def _mark_unsaved(self):
        """Mark the current screenplay as having unsaved changes."""
        self._has_unsaved_changes = True

    def _mark_saved(self):
        """Mark the current screenplay as fully saved (no pending changes)."""
        self._has_unsaved_changes = False

    def closeEvent(self, event):
        """Warn the user about unsaved changes before closing the application."""
        if self.current_screenplay and self._has_unsaved_changes:
            # Sync any pending UI edits so the save captures everything
            if self.framework_view and hasattr(self.framework_view, 'sync_current_scene_to_model'):
                self.framework_view.sync_current_scene_to_model()

            msg = QMessageBox(self)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText("Your story has unsaved changes.")
            msg.setInformativeText("Do you want to save before closing?")
            msg.setStandardButtons(
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel
            )
            msg.setDefaultButton(QMessageBox.StandardButton.Save)
            choice = msg.exec()

            if choice == QMessageBox.StandardButton.Save:
                if self.current_filename:
                    try:
                        self.current_screenplay.save_to_file(self.current_filename)
                    except Exception as e:
                        QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{str(e)}")
                        event.ignore()
                        return
                else:
                    self.save_screenplay_as()
                    # If the user cancelled the Save-As dialog, current_filename is still None
                    if not self.current_filename:
                        event.ignore()
                        return
                event.accept()
            elif choice == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                # Cancel
                event.ignore()
                return
        else:
            # No unsaved changes — silently save if possible and close
            if self.current_screenplay and self.current_filename:
                try:
                    if self.framework_view and hasattr(self.framework_view, 'sync_current_scene_to_model'):
                        self.framework_view.sync_current_scene_to_model()
                    self.current_screenplay.save_to_file(self.current_filename)
                except Exception:
                    pass
            event.accept()
    
    def update_status_bar(self):
        """Update the status bar with current information."""
        if self.current_screenplay:
            # Check if using new structure (acts/scenes) or legacy (storyboard_items)
            if self.current_screenplay.acts:
                # New structure
                total_scenes = sum(len(act.scenes) for act in self.current_screenplay.acts)
                complete_scenes = sum(1 for act in self.current_screenplay.acts for scene in act.scenes if scene.is_complete)
                total_items = len(self.current_screenplay.get_all_storyboard_items())
                total_duration = self.current_screenplay.get_total_duration_formatted()
                status_text = f"Acts: {len(self.current_screenplay.acts)} | Scenes: {complete_scenes}/{total_scenes} | Items: {total_items} | Duration: {total_duration}"
            else:
                # Legacy structure
                item_count = len(self.current_screenplay.storyboard_items)
                total_duration = self.current_screenplay.get_total_duration_formatted()
                status_text = f"Items: {item_count} | Duration: {total_duration}"
            
            if self.current_filename:
                status_text += f" | {os.path.basename(self.current_filename)}"
        else:
            status_text = "No storyboard loaded"
        
        self.status_bar.showMessage(status_text)
    
    def new_screenplay(self):
        """Create a new screenplay using the wizard."""
        if not self.require_license("AI Story Generation"):
            return
        if self.current_screenplay:
            reply = QMessageBox.question(
                self, "New Story (AI Generated)",
                "Create a new storyboard? Unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Open the story creation wizard
        wizard = StoryCreationWizard(self, self.ai_generator)
        wizard.wizard_completed.connect(self.on_wizard_completed)
        wizard.exec()
    
    def quick_micro_story(self):
        """Create a quick micro story (1 act, 1-5 scenes) in a single step."""
        if not self.require_license("AI Story Generation"):
            return
        if self.current_screenplay:
            reply = QMessageBox.question(
                self, "Quick Micro Story",
                "Create a new micro story? Unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in settings.")
            return
        
        # Show quick micro story dialog
        from PyQt6.QtWidgets import QInputDialog, QComboBox
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Quick Micro Story")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        
        # Title
        title_label = QLabel("Enter or generate a premise for your micro story:")
        layout.addWidget(title_label)
        
        premise_edit = QTextEdit()
        premise_edit.setPlaceholderText("Enter a premise or click 'Generate Premise' to create one...")
        premise_edit.setMinimumHeight(100)
        layout.addWidget(premise_edit)
        
        # Intent selector
        intent_layout = QHBoxLayout()
        intent_layout.addWidget(QLabel("Story Intent:"))
        intent_combo = QComboBox()
        intent_combo.addItems([
            "General Story",
            "Advertisement / Brand Film",
            "Social Media / Short-form",
            "Visual Art / Abstract"
        ])
        intent_layout.addWidget(intent_combo)
        intent_layout.addStretch()
        layout.addLayout(intent_layout)
        
        # Generate premise button
        generate_btn = QPushButton("Generate Premise")
        generate_btn.clicked.connect(lambda: self._generate_premise_for_micro(premise_edit))
        layout.addWidget(generate_btn)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        generate_story_btn = QPushButton("Generate Micro Story")
        generate_story_btn.setDefault(True)
        button_layout.addWidget(generate_story_btn)
        layout.addLayout(button_layout)
        
        # Connect generate button
        def on_generate():
            premise = premise_edit.toPlainText().strip()
            if not premise:
                QMessageBox.warning(dialog, "No Premise", "Please enter or generate a premise.")
                return
            intent = intent_combo.currentText()
            dialog.accept()
            self._generate_micro_story(premise, intent)
        
        generate_story_btn.clicked.connect(on_generate)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            premise = premise_edit.toPlainText().strip()
            if premise:
                intent = intent_combo.currentText()
                self._generate_micro_story(premise, intent)
    
    def _generate_premise_for_micro(self, premise_edit):
        """Generate a premise for micro story."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        # Simple premise generation - just use genres and atmosphere
        from PyQt6.QtWidgets import QInputDialog
        genres, ok1 = QInputDialog.getText(self, "Genres", "Enter genres (comma-separated):", text="Drama, Thriller")
        if not ok1:
            return
        
        atmosphere, ok2 = QInputDialog.getItem(
            self, "Atmosphere", "Select atmosphere:",
            ["Suspenseful", "Lighthearted", "Dark", "Mysterious", "Tense", "Energetic"],
            0, False
        )
        if not ok2:
            return
        
        try:
            genre_list = [g.strip() for g in genres.split(",") if g.strip()]
            premise = self.ai_generator.generate_premise(genre_list, atmosphere)
            premise_edit.setPlainText(premise)
        except Exception as e:
            QMessageBox.critical(self, "Generation Failed", f"Failed to generate premise:\n{str(e)}")
    
    def _generate_micro_story(self, premise: str, intent: str):
        """Generate a complete micro story (premise → scene → storyboard) in one go."""
        if not self.ai_generator:
            return
        
        # Show progress
        progress = QProgressDialog("Generating micro story...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        
        try:
            # Generate complete micro story
            screenplay = self.ai_generator.generate_micro_story(premise, intent)
            
            progress.close()
            
            # Set as current screenplay
            self.current_screenplay = screenplay
            self.current_filename = None
            self._mark_unsaved()
            self.setWindowTitle(f"SceneWrite - {screenplay.title or 'Untitled Micro Story'}")
            
            # Update views
            if self.framework_view:
                self.framework_view.set_screenplay(screenplay)
            
            # Switch to storyboard timeline view
            self.show_storyboard_timeline()
            
            self.status_bar.showMessage(
                f"Micro story generated — {len(screenplay.get_all_storyboard_items())} storyboard items", 5000)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Generation Failed", f"Failed to generate micro story:\n{str(e)}")
    
    def new_screenplay_manual(self):
        """Create a new blank screenplay manually without the wizard."""
        if self.current_screenplay:
            reply = QMessageBox.question(
                self, "New Story (Manual)",
                "Create a new story? Unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Show dialog to get title, premise, genres, atmosphere, and structure info
        dialog = ManualStoryDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            title, premise, genres, atmosphere, num_characters, num_acts, num_scenes_per_act = dialog.get_values()
            if not title.strip():
                QMessageBox.warning(self, "Invalid Input", "Title cannot be empty.")
                return
            
            # Create blank screenplay
            screenplay = Screenplay(title=title.strip(), premise=premise.strip())
            screenplay.genre = genres
            screenplay.atmosphere = atmosphere
            screenplay.story_length = "medium"
            screenplay.intent = "General Story"
            
            # Create placeholder characters (list of dicts, wizard-compatible schema)
            characters_list = []
            registry_names = []
            if num_characters > 0:
                for i in range(1, num_characters + 1):
                    char_name = f"Character {i}"
                    characters_list.append({
                        "name": char_name,
                        "role": "main",
                        "species": "Human",
                        "outline": "",
                        "growth_arc": "",
                        "physical_appearance": ""
                    })
                    registry_names.append(char_name)
            screenplay.story_outline["characters"] = characters_list
            screenplay.character_registry = registry_names
            screenplay.character_registry_frozen = bool(registry_names)
            
            # Create placeholder acts and scenes
            if num_acts > 0 and num_scenes_per_act > 0:
                for act_num in range(1, num_acts + 1):
                    act = StoryAct(
                        act_number=act_num,
                        title=f"Act {act_num}",
                        description=f"Placeholder description for Act {act_num}"
                    )
                    
                    for scene_num in range(1, num_scenes_per_act + 1):
                        try:
                            scene = StoryScene(
                                scene_id=str(uuid.uuid4()),
                                scene_number=scene_num,
                                title=f"Scene {scene_num}",
                                description=f"Placeholder scene description for Act {act_num}, Scene {scene_num}",
                                estimated_duration=60,
                                pacing="Medium",
                                character_focus=[],
                                metadata={}
                            )
                            act.add_scene(scene)
                        except Exception as e:
                            try:
                                log_exception(f"Error creating scene {scene_num} for act {act_num}", e)
                            except:
                                pass
                            continue
                    
                    screenplay.acts.append(act)
            
            screenplay.framework_complete = True
            
            self.on_wizard_completed(screenplay)
    
    def create_snapshot(self, screenplay: Screenplay, milestone: str, description: str = ""):
        """Create a snapshot of the screenplay at a milestone."""
        try:
            from core.snapshot_manager import SnapshotManager
            if not screenplay.snapshot_manager:
                screenplay.snapshot_manager = SnapshotManager()
            screenplay.snapshot_manager.create_snapshot(screenplay, milestone, description)
        except Exception as e:
            # Silently fail - snapshots are optional
            pass
    
    def on_wizard_completed(self, screenplay: Screenplay):
        """Handle wizard completion."""
        if self._pending_story_settings:
            pending = self._pending_story_settings
            ss = getattr(screenplay, "story_settings", None) or {}
            pending_audio = pending.pop("audio_settings", None)
            pending_pc = pending.pop("platform_config", None)
            ss.update(pending)
            if pending_audio:
                ss.setdefault("audio_settings", {}).update(pending_audio)
            if pending_pc:
                ss.setdefault("platform_config", {}).update(pending_pc)
            screenplay.story_settings = ss
            self._pending_story_settings = None

        self.current_screenplay = screenplay
        self.current_filename = None
        self._mark_unsaved()
        
        # Create snapshot at framework milestone
        self.create_snapshot(screenplay, "framework", "Framework generated")
        
        # Show framework view
        if self.framework_view:
            self.framework_view.set_screenplay(screenplay)
            self.framework_view.set_ai_generator(self.ai_generator)
            self.framework_view.show()
        if self.timeline_view:
            self.timeline_view.hide()
        
        # Update chat panel with new screenplay and AI generator
        if self.chat_panel:
            self.chat_panel.set_screenplay(screenplay)
            self.chat_panel.set_ai_generator(self.ai_generator)
        if hasattr(self, 'hf_panel') and self.hf_panel:
            self.hf_panel.set_screenplay(screenplay)
        
        self.update_status_bar()
        self._update_window_title(screenplay)
    
    def create_chat_panel(self):
        """Create and setup the AI chat panel as a dock widget."""
        self.chat_panel = AIChatPanel()
        self.chat_panel.set_screenplay(self.current_screenplay)
        self.chat_panel.set_ai_generator(self.ai_generator)
        self.chat_panel.changes_applied.connect(self.on_chat_changes_applied)
        
        # Create dock widget
        chat_dock = QDockWidget("AI Chat", self)
        chat_dock.setWidget(self.chat_panel)
        chat_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, chat_dock)
        chat_dock.setVisible(True)  # Visible by default
        
        self.chat_dock = chat_dock
        
        # Update menu item to reflect visible state
        if hasattr(self, 'chat_toggle_action'):
            self.chat_toggle_action.setChecked(True)
    
    def toggle_chat_panel(self, checked: bool):
        """Show or hide the chat panel."""
        if hasattr(self, 'chat_dock'):
            self.chat_dock.setVisible(checked)
            if hasattr(self, 'chat_toggle_action'):
                self.chat_toggle_action.setChecked(checked)
    
    def create_higgsfield_panel(self):
        """Create and setup the Higgsfield API panel as a dock widget."""
        self.hf_panel = HiggsfieldPanel()
        self.hf_panel.set_screenplay(self.current_screenplay)
        
        hf_dock = QDockWidget("Higgsfield API", self)
        hf_dock.setWidget(self.hf_panel)
        hf_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, hf_dock)
        hf_dock.setVisible(False)
        self.hf_dock = hf_dock
        
        if hasattr(self, 'hf_toggle_action'):
            self.hf_toggle_action.setChecked(False)
    
    def toggle_higgsfield_panel(self, checked: bool):
        """Show or hide the Higgsfield API panel."""
        if hasattr(self, 'hf_dock'):
            self.hf_dock.setVisible(checked)
            if hasattr(self, 'hf_toggle_action'):
                self.hf_toggle_action.setChecked(checked)
    
    def on_chat_changes_applied(self, change_type: str, change_data: dict):
        """Handle changes applied from chat panel."""
        self._mark_unsaved()
        try:
            if not self.current_screenplay or not self.chat_panel:
                QMessageBox.warning(self, "Error", "No screenplay or chat panel available.")
                return
            
            if change_type == "regenerate_scene" and self.chat_panel.current_scene:
                # Regenerate scene content
                scene = self.chat_panel.current_scene
                new_content = change_data.get("new_content", "")
                if not new_content:
                    QMessageBox.warning(self, "Error", "No new content provided to apply.")
                    return
                
                # Get existing content to verify paragraph count
                existing_content = ""
                if scene.metadata and scene.metadata.get("generated_content"):
                    existing_content = scene.metadata["generated_content"]
                else:
                    existing_content = scene.description
                
                # Check if this was a paragraph edit (by checking user request or change_data)
                user_request = change_data.get("user_request", "").lower()
                
                # Check if paragraph_index is explicitly set in change_data (from chat analysis)
                paragraph_index = change_data.get("paragraph_index")
                if paragraph_index is not None:
                    # Explicitly provided paragraph index - definitely a paragraph edit
                    is_paragraph_edit = True
                    paragraph_index = int(paragraph_index)
                else:
                    # Try to detect from user request keywords
                    is_paragraph_edit = any(keyword in user_request for keyword in [
                        "first paragraph", "second paragraph", "third paragraph", 
                        "paragraph 1", "paragraph 2", "paragraph 3",
                        "change paragraph", "edit paragraph", "modify paragraph",
                        "extend paragraph", "expand paragraph", "add to paragraph",
                        "option", "options", "alternative", "alternatives", 
                        "version", "versions", "different", "variation"
                    ])
                    
                    # If detected, try to extract paragraph index from request
                    if is_paragraph_edit:
                        paragraph_index = 0
                        import re
                        # Look for explicit paragraph numbers like [1], [2], paragraph 1, etc.
                        paragraph_number_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request)
                        if paragraph_number_match:
                            para_num = int(paragraph_number_match.group(1) or paragraph_number_match.group(2) or paragraph_number_match.group(3))
                            paragraph_index = para_num - 1  # Convert to 0-based index
                        elif "second" in user_request or "paragraph 2" in user_request or "2nd" in user_request:
                            paragraph_index = 1
                        elif "third" in user_request or "paragraph 3" in user_request or "3rd" in user_request:
                            paragraph_index = 2
                        elif "fourth" in user_request or "paragraph 4" in user_request or "4th" in user_request:
                            paragraph_index = 3
                        elif "fifth" in user_request or "paragraph 5" in user_request or "5th" in user_request:
                            paragraph_index = 4
                        elif "first" in user_request or "paragraph 1" in user_request or "1st" in user_request:
                            paragraph_index = 0
                
                # If this is a paragraph edit, merge properly
                if is_paragraph_edit and existing_content:
                    # Split existing content into paragraphs (remove paragraph numbers if present)
                    import re
                    existing_content_cleaned = re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE)
                    existing_paragraphs = [p.strip() for p in existing_content_cleaned.split('\n\n') if p.strip()]
                    if not existing_paragraphs:
                        # Try single newline split
                        existing_paragraphs = [p.strip() for p in existing_content_cleaned.split('\n') if p.strip()]
                    
                    if not existing_paragraphs:
                        # Can't split into paragraphs - use content as-is
                        pass
                    else:
                        # Clean new_content and split into paragraphs
                        new_content_cleaned = re.sub(r'^\[\d+\]\s+', '', new_content, flags=re.MULTILINE)
                        new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n\n') if p.strip()]
                        if not new_paragraphs:
                            # Try single newline split
                            new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n') if p.strip()]
                        
                        # Ensure paragraph_index is valid
                        if paragraph_index is None:
                            paragraph_index = 0
                        if paragraph_index < 0:
                            paragraph_index = 0
                        if paragraph_index >= len(existing_paragraphs):
                            paragraph_index = len(existing_paragraphs) - 1
                        
                        # Check if new_content appears to be just one paragraph (fewer paragraphs than existing)
                        # or if it's missing other paragraphs that should be there
                        if len(new_paragraphs) < len(existing_paragraphs) or len(new_paragraphs) == 1:
                            # New content appears to be just the edited paragraph
                            # Reconstruct: keep all original paragraphs, replace only the edited one
                            reconstructed = existing_paragraphs.copy()
                            
                            # Extract the paragraph to use as replacement
                            replacement_paragraph = None
                            if new_paragraphs:
                                # Check if the new content has the paragraph number in it
                                numbered_match = re.search(rf'\[{paragraph_index + 1}\]\s+(.+?)(?=\n\n\[|\Z)', new_content, re.DOTALL)
                                if numbered_match:
                                    replacement_paragraph = numbered_match.group(1).strip()
                                else:
                                    # Use the first (and likely only) paragraph from new_content
                                    replacement_paragraph = new_paragraphs[0]
                            else:
                                # No paragraphs found - use whole new_content as replacement
                                replacement_paragraph = new_content_cleaned.strip()
                            
                            # Replace only the specified paragraph
                            if replacement_paragraph and paragraph_index < len(reconstructed):
                                reconstructed[paragraph_index] = replacement_paragraph
                            
                            # Reconstruct the full scene content
                            new_content = '\n\n'.join(reconstructed)
                        elif len(new_paragraphs) == len(existing_paragraphs):
                            # Same number of paragraphs - might be full scene, but we still want to merge
                            # Use the paragraph at the expected index from new content
                            reconstructed = existing_paragraphs.copy()
                            if paragraph_index < len(new_paragraphs):
                                reconstructed[paragraph_index] = new_paragraphs[paragraph_index]
                            new_content = '\n\n'.join(reconstructed)
                        else:
                            # More paragraphs in new content - might be a full regeneration
                            # But if user_request suggests paragraph edit, still merge
                            # For safety, if it's clearly a paragraph edit request, we should still merge
                            if "paragraph" in user_request or paragraph_index is not None:
                                # Still treat as paragraph edit - use paragraph at index
                                reconstructed = existing_paragraphs.copy()
                                if paragraph_index < len(new_paragraphs):
                                    reconstructed[paragraph_index] = new_paragraphs[paragraph_index]
                                new_content = '\n\n'.join(reconstructed)
                
                if scene.metadata is None:
                    scene.metadata = {}
                scene.metadata["generated_content"] = new_content
                scene.updated_at = datetime.now().isoformat()
                # Refresh framework view
                if self.framework_view:
                    self.framework_view.load_scene_data(scene)
                    self.framework_view.update_tree()
                self._show_toast("Scene content updated")
            
            elif change_type == "regenerate_items" and self.chat_panel.selected_items and self.chat_panel.current_scene:
                # Regenerate storyboard items
                new_items = change_data.get("new_items", [])
                if new_items and len(new_items) == len(self.chat_panel.selected_items):
                    scene = self.chat_panel.current_scene
                    # Replace selected items with new ones
                    for old_item, new_item in zip(self.chat_panel.selected_items, new_items):
                        if old_item in scene.storyboard_items:
                            idx = scene.storyboard_items.index(old_item)
                            # Preserve sequence number
                            new_item.sequence_number = old_item.sequence_number
                            scene.storyboard_items[idx] = new_item
                    # Renumber items
                    if self.framework_view:
                        self.framework_view.renumber_storyboard_items()
                        self.framework_view.load_storyboard_items()
            
            elif change_type == "edit_character_outline" and self.current_screenplay:
                character_name = change_data.get("character_name", "")
                new_outline = change_data.get("character_outline", "")
                new_growth_arc = change_data.get("character_growth_arc", "")

                if not character_name:
                    QMessageBox.warning(self, "Error", "No character name provided in the change data.")
                    return
                if not new_outline and not new_growth_arc:
                    QMessageBox.warning(self, "Error", f"No character outline or growth arc provided for {character_name}.")
                    return

                if not self.current_screenplay.story_outline:
                    self.current_screenplay.story_outline = {}
                if "characters" not in self.current_screenplay.story_outline:
                    self.current_screenplay.story_outline["characters"] = []

                characters = self.current_screenplay.story_outline["characters"]
                character_found = False
                character_name_normalized = character_name.strip()

                for char in characters:
                    if not isinstance(char, dict):
                        continue
                    char_name = char.get("name", "").strip()
                    if char_name.lower() == character_name_normalized.lower():
                        old_outline = char.get("outline", "")
                        old_growth = char.get("growth_arc", "")

                        if new_outline:
                            if old_outline and len(new_outline) < len(old_outline):
                                if old_outline.lower() not in new_outline.lower():
                                    char["outline"] = f"{old_outline} {new_outline}"
                                else:
                                    char["outline"] = new_outline
                            else:
                                char["outline"] = new_outline

                        if new_growth_arc:
                            if old_growth:
                                if old_growth.lower() not in new_growth_arc.lower():
                                    char["growth_arc"] = f"{old_growth} {new_growth_arc}"
                                elif len(new_growth_arc) < len(old_growth):
                                    char["growth_arc"] = f"{old_growth} {new_growth_arc}"
                                else:
                                    char["growth_arc"] = new_growth_arc
                            else:
                                char["growth_arc"] = new_growth_arc

                        character_found = True
                        break

                if not character_found:
                    new_char = {
                        "name": character_name,
                        "outline": new_outline or "",
                        "growth_arc": new_growth_arc or ""
                    }
                    characters.append(new_char)

                self.current_screenplay.updated_at = datetime.now().isoformat()
                self.setWindowModified(True)
                self._mark_unsaved()

                if self.framework_view:
                    try:
                        self.framework_view.update_character_details()
                    except Exception:
                        pass
                    self.framework_view.update_tree()

                self._show_toast(f"Character outline for {character_name} updated")
            
            elif change_type == "edit_scene" and self.chat_panel.current_scene:
                # Edit scene properties or content
                scene = self.chat_panel.current_scene
                
                # Check if this is a content update (new_content) or property edits
                new_content = change_data.get("new_content", "")
                if new_content:
                    # This is a content update (similar to regenerate_scene)
                    # Get existing content to verify paragraph count
                    existing_content = ""
                    if scene.metadata and scene.metadata.get("generated_content"):
                        existing_content = scene.metadata["generated_content"]
                    else:
                        existing_content = scene.description
                    
                    # Check if this was a paragraph edit
                    user_request = change_data.get("user_request", "").lower()
                    paragraph_index = change_data.get("paragraph_index")
                    
                    if paragraph_index is not None:
                        is_paragraph_edit = True
                        paragraph_index = int(paragraph_index)
                    else:
                        is_paragraph_edit = any(keyword in user_request for keyword in [
                            "first paragraph", "second paragraph", "third paragraph", 
                            "paragraph 1", "paragraph 2", "paragraph 3",
                            "change paragraph", "edit paragraph", "modify paragraph",
                            "extend paragraph", "expand paragraph", "add to paragraph",
                            "option", "options", "alternative", "alternatives", 
                            "version", "versions", "different", "variation"
                        ])
                        
                        if is_paragraph_edit:
                            paragraph_index = 0
                            import re
                            paragraph_number_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_request)
                            if paragraph_number_match:
                                para_num = int(paragraph_number_match.group(1) or paragraph_number_match.group(2) or paragraph_number_match.group(3))
                                paragraph_index = para_num - 1
                            elif "second" in user_request or "paragraph 2" in user_request or "2nd" in user_request:
                                paragraph_index = 1
                            elif "third" in user_request or "paragraph 3" in user_request or "3rd" in user_request:
                                paragraph_index = 2
                            elif "fourth" in user_request or "paragraph 4" in user_request or "4th" in user_request:
                                paragraph_index = 3
                            elif "fifth" in user_request or "paragraph 5" in user_request or "5th" in user_request:
                                paragraph_index = 4
                            elif "first" in user_request or "paragraph 1" in user_request or "1st" in user_request:
                                paragraph_index = 0
                    
                    # If this is a paragraph edit, merge properly
                    if is_paragraph_edit and existing_content:
                        import re
                        existing_content_cleaned = re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE)
                        existing_paragraphs = [p.strip() for p in existing_content_cleaned.split('\n\n') if p.strip()]
                        if not existing_paragraphs:
                            existing_paragraphs = [p.strip() for p in existing_content_cleaned.split('\n') if p.strip()]
                        
                        if existing_paragraphs:
                            new_content_cleaned = re.sub(r'^\[\d+\]\s+', '', new_content, flags=re.MULTILINE)
                            new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n\n') if p.strip()]
                            if not new_paragraphs:
                                new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n') if p.strip()]
                            
                            if paragraph_index is None:
                                paragraph_index = 0
                            if paragraph_index < 0:
                                paragraph_index = 0
                            if paragraph_index >= len(existing_paragraphs):
                                paragraph_index = len(existing_paragraphs) - 1
                            
                            if len(new_paragraphs) < len(existing_paragraphs) or len(new_paragraphs) == 1:
                                reconstructed = existing_paragraphs.copy()
                                replacement_paragraph = None
                                if new_paragraphs:
                                    numbered_match = re.search(rf'\[{paragraph_index + 1}\]\s+(.+?)(?=\n\n\[|\Z)', new_content, re.DOTALL)
                                    if numbered_match:
                                        replacement_paragraph = numbered_match.group(1).strip()
                                    else:
                                        replacement_paragraph = new_paragraphs[0]
                                else:
                                    replacement_paragraph = new_content_cleaned.strip()
                                
                                if replacement_paragraph and paragraph_index < len(reconstructed):
                                    reconstructed[paragraph_index] = replacement_paragraph
                                new_content = '\n\n'.join(reconstructed)
                            elif len(new_paragraphs) == len(existing_paragraphs):
                                reconstructed = existing_paragraphs.copy()
                                if paragraph_index < len(new_paragraphs):
                                    reconstructed[paragraph_index] = new_paragraphs[paragraph_index]
                                new_content = '\n\n'.join(reconstructed)
                            else:
                                if "paragraph" in user_request or paragraph_index is not None:
                                    reconstructed = existing_paragraphs.copy()
                                    if paragraph_index < len(new_paragraphs):
                                        reconstructed[paragraph_index] = new_paragraphs[paragraph_index]
                                    new_content = '\n\n'.join(reconstructed)
                    
                    # Update the generated content
                    if scene.metadata is None:
                        scene.metadata = {}
                    scene.metadata["generated_content"] = new_content
                    scene.updated_at = datetime.now().isoformat()
                    
                    if self.framework_view:
                        self.framework_view.load_scene_data(scene)
                        self.framework_view.update_tree()
                    self._show_toast("Scene content updated")
                else:
                    # Handle property edits (description, title, character_focus, etc.)
                    edits = change_data.get("edits", {})
                    if "description" in edits:
                        scene.description = edits["description"]
                    if "title" in edits:
                        scene.title = edits["title"]
                    if "estimated_duration" in edits:
                        scene.estimated_duration = edits["estimated_duration"]
                    if "character_focus" in edits:
                        # Handle character_focus - can be a list or a string that needs to be parsed
                        character_focus = edits["character_focus"]
                        if isinstance(character_focus, str):
                            # Parse comma-separated string into list
                            scene.character_focus = [char.strip() for char in character_focus.split(',') if char.strip()]
                        elif isinstance(character_focus, list):
                            scene.character_focus = character_focus
                    scene.updated_at = datetime.now().isoformat()
                    if self.framework_view:
                        self.framework_view.load_scene_data(scene)
                        self.framework_view.update_tree()
            
            elif change_type == "edit_items" and self.chat_panel.selected_items:
                # Edit storyboard items
                edits = change_data.get("edits", {})
                for item in self.chat_panel.selected_items:
                    if "storyline" in edits:
                        item.storyline = edits["storyline"]
                    if "prompt" in edits:
                        item.prompt = (edits.get("prompt") or "").strip()
                    if "image_prompt" in edits:
                        item.image_prompt = (edits.get("image_prompt") or "").strip()
                    if "dialogue" in edits:
                        item.dialogue = edits["dialogue"]
                if self.framework_view:
                    self.framework_view.load_storyboard_items()
            
            elif change_type == "add_items" and self.chat_panel.current_scene:
                new_items = change_data.get("new_items", [])
                scene = self.chat_panel.current_scene
                for item in new_items:
                    if isinstance(item, StoryboardItem):
                        scene.add_storyboard_item(item)
                    elif isinstance(item, dict):
                        sb_item = StoryboardItem(
                            storyline=item.get("storyline", ""),
                            prompt=item.get("prompt", ""),
                            dialogue=item.get("dialogue", ""),
                            duration=item.get("duration", 5)
                        )
                        scene.add_storyboard_item(sb_item)
                if self.framework_view:
                    self.framework_view.renumber_storyboard_items()
                    self.framework_view.load_storyboard_items()
                self._show_toast(f"Added {len(new_items)} storyboard item(s)")

            elif change_type == "remove_items" and self.chat_panel.selected_items and self.chat_panel.current_scene:
                scene = self.chat_panel.current_scene
                removed_count = 0
                for item in self.chat_panel.selected_items:
                    if item in scene.storyboard_items:
                        scene.storyboard_items.remove(item)
                        removed_count += 1
                if self.framework_view:
                    self.framework_view.renumber_storyboard_items()
                    self.framework_view.load_storyboard_items()
                self._show_toast(f"Removed {removed_count} storyboard item(s)")

            elif change_type == "edit_premise" and self.current_screenplay:
                if change_data.get("premise"):
                    self.current_screenplay.premise = change_data["premise"]
                if change_data.get("title"):
                    self.current_screenplay.title = change_data["title"]
                    self.setWindowTitle(f"SceneWrite - {change_data['title']}")
                if change_data.get("genres"):
                    genres = change_data["genres"]
                    if isinstance(genres, str):
                        genres = [g.strip() for g in genres.split(",") if g.strip()]
                    self.current_screenplay.genre = genres
                if change_data.get("atmosphere"):
                    self.current_screenplay.atmosphere = change_data["atmosphere"]
                self.current_screenplay.updated_at = datetime.now().isoformat()
                if self.framework_view:
                    self.framework_view.update_premise_tab()
                    self.framework_view.update_tree()
                self._show_toast("Story premise updated")

            elif change_type == "edit_story_outline" and self.current_screenplay:
                if not self.current_screenplay.story_outline:
                    self.current_screenplay.story_outline = {}
                if change_data.get("main_storyline"):
                    self.current_screenplay.story_outline["main_storyline"] = change_data["main_storyline"]
                if change_data.get("subplots"):
                    self.current_screenplay.story_outline["subplots"] = change_data["subplots"]
                if change_data.get("conclusion"):
                    self.current_screenplay.story_outline["conclusion"] = change_data["conclusion"]
                self.current_screenplay.updated_at = datetime.now().isoformat()
                if self.framework_view:
                    self.framework_view.update_premise_tab()
                    self.framework_view.update_tree()
                self._show_toast("Story outline updated")

            elif change_type == "regenerate_framework" and self.current_screenplay:
                if not change_data.get("confirm"):
                    QMessageBox.warning(self, "Error", "Framework regeneration was not confirmed.")
                    return
                reply = QMessageBox.question(
                    self, "Regenerate Framework",
                    "This will replace the entire story framework (all acts and scenes). "
                    "Generated scene content and storyboard items will be lost.\n\n"
                    "Are you sure you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self._regenerate_framework_from_chat(change_data)

            elif change_type == "edit_series_bible" and self.current_screenplay:
                sm = getattr(self.current_screenplay, "series_metadata", None) or {}
                bible_path = sm.get("series_bible_path", "")
                if not bible_path or not os.path.exists(bible_path):
                    QMessageBox.warning(self, "Error", "No Series Bible found for this story.")
                    return
                try:
                    from core.series_bible import SeriesBible
                    bible = SeriesBible.load(bible_path)
                    wc = bible.world_context or {}
                    if change_data.get("setting_description"):
                        wc["setting_description"] = change_data["setting_description"]
                    if change_data.get("time_period"):
                        wc["time_period"] = change_data["time_period"]
                    if change_data.get("rules_and_lore"):
                        wc["rules_and_lore"] = change_data["rules_and_lore"]
                    if change_data.get("tone"):
                        wc["tone"] = change_data["tone"]
                    bible.world_context = wc
                    bible.save(bible_path)
                    self._show_toast("Series Bible updated")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to update Series Bible:\n{str(e)}")

            elif change_type == "edit_identity_block" and self.current_screenplay:
                entity_name = change_data.get("entity_name", "")
                entity_type = change_data.get("entity_type", "")
                user_notes = change_data.get("user_notes", "")
                if not entity_name:
                    QMessageBox.warning(self, "Error", "No entity name provided.")
                    return
                entity_id = self._find_entity_id(entity_name, entity_type)
                if entity_id:
                    self.current_screenplay.update_identity_block_metadata(
                        entity_id, user_notes=user_notes
                    )
                    self.current_screenplay.updated_at = datetime.now().isoformat()
                    self._show_toast(f"Identity block for {entity_name} updated")
                else:
                    QMessageBox.warning(self, "Error", f"Could not find identity block for '{entity_name}'.")

            elif change_type == "approve_identity_block" and self.current_screenplay:
                entity_name = change_data.get("entity_name", "")
                entity_type = change_data.get("entity_type", "")
                if not entity_name:
                    QMessageBox.warning(self, "Error", "No entity name provided.")
                    return
                entity_id = self._find_entity_id(entity_name, entity_type)
                if entity_id:
                    meta = self.current_screenplay.get_identity_block_metadata_by_id(entity_id)
                    ib = (meta or {}).get("identity_block", "")
                    if not ib:
                        QMessageBox.warning(self, "Error",
                            f"Cannot approve '{entity_name}' — no identity block generated yet. "
                            "Generate one first using the Identity Block Manager.")
                        return
                    self.current_screenplay.update_identity_block_metadata(
                        entity_id, status="approved"
                    )
                    self.current_screenplay.updated_at = datetime.now().isoformat()
                    self._show_toast(f"Identity block for {entity_name} approved")
                else:
                    QMessageBox.warning(self, "Error", f"Could not find identity block for '{entity_name}'.")

            self.update_status_bar()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply changes:\n{str(e)}")

    # ------------------------------------------------------------------
    # Chat-change helpers
    # ------------------------------------------------------------------

    def _find_entity_id(self, entity_name: str, entity_type: str) -> str | None:
        """Resolve entity_name + entity_type to an identity-block entity_id."""
        if not self.current_screenplay:
            return None
        name_lower = entity_name.strip().lower()
        # Direct lookup via identity_block_ids registry
        lookup_key = f"{entity_type}:{entity_name}".lower()
        eid = self.current_screenplay.identity_block_ids.get(lookup_key)
        if eid:
            return eid
        # Fallback: scan metadata
        for eid, meta in (self.current_screenplay.identity_block_metadata or {}).items():
            if not isinstance(meta, dict):
                continue
            if (meta.get("name") or "").strip().lower() == name_lower:
                if not entity_type or (meta.get("type") or "").lower() == entity_type.lower():
                    return eid
        return None

    def _regenerate_framework_from_chat(self, change_data: dict):
        """Regenerate the story framework in a background thread triggered from the chat."""
        if not self.ai_generator or not self.current_screenplay:
            return
        sp = self.current_screenplay
        series_bible = None
        custom_dur = getattr(sp, "custom_duration_seconds", 0) or 0
        sm = getattr(sp, "series_metadata", None) or {}
        bible_path = sm.get("series_bible_path", "")
        if bible_path and os.path.exists(bible_path):
            try:
                from core.series_bible import SeriesBible
                series_bible = SeriesBible.load(bible_path)
            except Exception:
                pass

        self._regen_thread = FrameworkGenerationThread(
            self.ai_generator,
            premise=sp.premise,
            title=sp.title,
            length=sp.length if hasattr(sp, "length") else "Medium",
            atmosphere=sp.atmosphere,
            genres=sp.genre,
            story_outline=sp.story_outline,
            intent=sp.intent if hasattr(sp, "intent") else "General Story",
            series_bible=series_bible,
            custom_duration_seconds=custom_dur,
        )
        self._regen_thread.finished.connect(self._on_regen_framework_done)
        self._regen_thread.error.connect(self._on_regen_framework_error)
        self._regen_thread.start()
        self.status_bar.showMessage("Regenerating framework...")
        if self.chat_panel:
            self.chat_panel.add_message("system", "Framework regeneration in progress...")

    def _on_regen_framework_done(self, new_sp: "Screenplay"):
        """Handle completion of framework regeneration from chat."""
        if not self.current_screenplay:
            return
        self.current_screenplay.acts = new_sp.acts
        if new_sp.story_outline:
            self.current_screenplay.story_outline = new_sp.story_outline
        self.current_screenplay.updated_at = datetime.now().isoformat()
        if self.framework_view:
            self.framework_view.screenplay = self.current_screenplay
            self.framework_view.update_tree()
            self.framework_view.update_premise_tab()
        self._mark_unsaved()
        self._show_toast("Framework regenerated successfully")
        if self.chat_panel:
            self.chat_panel.add_message("system", "Framework regeneration complete.")

    def _on_regen_framework_error(self, error_msg: str):
        """Handle framework regeneration error."""
        QMessageBox.critical(self, "Error", f"Framework regeneration failed:\n{error_msg}")
        if self.chat_panel:
            self.chat_panel.add_message("system", f"Framework regeneration failed: {error_msg}", is_error=True)

    def _show_toast(self, message: str, duration_ms: int = 4000):
        """Show a brief toast-style notification on the status bar and as a fading overlay."""
        self.status_bar.showMessage(message, duration_ms)
        try:
            toast = _ToastOverlay(message, self, duration_ms)
            toast.show()
        except Exception:
            pass

    def open_screenplay(self):
        """Open an existing screenplay."""
        if self.current_screenplay and self._has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Open a different story anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Storyboard", get_stories_directory(),
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if filename:
            try:
                screenplay = Screenplay.load_from_file(filename)
                self.current_screenplay = screenplay
                self.current_filename = filename
                self._mark_saved()
                
                # Show appropriate view based on structure
                if screenplay.acts:
                    # New structure - use framework view
                    self.framework_view.set_screenplay(screenplay)
                    self.framework_view.set_ai_generator(self.ai_generator)
                    self.framework_view.show()
                    self.timeline_view.hide()
                else:
                    # Legacy structure - use timeline view
                    self.timeline_view.set_screenplay(screenplay)
                    self.timeline_view.show()
                    self.framework_view.hide()
                
                self.update_status_bar()
                self.setWindowTitle(f"SceneWrite - {os.path.basename(filename)}")
                
                # Update chat panel and Higgsfield panel
                if self.chat_panel:
                    self.chat_panel.set_screenplay(screenplay)
                    self.chat_panel.set_ai_generator(self.ai_generator)
                if hasattr(self, 'hf_panel') and self.hf_panel:
                    self.hf_panel.set_screenplay(screenplay)
                
                # Track in recent files
                config.add_recent_file(filename)
                self._update_recent_files_menu()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{str(e)}")
    
    def import_story_from_text(self):
        """Import a novel/story from a text file and convert to screenplay."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured. Please set up your API key in Settings.")
            return

        from core.novel_importer import extract_text_from_file, validate_text
        from ui.novel_import_dialog import NovelImportDialog

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Story from Text", "",
            "Text Files (*.txt);;Word Documents (*.docx);;All Files (*.*)"
        )
        if not filepath:
            return

        try:
            text = extract_text_from_file(filepath)
        except ValueError as e:
            QMessageBox.critical(self, "Import Error", str(e))
            return

        is_valid, message = validate_text(text)
        if not is_valid:
            QMessageBox.warning(self, "Import Error", message)
            return

        dialog = NovelImportDialog(filepath, text, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        length = dialog.get_length()
        intent = dialog.get_intent()

        # Progress dialog
        progress = QProgressDialog("Preparing import...", None, 0, 0, self)
        progress.setWindowTitle("Importing Story")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(400)
        progress.show()

        self._novel_import_thread = NovelImportThread(self.ai_generator, text, length, intent)

        def on_progress(msg):
            progress.setLabelText(msg)

        def on_finished(screenplay):
            progress.close()
            self._novel_import_thread = None
            self.on_wizard_completed(screenplay)
            QMessageBox.information(
                self, "Import Complete",
                f"Successfully imported and converted to screenplay:\n\"{screenplay.title}\"\n\n"
                "You can now generate storyboards for each scene."
            )

        def on_error(error_msg):
            progress.close()
            self._novel_import_thread = None
            QMessageBox.critical(self, "Import Failed", f"Failed to convert story:\n{error_msg}")

        self._novel_import_thread.progress.connect(on_progress)
        self._novel_import_thread.finished.connect(on_finished)
        self._novel_import_thread.error.connect(on_error)
        self._novel_import_thread.start()

    def save_screenplay(self):
        """Save the current screenplay."""
        if not self.current_screenplay:
            return
        
        # Sync any pending UI edits (scene content, description, wardrobe) to the model
        if self.framework_view and hasattr(self.framework_view, 'sync_current_scene_to_model'):
            self.framework_view.sync_current_scene_to_model()
        
        if self.current_filename:
            try:
                self.current_screenplay.save_to_file(self.current_filename)
                self._mark_saved()
                self.status_bar.showMessage("Saved successfully", 2000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")
        else:
            self.save_screenplay_as()
    
    def save_screenplay_as(self):
        """Save the current screenplay with a new filename."""
        if not self.current_screenplay:
            return
        
        meta = getattr(self.current_screenplay, "series_metadata", None)
        if meta and meta.get("series_folder"):
            from core.series_manager import SeriesManager
            ep_filename = SeriesManager.build_episode_filename(
                meta.get("episode_number", 1),
                meta.get("episode_title", ""),
            )
            default_path = os.path.join(meta["series_folder"], ep_filename)
        else:
            default_name = (self.current_screenplay.title or "Untitled Story").strip()
            default_name = re.sub(r'[<>:"/\\|?*]', '', default_name) or "Untitled Story"
            default_path = os.path.join(get_stories_directory(), default_name + ".json")
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Story", default_path,
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if filename:
            try:
                if not filename.endswith('.json'):
                    filename += '.json'
                self.current_screenplay.save_to_file(filename)
                self.current_filename = filename
                self._mark_saved()
                self.update_status_bar()
                self._update_window_title()
                self.status_bar.showMessage("Saved successfully", 2000)
                
                # Track in recent files
                config.add_recent_file(filename)
                self._update_recent_files_menu()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")
    
    def export_screenplay(self, format_type: str):
        """Export the screenplay in the specified format."""
        if not self.require_license("Export"):
            return
        if not self.current_screenplay:
            QMessageBox.warning(self, "No Storyboard", "No storyboard to export.")
            return
        
        # Check if there are any storyboard items (either new or legacy structure)
        all_items = self.current_screenplay.get_all_storyboard_items()
        if not all_items:
            QMessageBox.warning(self, "No Storyboard", "No storyboard items to export.")
            return
        
        # Determine default filename and extension
        base_name = self.current_filename or "storyboard"
        if base_name.endswith('.json'):
            base_name = base_name[:-5]
        
        extensions = {
            "json": ("JSON Files (*.json)", ".json"),
            "csv": ("CSV Files (*.csv)", ".csv"),
            "higgsfield": ("JSON Files (*.json)", ".json"),
            "prompts": ("Text Files (*.txt)", ".txt")
        }
        
        file_filter, extension = extensions.get(format_type, ("All Files (*.*)", ""))
        
        filename, _ = QFileDialog.getSaveFileName(
            self, f"Export Storyboard as {format_type.upper()}", base_name + extension,
            file_filter
        )
        
        if filename:
            try:
                # Run image-mapping validation before Higgsfield / prompts export
                if format_type in ("higgsfield", "prompts"):
                    from core.video_prompt_builder import validate_for_generation
                    all_errors: list = []
                    for item in all_items:
                        has_images = (
                            (getattr(item, "environment_start_image", "") or "").strip()
                            or any(
                                (info.get("path") or "").strip()
                                for info in (getattr(item, "image_assignments", {}) or {}).values()
                            )
                        )
                        if not has_images:
                            continue
                        valid, errors = validate_for_generation(item)
                        if not valid:
                            all_errors.extend(f"Item #{item.sequence_number}: {e}" for e in errors)
                    if all_errors:
                        QMessageBox.warning(
                            self, "Validation Errors",
                            "Some storyboard items have image-mapping issues:\n\n"
                            + "\n".join(all_errors[:15])
                            + "\n\nPlease fix these before exporting.")
                        return

                if format_type == "json":
                    self.exporter.export_to_json(self.current_screenplay, filename)
                elif format_type == "csv":
                    self.exporter.export_to_csv(self.current_screenplay, filename)
                elif format_type == "higgsfield":
                    self.exporter.export_higgsfield_format(self.current_screenplay, filename)
                elif format_type == "prompts":
                    self.exporter.export_prompts_only(self.current_screenplay, filename)
                
                self.status_bar.showMessage(f"Exported successfully to {os.path.basename(filename)}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")
    
    def export_for_platform(self):
        """Export prompts formatted for a specific AI video platform."""
        if not self.require_license("Platform Export"):
            return
        if not self.current_screenplay:
            QMessageBox.warning(self, "No Storyboard", "No storyboard to export.")
            return
        all_items = self.current_screenplay.get_all_storyboard_items()
        if not all_items:
            QMessageBox.warning(self, "No Storyboard", "No storyboard items to export.")
            return

        from core.prompt_adapters import get_available_platforms, get_adapter

        platforms = get_available_platforms()
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Prompts for Platform")
        dialog.setModal(True)
        dialog.resize(420, 300)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Select target platform:"))

        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        platform_list = QListWidget()
        for p in platforms:
            item = QListWidgetItem(f"{p['name']}  —  {p['description']}")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            platform_list.addItem(item)
        platform_list.setCurrentRow(0)
        layout.addWidget(platform_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = platform_list.currentItem()
        if not selected:
            return
        platform_id = selected.data(Qt.ItemDataRole.UserRole)
        adapter = get_adapter(platform_id)
        if not adapter:
            return

        base_name = self.current_filename or "storyboard"
        if base_name.endswith(".json"):
            base_name = base_name[:-5]
        suggested = f"{base_name}_{platform_id}{adapter.file_extension}"

        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Prompts for {adapter.platform_name}",
            suggested,
            f"Text Files (*{adapter.file_extension});;All Files (*.*)",
        )
        if not filename:
            return

        try:
            adapter.export(self.current_screenplay, filename)
            self.status_bar.showMessage(
                f"Exported {adapter.platform_name} prompts to {os.path.basename(filename)}",
                3000,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", f"Failed to export:\n{str(e)}"
            )

    def show_premise_dialog(self):
        """Show the premise dialog."""
        dialog = PremiseDialog(self, self.ai_generator)
        dialog.premise_accepted.connect(self.on_premise_accepted)
        dialog.exec()
    
    def on_premise_accepted(self, premise: str, title: str, genres: list, atmosphere: str):
        """Handle premise acceptance."""
        # Create new screenplay with premise
        self.current_screenplay = Screenplay(title=title, premise=premise)
        self.current_screenplay.genre = genres
        self.current_screenplay.atmosphere = atmosphere
        self.current_filename = None
        self._mark_unsaved()
        self.framework_view.set_screenplay(self.current_screenplay)
        self.framework_view.set_ai_generator(self.ai_generator)
        self.framework_view.show()
        self.timeline_view.hide()
        self.update_status_bar()
        self.setWindowTitle(f"SceneWrite - {title or 'Untitled Story'}")
    
    def generate_storyboard(self):
        """Generate a storyboard from the current premise."""
        if not self.require_license("Storyboard Generation"):
            return
        if not self.current_screenplay or not self.current_screenplay.premise:
            QMessageBox.warning(
                self, "No Premise",
                "Please create or enter a premise first using 'Generate Premise' or 'New Story (AI Generated)'."
            )
            return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        # Ask for length
        length, ok = QInputDialog.getItem(
            self, "Storyboard Length", "Select storyboard length:",
            ["Micro (15-30 seconds)", "Short (30-60 seconds)", "Medium (1-3 minutes)", "Long (3-5 minutes)"],
            2, False
        )
        
        if not ok:
            return
        
        length_map = {
            "Micro (15-30 seconds)": "micro",
            "Short (30-60 seconds)": "short",
            "Medium (1-3 minutes)": "medium",
            "Long (3-5 minutes)": "long"
        }
        length_value = length_map.get(length, "medium")
        
        # Show progress dialog
        progress = QProgressDialog("Generating storyboard...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Can't cancel
        progress.show()
        
        # Create and start generation thread
        atmosphere = self.current_screenplay.atmosphere if self.current_screenplay else ""
        self.generation_thread = StoryboardGenerationThread(
            self.ai_generator,
            self.current_screenplay.premise,
            self.current_screenplay.title,
            length_value,
            atmosphere
        )
        self.generation_thread.finished.connect(
            lambda screenplay: self.on_storyboard_generated(screenplay, progress)
        )
        self.generation_thread.error.connect(
            lambda error: self.on_storyboard_error(error, progress)
        )
        self.generation_thread.start()
    
    def on_storyboard_generated(self, screenplay: Screenplay, progress: QProgressDialog):
        # Create snapshot at storyboard milestone
        self.create_snapshot(screenplay, "storyboard", "Storyboard generated")
        """Handle successful storyboard generation."""
        progress.close()
        
        # Merge with existing screenplay (keep title, premise, genre, atmosphere)
        if self.current_screenplay:
            screenplay.title = self.current_screenplay.title or screenplay.title
            screenplay.premise = self.current_screenplay.premise
            screenplay.genre = self.current_screenplay.genre
            screenplay.atmosphere = self.current_screenplay.atmosphere
        
        self.current_screenplay = screenplay
        self._mark_unsaved()
        
        # Show appropriate view
        if screenplay.acts:
            self.framework_view.set_screenplay(screenplay)
            self.framework_view.set_ai_generator(self.ai_generator)
            self.framework_view.show()
            self.timeline_view.hide()
        else:
            self.timeline_view.set_screenplay(screenplay)
            self.timeline_view.show()
            self.framework_view.hide()
        
        self.update_status_bar()
        
        item_count = len(screenplay.get_all_storyboard_items())
        self.status_bar.showMessage(
            f"Storyboard generated — {item_count} items, duration: {screenplay.get_total_duration_formatted()}", 5000)
    
    def on_storyboard_error(self, error: str, progress: QProgressDialog):
        """Handle storyboard generation error."""
        progress.close()
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate storyboard:\n{error}")
    
    def on_item_clicked(self, item_id: str):
        """Handle storyboard item click."""
        if self.current_screenplay:
            item = self.current_screenplay.get_item(item_id)
            if item:
                self.edit_item(item)
    
    def on_item_edit_requested(self, item_id: str):
        """Handle storyboard item edit request."""
        if self.current_screenplay:
            item = self.current_screenplay.get_item(item_id)
            if item:
                self.edit_item(item)
    
    def edit_item(self, item: StoryboardItem):
        """Edit a storyboard item."""
        editor = StoryboardItemEditor(item, self.current_screenplay, self.ai_generator, self)
        editor.item_saved.connect(self.on_item_saved)
        editor.exec()
    
    def on_item_saved(self, item: StoryboardItem):
        """Handle item save."""
        try:
            self._mark_unsaved()
            if not item:
                _safe_print("Warning: on_item_saved called with None item")
                return
            
            if self.framework_view and hasattr(self.framework_view, 'isVisible') and self.framework_view.isVisible():
                try:
                    if hasattr(self.framework_view, 'refresh'):
                        self.framework_view.refresh()
                except Exception as e:
                    _safe_print(f"Error refreshing framework view: {e}")
                    import traceback
                    traceback.print_exc()
            
            if self.timeline_view and hasattr(self.timeline_view, 'isVisible') and self.timeline_view.isVisible():
                try:
                    if hasattr(self.timeline_view, 'refresh'):
                        self.timeline_view.refresh()
                except Exception as e:
                    _safe_print(f"Error refreshing timeline view: {e}")
                    import traceback
                    traceback.print_exc()
            
            try:
                self.update_status_bar()
            except Exception as e:
                _safe_print(f"Error updating status bar: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            _safe_print(f"Error in on_item_saved: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Save Warning", f"Item was saved but there was an error updating the display:\n{str(e)}")
    
    def generate_story_framework(self):
        """Generate a story framework from the current premise (Phase 1)."""
        if not self.require_license("Framework Generation"):
            return
        if not self.current_screenplay or not self.current_screenplay.premise:
            QMessageBox.warning(
                self, "No Premise",
                "Please create or enter a premise first using 'Generate Premise'."
            )
            return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        # Ask for length
        length, ok = QInputDialog.getItem(
            self, "Story Framework Length", "Select story framework length:",
            ["Micro (1-5 scenes, 1 act)", "Short (9-15 scenes, 3 acts)", "Medium (15-24 scenes, 3 acts)", "Long (30-50 scenes, 5 acts)"],
            2, False
        )
        
        if not ok:
            return
        
        length_map = {
            "Micro (1-5 scenes, 1 act)": "micro",
            "Short (9-15 scenes, 3 acts)": "short",
            "Medium (15-24 scenes, 3 acts)": "medium",
            "Long (30-50 scenes, 5 acts)": "long"
        }
        length_value = length_map.get(length, "medium")
        
        # Show progress dialog
        progress = QProgressDialog("Generating story framework...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        
        # Create and start generation thread
        genres = self.current_screenplay.genre if self.current_screenplay else []
        atmosphere = self.current_screenplay.atmosphere if self.current_screenplay else ""
        story_outline = getattr(self.current_screenplay, 'story_outline', None)
        self.framework_thread = FrameworkGenerationThread(
            self.ai_generator,
            self.current_screenplay.premise,
            self.current_screenplay.title,
            length_value,
            atmosphere,
            genres,
            story_outline
        )
        self.framework_thread.finished.connect(
            lambda screenplay: self.on_framework_generated(screenplay, progress)
        )
        self.framework_thread.error.connect(
            lambda error: self.on_framework_error(error, progress)
        )
        self.framework_thread.start()
    
    def on_framework_generated(self, screenplay: Screenplay, progress: QProgressDialog):
        """Handle successful framework generation."""
        progress.close()
        
        # Merge with existing screenplay (keep title, premise, genre, atmosphere)
        if self.current_screenplay:
            screenplay.title = self.current_screenplay.title or screenplay.title
            screenplay.premise = self.current_screenplay.premise
            screenplay.genre = self.current_screenplay.genre
            screenplay.atmosphere = self.current_screenplay.atmosphere
        
        self.current_screenplay = screenplay
        self._mark_unsaved()
        self.framework_view.set_screenplay(screenplay)
        self.framework_view.set_ai_generator(self.ai_generator)
        self.framework_view.show()
        self.timeline_view.hide()
        self.update_status_bar()
        
        total_scenes = sum(len(act.scenes) for act in screenplay.acts)
        self.status_bar.showMessage(
            f"Framework generated — {len(screenplay.acts)} acts, {total_scenes} scenes", 5000)
    
    def on_framework_error(self, error: str, progress: QProgressDialog):
        """Handle framework generation error."""
        progress.close()
        QMessageBox.critical(self, "Generation Failed", f"Failed to generate framework:\n{error}")
    
    def on_scene_selected(self, scene: StoryScene):
        """Handle scene selection."""
        # Update chat panel context
        if self.chat_panel:
            self.chat_panel.set_context(scene=scene)
    
    def on_storyboard_items_selected(self, items: List[StoryboardItem]):
        """Handle storyboard items selection."""
        # Update chat panel context
        if self.chat_panel:
            self.chat_panel.set_context(items=items)
    
    def on_storyboard_items_selected(self, items: List[StoryboardItem]):
        """Handle storyboard items selection."""
        # Update chat panel context
        if self.chat_panel:
            self.chat_panel.set_context(items=items)
    
    def on_scene_edit_requested(self, scene: StoryScene):
        """Handle scene edit request."""
        if not self.current_screenplay:
            return
        
        editor = SceneFrameworkEditor(scene, self.current_screenplay, self.ai_generator, self)
        editor.scene_saved.connect(self.on_scene_saved)
        editor.exec()
    
    def on_scene_saved(self, scene: StoryScene):
        """Handle scene save."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("on_scene_saved() started")
            debug_log(f"Scene ID: {scene.scene_id if scene else 'None'}")
        except:
            pass
        
        self._mark_unsaved()
        try:
            debug_log("Updating scene in screenplay structure...")
            # Ensure the scene is properly updated in the screenplay's act structure
            if self.current_screenplay and scene:
                debug_log(f"Current screenplay has {len(self.current_screenplay.acts)} acts")
                # Find and update the scene in the act structure
                scene_found = False
                for act_idx, act in enumerate(self.current_screenplay.acts):
                    debug_log(f"Checking act {act_idx}, has {len(act.scenes) if hasattr(act, 'scenes') else 0} scenes")
                    if not hasattr(act, 'scenes'):
                        debug_log(f"Act {act_idx} has no scenes attribute")
                        continue
                    for i, act_scene in enumerate(act.scenes):
                        if hasattr(act_scene, 'scene_id') and hasattr(scene, 'scene_id'):
                            if act_scene.scene_id == scene.scene_id:
                                debug_log(f"Found matching scene at act {act_idx}, scene {i}")
                                # Update the scene in the act's list
                                act.scenes[i] = scene
                                scene_found = True
                                break
                    if scene_found:
                        break
                if not scene_found:
                    debug_log("WARNING: Scene not found in any act")
            
            debug_log("Updating framework view...")
            if self.framework_view:
                # Update current scene reference if it's the same scene
                if hasattr(self.framework_view, 'current_scene') and self.framework_view.current_scene:
                    if hasattr(self.framework_view.current_scene, 'scene_id') and hasattr(scene, 'scene_id'):
                        if self.framework_view.current_scene.scene_id == scene.scene_id:
                            debug_log("Updating current_scene reference in framework_view")
                            self.framework_view.current_scene = scene
                debug_log("Refreshing framework view...")
                self.framework_view.refresh()
                debug_log("Framework view refreshed")
            debug_log("Updating status bar...")
            self.update_status_bar()
            debug_log("on_scene_saved() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in on_scene_saved()", e)
            except:
                pass
            try:
                log_exception("Error updating after scene save", e)
            except:
                import traceback
                _safe_print(f"Error updating after scene save: {e}")
                traceback.print_exc()
            try:
                log_path = get_log_file_path()
            except:
                log_path = "N/A"
            QMessageBox.critical(self, "Update Error", 
                f"An error occurred while updating after saving the scene. Please check the log file for details.\n\nLog file location: {log_path}")
    
    def on_storyboard_item_edit_requested(self, item: StoryboardItem):
        """Handle storyboard item edit request."""
        if self.current_screenplay:
            self.edit_item(item)
    
    def show_settings(self):
        """Show settings dialog (all tabs)."""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_ai_generator()
            self.setup_auto_save()
            from config import config
            ui_settings = config.get_ui_settings()
            dialog.apply_ui_settings(ui_settings["theme"], ui_settings["font_size"])

    def show_ai_settings(self):
        """Show AI settings dialog."""
        dialog = SettingsDialog(self, show_tab="ai")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_ai_generator()

    def _refresh_ai_generator(self):
        """Reload or create the AI generator after settings change and propagate to all panels."""
        if self.ai_generator:
            self.ai_generator.reload_settings()
        else:
            self.init_ai_generator()
        if self.chat_panel:
            self.chat_panel.set_ai_generator(self.ai_generator)
        if self.framework_view:
            self.framework_view.set_ai_generator(self.ai_generator)
    
    def show_instructions(self):
        """Show instructions dialog."""
        dialog = InstructionsDialog(self)
        dialog.exec()
    
    def show_about(self):
        """Show about dialog."""
        dialog = AboutDialog(self)
        dialog.exec()
    
    def show_license(self):
        """Show license dialog."""
        dialog = LicenseDialog(self)
        dialog.exec()

    # ── License System ───────────────────────────────────────────────

    def set_license_state(self, state: LicenseState):
        """Store the license state and update UI restrictions accordingly."""
        self._license_state = state
        restricted = state.status not in (
            LicenseStatus.VALID,
            LicenseStatus.TRIAL_ACTIVE,
        )
        if restricted:
            self.status_bar.showMessage(state.message or "License required for full features.")
        elif state.status == LicenseStatus.TRIAL_ACTIVE and state.days_remaining is not None:
            self.status_bar.showMessage(
                f"Trial: {state.days_remaining} day{'s' if state.days_remaining != 1 else ''} remaining",
                0,
            )

    @property
    def is_licensed(self) -> bool:
        """True if the app has a valid license or active trial."""
        if self._license_state is None:
            return True  # not yet checked
        return self._license_state.status in (
            LicenseStatus.VALID,
            LicenseStatus.TRIAL_ACTIVE,
        )

    def require_license(self, feature_name: str = "This feature") -> bool:
        """Gate a feature behind license validation.

        Returns True if the user is licensed and may proceed.
        Shows a message and returns False otherwise.
        """
        if self.is_licensed:
            return True
        QMessageBox.warning(
            self,
            "License Required",
            f"{feature_name} requires an active license or trial.\n\n"
            "Go to Help > Enter License Key to activate.",
        )
        return False

    def show_activation_dialog(self):
        """Show the license activation dialog from the menu."""
        dlg = ActivationDialog(parent=self, allow_trial=False, allow_close=True)
        dlg.exec()
        if dlg.was_activated:
            self._license_state = check_license()
            self.set_license_state(self._license_state)
            self.status_bar.showMessage("License activated.", 5000)

    # ── Update System ────────────────────────────────────────────────

    def start_update_check(self):
        """Launch a background thread to check for updates (called once at startup)."""
        self._update_thread = UpdateCheckThread()
        self._update_thread.update_available.connect(self._on_update_available)
        self._update_thread.start()

    def _on_update_available(self, info):
        """Handle the signal from the background update checker."""
        dlg = UpdateAvailableDialog(info, parent=self)
        dlg.exec()

    def check_for_updates_manual(self):
        """Triggered from Help > Check for Updates (always checks, ignores interval)."""
        from core.update_checker import check_for_update, record_update_check

        self.status_bar.showMessage("Checking for updates...")
        QApplication.processEvents()

        info = check_for_update()
        record_update_check(config)

        if info is not None:
            self.status_bar.clearMessage()
            dlg = UpdateAvailableDialog(info, parent=self)
            dlg.exec()
        else:
            self.status_bar.showMessage("You're running the latest version.", 5000)
            QMessageBox.information(
                self, "No Updates",
                "You are already running the latest version of SceneWrite."
            )

    # ── Episodic Series System ───────────────────────────────────────

    def _update_window_title(self, screenplay=None):
        sp = screenplay or self.current_screenplay
        if not sp:
            self.setWindowTitle("SceneWrite")
            return
        meta = getattr(sp, "series_metadata", None)
        if meta:
            series_title = meta.get("series_title", "")
            ep_num = meta.get("episode_number", "")
            ep_title = meta.get("episode_title", "")
            self.setWindowTitle(f"SceneWrite - {series_title} - Episode {ep_num}: {ep_title}")
        else:
            title = sp.title or "Untitled Story"
            self.setWindowTitle(f"SceneWrite - {title}")

    def _get_current_series_folder(self) -> str:
        if self.current_screenplay and getattr(self.current_screenplay, "series_metadata", None):
            return self.current_screenplay.series_metadata.get("series_folder", "")
        return ""

    def new_series(self):
        """Start a new series by opening the wizard in series mode."""
        self.new_screenplay()

    def new_episode(self):
        """Add a new episode to an existing series by opening the wizard."""
        self.new_screenplay()

    def open_series_dashboard(self):
        """Open the Series Dashboard for an existing series."""
        from core.series_manager import SeriesManager
        from ui.series_dashboard import SeriesDashboard

        folder = self._get_current_series_folder()
        if not folder:
            series_list = SeriesManager.list_all_series()
            if not series_list:
                QMessageBox.information(self, "No Series", "No series found. Create one via File > New Story.")
                return
            from PyQt6.QtWidgets import QInputDialog
            titles = [s["title"] for s in series_list]
            chosen, ok = QInputDialog.getItem(self, "Select Series", "Choose a series:", titles, 0, False)
            if not ok:
                return
            idx = titles.index(chosen)
            folder = series_list[idx]["folder"]

        try:
            bible = SeriesManager.load_series(folder)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load series:\n{e}")
            return

        dashboard = SeriesDashboard(bible, folder, self)
        dashboard.episode_open_requested.connect(self._open_episode_file)
        dashboard.new_episode_requested.connect(self.new_episode)
        dashboard.edit_bible_requested.connect(lambda: self._open_bible_editor(bible, folder))
        dashboard.exec()

    def edit_series_bible(self):
        """Open the Series Bible editor for the current series."""
        from core.series_manager import SeriesManager

        folder = self._get_current_series_folder()
        if not folder:
            series_list = SeriesManager.list_all_series()
            if not series_list:
                QMessageBox.information(self, "No Series", "No series found.")
                return
            from PyQt6.QtWidgets import QInputDialog
            titles = [s["title"] for s in series_list]
            chosen, ok = QInputDialog.getItem(self, "Select Series", "Choose a series:", titles, 0, False)
            if not ok:
                return
            idx = titles.index(chosen)
            folder = series_list[idx]["folder"]

        try:
            bible = SeriesManager.load_series(folder)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load series:\n{e}")
            return

        self._open_bible_editor(bible, folder)

    def _open_bible_editor(self, bible, folder):
        from ui.series_bible_editor import SeriesBibleEditor
        editor = SeriesBibleEditor(bible, folder, self)
        editor.exec()

    def _open_episode_file(self, filepath: str):
        """Open a specific episode file from the series dashboard."""
        if not os.path.isfile(filepath):
            QMessageBox.warning(self, "File Not Found", f"Episode file not found:\n{filepath}")
            return
        if self.current_screenplay and self._has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Open a different episode anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
        try:
            screenplay = Screenplay.load_from_file(filepath)
            self.current_screenplay = screenplay
            self.current_filename = filepath
            self._has_unsaved_changes = False
            if self.framework_view:
                self.framework_view.set_screenplay(screenplay)
                self.framework_view.set_ai_generator(self.ai_generator)
                self.framework_view.show()
            if self.chat_panel:
                self.chat_panel.set_screenplay(screenplay)
                self.chat_panel.set_ai_generator(self.ai_generator)
            if hasattr(self, 'hf_panel') and self.hf_panel:
                self.hf_panel.set_screenplay(screenplay)
            self.update_status_bar()
            self._update_window_title(screenplay)
            config.add_recent_file(filepath)
            self._update_recent_files_menu()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open episode:\n{e}")

    def convert_to_series(self):
        """Convert the current standalone story into Episode 1 of a new series."""
        from core.series_manager import SeriesManager

        if not self.current_screenplay:
            QMessageBox.warning(self, "No Story", "No story is currently loaded.")
            return

        if getattr(self.current_screenplay, "series_metadata", None):
            QMessageBox.information(self, "Already a Series", "This story is already part of a series.")
            return

        title, ok = QInputDialog.getText(
            self, "Series Title",
            "Enter a title for the new series:",
            QLineEdit.EchoMode.Normal,
            self.current_screenplay.title or "",
        )
        if not ok or not title.strip():
            return

        try:
            folder, bible = SeriesManager.convert_to_series(self.current_screenplay, title.strip())
            # Save the screenplay into the series folder as Episode 1
            ep_filename = SeriesManager.build_episode_filename(1, self.current_screenplay.series_metadata.get("episode_title", "Pilot"))
            ep_path = os.path.join(folder, ep_filename)
            self.current_screenplay.save_to_file(ep_path)
            self.current_filename = ep_path
            self._mark_unsaved()
            self._update_window_title()
            self.update_status_bar()
            QMessageBox.information(
                self, "Converted",
                f"Story converted to series '{title.strip()}'.\n"
                f"Saved as Episode 1 in:\n{folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert to series:\n{e}")

    def finalize_episode(self):
        """Finalize the current episode and update the Series Bible."""
        from core.series_manager import SeriesManager

        if not self.current_screenplay:
            QMessageBox.warning(self, "No Story", "No story is currently loaded.")
            return

        meta = getattr(self.current_screenplay, "series_metadata", None)
        if not meta:
            QMessageBox.information(self, "Not an Episode", "The current story is not part of a series.")
            return

        folder = meta.get("series_folder", "")
        if not folder or not SeriesManager.is_series_folder(folder):
            QMessageBox.warning(self, "Series Not Found", "Cannot locate the series folder.")
            return

        reply = QMessageBox.question(
            self, "Finalize Episode",
            f"Finalize Episode {meta.get('episode_number', '?')}: {meta.get('episode_title', '')}?\n\n"
            "This will mark the episode as complete and update the Series Bible.\n"
            "You can optionally generate an AI summary afterwards.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            bible = SeriesManager.load_series(folder)

            summary = ""
            if self.ai_generator:
                gen_reply = QMessageBox.question(
                    self, "Generate Summary",
                    "Would you like to generate an AI summary for this episode?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if gen_reply == QMessageBox.StandardButton.Yes:
                    try:
                        result = self.ai_generator.generate_episode_summary(self.current_screenplay)
                        summary = result.get("summary", "")
                        timeline_events = result.get("timeline_events", [])
                        SeriesManager.finalize_episode(
                            self.current_screenplay, bible, folder,
                            summary=summary,
                            story_arc=result.get("story_arc", ""),
                            timeline_events=timeline_events,
                        )
                    except Exception as e:
                        QMessageBox.warning(self, "Summary Failed", f"AI summary failed: {e}\nFinalizing without summary.")
                        SeriesManager.finalize_episode(self.current_screenplay, bible, folder)
                else:
                    SeriesManager.finalize_episode(self.current_screenplay, bible, folder)
            else:
                SeriesManager.finalize_episode(self.current_screenplay, bible, folder)

            # Save the screenplay
            if self.current_filename:
                self.current_screenplay.save_to_file(self.current_filename)
            self._update_window_title()
            self.update_status_bar()
            QMessageBox.information(self, "Finalized", "Episode finalized and Series Bible updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to finalize episode:\n{e}")

    def show_ui_settings(self):
        """Show UI settings dialog."""
        dialog = SettingsDialog(self, show_tab="ui")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update auto-save interval
            self.setup_auto_save()
            # Apply UI settings (theme and font size)
            from config import config
            ui_settings = config.get_ui_settings()
            self.apply_ui_settings(ui_settings["theme"], ui_settings["font_size"])
    
    def show_story_settings(self):
        """Show story settings dialog for the current project or pre-creation defaults."""
        if self.current_screenplay:
            ss = getattr(self.current_screenplay, "story_settings", None) or {}
            old_visual_style = ss.get("visual_style") or "photorealistic"

            story_tab = self.framework_view.story_settings_tab
            dialog = QDialog(self)
            dialog.setWindowTitle("Story Settings")
            dialog.setModal(True)
            dialog.resize(600, 650)
            layout = QVBoxLayout(dialog)
            layout.addWidget(story_tab)
            story_tab.show()
            story_tab.load_settings(self.current_screenplay)
            dialog.exec()
            layout.removeWidget(story_tab)
            story_tab.setParent(self.framework_view)
            story_tab.hide()

            ss = getattr(self.current_screenplay, "story_settings", None) or {}
            new_visual_style = ss.get("visual_style") or "photorealistic"
            if new_visual_style != old_visual_style:
                self._offer_batch_regenerate_reference_prompts(new_visual_style)
        else:
            import types
            from core.screenplay_engine import get_default_story_settings
            from .story_settings_tab import StorySettingsTab

            initial = self._pending_story_settings or get_default_story_settings()
            proxy = types.SimpleNamespace(story_settings=dict(initial))

            story_tab = StorySettingsTab()
            dialog = QDialog(self)
            dialog.setWindowTitle("Story Settings — Pre-Creation Defaults")
            dialog.setModal(True)
            dialog.resize(600, 650)
            layout = QVBoxLayout(dialog)
            info_label = QLabel(
                "Configure story settings before creating a new story.\n"
                "These settings will be applied when you create your next story."
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet(
                "color: #666; padding: 8px; font-style: italic;"
            )
            layout.addWidget(info_label)
            layout.addWidget(story_tab)
            story_tab.load_settings(proxy)
            dialog.exec()

            self._pending_story_settings = proxy.story_settings

    def _offer_batch_regenerate_reference_prompts(self, new_style: str):
        """Ask user whether to regenerate all prompts after a visual style change."""
        from core.screenplay_engine import VISUAL_STYLE_OPTIONS

        ibm = getattr(self.framework_view, "identity_block_manager", None)
        if not ibm or not ibm.ai_generator or not self.current_screenplay:
            return

        ref_count = 0
        for meta in self.current_screenplay.identity_block_metadata.values():
            if meta.get("status") == "approved" and meta.get("reference_image_prompt", "").strip():
                ref_count += 1
        wv = getattr(self.current_screenplay, "character_wardrobe_variants", {})
        for variants in wv.values():
            for v in variants:
                if v.get("identity_block", "").strip() and v.get("reference_image_prompt", "").strip():
                    ref_count += 1

        sb_count = 0
        for scene in self.current_screenplay.get_all_scenes():
            for item in scene.storyboard_items:
                if (getattr(item, "image_prompt", "") or "").strip():
                    sb_count += 1

        total_count = ref_count + sb_count
        if total_count == 0:
            return

        style_name = VISUAL_STYLE_OPTIONS.get(new_style, new_style)
        detail_lines = []
        if ref_count:
            detail_lines.append(f"  - {ref_count} reference image prompt(s)")
        if sb_count:
            detail_lines.append(f"  - {sb_count} storyboard hero frame prompt(s)")
        detail_text = "\n".join(detail_lines)

        reply = QMessageBox.question(
            self,
            "Regenerate Prompts for New Style?",
            f"You changed the visual style to '{style_name}'.\n\n"
            f"The following existing prompts still use the previous style:\n"
            f"{detail_text}\n\n"
            f"Would you like to regenerate them all now to match the new style?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        progress = QProgressDialog(
            "Regenerating prompts for new visual style...", None, 0, 0, self
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        try:
            result = ibm.batch_regenerate_reference_prompts(new_style)

            sb_regen = self._batch_regenerate_storyboard_keyframes()

            progress.close()

            parts = []
            if result["identity_count"]:
                parts.append(f"{result['identity_count']} identity block(s)")
            if result["wardrobe_count"]:
                parts.append(f"{result['wardrobe_count']} wardrobe variant(s)")
            if sb_regen:
                parts.append(f"{sb_regen} storyboard hero frame(s)")
            msg = f"Regenerated prompts for {', '.join(parts)}."
            if result["errors"]:
                msg += f"\n\n{len(result['errors'])} error(s) occurred:\n" + "\n".join(
                    result["errors"][:5]
                )
            total = result["identity_count"] + result["wardrobe_count"] + sb_regen
            if total > 0:
                QMessageBox.information(self, "Regeneration Complete", msg)
            elif result["errors"]:
                QMessageBox.warning(self, "Regeneration Failed", msg)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(
                self, "Error", f"Batch regeneration failed:\n\n{str(exc)}"
            )

    def _batch_regenerate_storyboard_keyframes(self) -> int:
        """Regenerate all storyboard item keyframe (hero frame) prompts using current visual style.

        Uses build_keyframe_prompt which resolves the visual style from story settings.
        Returns the number of items regenerated.
        """
        from core.video_prompt_builder import build_keyframe_prompt

        if not self.current_screenplay:
            return 0

        count = 0
        for scene in self.current_screenplay.get_all_scenes():
            for item in scene.storyboard_items:
                old_prompt = (getattr(item, "image_prompt", "") or "").strip()
                if not old_prompt:
                    continue
                new_prompt = build_keyframe_prompt(item, self.current_screenplay, scene)
                if new_prompt and new_prompt.strip():
                    item.image_prompt = new_prompt.strip()
                    count += 1
        return count

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

