"""
Main entry point for SceneWrite.
"""

import sys
import os

# Hide the console window on Windows (must run before any output)
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
    except Exception:
        pass

# Add debug logging first, before anything else
try:
    from debug_log import debug_log, debug_exception
    debug_log("=" * 80)
    debug_log("APPLICATION STARTING")
    debug_log(f"Python version: {sys.version}")
    debug_log(f"Working directory: {os.getcwd()}")
except Exception as e:
    # If debug logging fails, try to write to a simple file
    try:
        with open('debug_crash.log', 'a') as f:
            f.write(f"Failed to import debug_log: {e}\n")
    except:
        pass

try:
    debug_log("Importing PyQt6...")
    from PyQt6.QtWidgets import QApplication, QComboBox, QAbstractSpinBox
    from PyQt6.QtCore import Qt, QObject, QEvent
    from PyQt6.QtGui import QIcon, QFont
    debug_log("PyQt6 imported successfully")
except Exception as e:
    debug_exception("Failed to import PyQt6", e)
    raise


class ScrollGuardFilter(QObject):
    """Prevent the mouse scroll wheel from changing combo boxes and spin boxes.

    Installed once on QApplication so every widget is covered without
    subclassing or per-widget event filters.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QAbstractSpinBox)):
                event.ignore()
                return True
        return False

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    debug_log("Importing MainWindow...")
    from ui.main_window import MainWindow
    debug_log("MainWindow imported successfully")
except Exception as e:
    debug_exception("Failed to import MainWindow", e)
    raise

try:
    debug_log("Importing config...")
    from config import config, APP_VERSION
    debug_log("Config imported successfully")
except Exception as e:
    debug_exception("Failed to import config", e)
    raise

try:
    debug_log("Importing license manager...")
    from core.license_manager import (
        LicenseStatus, check_license, get_machine_id,
    )
    from ui.activation_dialog import ActivationDialog, TrialExpiredDialog
    debug_log("License imports successful")
except Exception as e:
    debug_exception("Failed to import license modules", e)
    raise

def apply_ui_settings():
    """Apply theme and font size from config to the application."""
    app = QApplication.instance()
    if app is None:
        return
    
    ui_settings = config.get_ui_settings()
    theme = ui_settings.get("theme", "light")
    font_size = ui_settings.get("font_size", 12)
    
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

def main():
    """Main application entry point."""
    try:
        debug_log("Creating QApplication...")
        app = QApplication(sys.argv)
        debug_log("QApplication created")
        
        app.setApplicationName("SceneWrite")
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName("SceneWrite")
        debug_log("Application properties set")
        
        # Set application icon (works for taskbar, title bar, Alt+Tab)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        icon_candidates = [
            'SceneWrite_Logo.ico',
            'SceneWrite_Logo.icns',
            'SceneWrite_Logo.png',
        ]
        icon_path = None
        for candidate in icon_candidates:
            p = os.path.join(base_path, candidate)
            if os.path.exists(p):
                icon_path = p
                break
        if icon_path:
            app.setWindowIcon(QIcon(icon_path))
            debug_log(f"Application icon set from {icon_path}")
        else:
            debug_log(f"No icon file found in {base_path}")
        
        # Set application style
        debug_log("Setting application style...")
        app.setStyle('Fusion')
        debug_log("Application style set")
        
        # Prevent scroll wheel from changing combo boxes and spin boxes
        scroll_guard = ScrollGuardFilter(app)
        app.installEventFilter(scroll_guard)
        debug_log("Scroll-wheel guard installed")
        
        # Apply UI settings from config
        debug_log("Applying UI settings...")
        apply_ui_settings()
        debug_log("UI settings applied")
        
        # Load user cinematic whitelists into runtime sets
        debug_log("Syncing cinematic markup whitelists...")
        try:
            from core.markup_whitelist import sync_runtime_whitelists
            sync_runtime_whitelists()
            debug_log("Cinematic whitelists synced")
        except Exception as e:
            debug_log(f"Whitelist sync skipped: {e}")

        # ── License gate ─────────────────────────────────────────────
        debug_log("Checking license...")
        license_state = check_license()
        debug_log(f"License status: {license_state.status.value}")

        if license_state.status == LicenseStatus.NO_LICENSE:
            dlg = ActivationDialog(allow_trial=True, allow_close=False)
            result = dlg.exec()
            if dlg.was_activated or dlg.was_trial_started:
                license_state = check_license()
            else:
                debug_log("User closed activation dialog without activating — exiting.")
                sys.exit(0)

        elif license_state.status == LicenseStatus.TRIAL_EXPIRED:
            while True:
                dlg = TrialExpiredDialog(message=license_state.message)
                dlg.exec()
                if dlg.wants_activate:
                    act_dlg = ActivationDialog(allow_trial=False, allow_close=True)
                    act_dlg.exec()
                    if act_dlg.was_activated:
                        license_state = check_license()
                        break
                else:
                    break

        elif license_state.status in (LicenseStatus.EXPIRED, LicenseStatus.INVALID):
            while True:
                dlg = TrialExpiredDialog(message=license_state.message)
                dlg.exec()
                if dlg.wants_activate:
                    act_dlg = ActivationDialog(allow_trial=False, allow_close=True)
                    act_dlg.exec()
                    if act_dlg.was_activated:
                        license_state = check_license()
                        break
                else:
                    break

        debug_log(f"Proceeding with license status: {license_state.status.value}")
        # ─────────────────────────────────────────────────────────────

        # Create and show main window
        debug_log("Creating MainWindow...")
        window = MainWindow()
        debug_log("MainWindow created")

        window.set_license_state(license_state)
        
        debug_log("Showing MainWindow...")
        window.show()
        debug_log("MainWindow shown")
        
        # Apply UI settings on startup
        debug_log("Applying UI settings on startup...")
        ui_settings = config.get_ui_settings()
        window.apply_ui_settings(ui_settings["theme"], ui_settings["font_size"])
        debug_log("UI settings applied on startup")
        
        debug_log("Starting event loop...")
        # Start event loop
        sys.exit(app.exec())
    except Exception as e:
        debug_exception("FATAL ERROR in main()", e)
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()

