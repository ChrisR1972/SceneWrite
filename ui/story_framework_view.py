"""
Story Framework View for MoviePrompterAI.
Displays acts and scenes in a tree structure, with editing capabilities.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QTextEdit, QLabel, QPushButton,
    QGroupBox, QFormLayout, QListWidget, QListWidgetItem, QScrollArea,
    QMessageBox, QProgressDialog, QMenu, QInputDialog, QDialog,
    QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QSizePolicy,
    QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QIcon, QAction, QTextCursor, QPixmap
from .image_thumbnail import ClickableImageLabel
from typing import Optional, List, Dict
from core.screenplay_engine import Screenplay, StoryAct, StoryScene, StoryboardItem, BrandContext
from core.ai_generator import AIGenerator
from core.workflow_profile import WorkflowProfileManager, WorkflowProfile
from core.spell_checker import enable_spell_checking, enable_cinematic_checking
from .identity_block_manager import IdentityBlockManager
from .story_settings_tab import StorySettingsTab

# Logger functions - temporarily disabled to prevent crashes
def log_exception(msg, exc):
    try:
        import traceback
        print(f"ERROR: {msg}: {exc}")
        traceback.print_exc()
    except:
        pass
def log_error(msg):
    try:
        print(f"ERROR: {msg}")
    except:
        pass
def log_info(msg):
    pass
def get_log_file_path():
    return "N/A"

class SceneDescriptionTextEdit(QTextEdit):
    """QTextEdit with Add Entity at top of standard context menu."""
    
    add_entity_requested = pyqtSignal()
    
    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        add_action = QAction("Add Entity", self)
        add_action.triggered.connect(self.add_entity_requested.emit)
        if menu.actions():
            menu.insertAction(menu.actions()[0], add_action)
            menu.insertSeparator(menu.actions()[1])
        else:
            menu.addAction(add_action)
            menu.addSeparator()
        menu.exec(event.globalPos())


class SceneContentTextEdit(QTextEdit):
    """QTextEdit with cinematic markup context menu, spell-check, and token highlighting.
    
    Provides:
    - Right-click markup application (Action, SFX, Character, Object, Vehicle, Environment)
    - Whitelist addition for Action and SFX (with safety filter + confirmation popup)
    - Markup removal without whitelist changes
    - Spell-check suggestions integrated into the same menu
    - Instance-level ignore for unknown tokens
    - Spellcheck-style underline highlighting for unmarked cinematic tokens
    """
    
    _MARKUP_PATTERNS = [
        (r'(?<!\w)_([^_]+)_(?!\w)', "environment", 1),
        (r'\[([^\]]+)\]', "object", 1),
        (r'\{([^}]+)\}', "vehicle", 1),
        (r'\(([^)]+)\)', "sfx", 1),
        (r'\*([^*]+)\*', "action", 1),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cinematic_ignore_words: set = set()
    
    def contextMenuEvent(self, event):
        import re
        from core.markup_whitelist import (
            add_to_action_whitelist, add_to_sfx_whitelist,
            is_valid_action_candidate, is_valid_sfx_candidate,
            normalize_sfx,
        )
        
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(event.pos())
        
        # Try to get user selection first; fall back to word under cursor
        sel_cursor = self.textCursor()
        if sel_cursor.hasSelection():
            word = sel_cursor.selectedText().strip()
            cursor = sel_cursor
        else:
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            word = cursor.selectedText().strip()
        
        if not word:
            menu.exec(event.globalPos())
            return
        
        full_text = self.toPlainText()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        
        # Detect if click is inside existing markup
        current_markup = None
        markup_span = None
        inner_word = word
        for pat, mtype, grp in self._MARKUP_PATTERNS:
            for m in re.finditer(pat, full_text):
                if m.start() <= sel_start and sel_end <= m.end():
                    current_markup = mtype
                    markup_span = (m.start(), m.end())
                    inner_word = m.group(grp)
                    break
            if current_markup:
                break
        
        first_action = menu.actions()[0] if menu.actions() else None
        
        # ── SPELL CHECK SUGGESTIONS ──
        self._add_spellcheck_items(menu, cursor, word, first_action)
        
        # ── SEPARATOR ──
        if first_action:
            menu.insertSeparator(first_action)
        else:
            menu.addSeparator()
        
        # ── MARKUP SECTION ──
        markup_menu = QMenu("Mark As", self)
        
        for label, ctype, fmt_example in [
            ("Action", "action", f"*{word}*"),
            ("SFX", "sfx", f"({normalize_sfx(word)})"),
            ("Character", "character", word.upper()),
            ("Object", "object", f"[{word}]"),
            ("Vehicle", "vehicle", "{" + word + "}"),
            ("Environment", "environment", f"_{word}_"),
        ]:
            a = QAction(f"{label}  \u2192  {fmt_example}", self)
            ctype_copy = ctype
            word_copy = word
            def apply_markup(checked=False, ct=ctype_copy, w=word_copy):
                self._apply_markup(ct, w)
            a.triggered.connect(apply_markup)
            markup_menu.addAction(a)
        
        if first_action:
            menu.insertMenu(first_action, markup_menu)
        else:
            menu.addMenu(markup_menu)
        
        # ── WHITELIST SECTION (Action + SFX only) ──
        whitelist_menu = QMenu("Add to Whitelist", self)
        
        action_valid, action_reason = is_valid_action_candidate(word)
        sfx_valid, sfx_reason = is_valid_sfx_candidate(word)
        
        add_action_wl = QAction("Add to Action Whitelist", self)
        if action_valid:
            word_for_action = word
            def do_add_action(checked=False, w=word_for_action):
                self._add_to_whitelist("action", w)
            add_action_wl.triggered.connect(do_add_action)
        else:
            add_action_wl.setEnabled(False)
            add_action_wl.setToolTip(action_reason or "")
        whitelist_menu.addAction(add_action_wl)
        
        add_sfx_wl = QAction("Add to SFX Whitelist", self)
        if sfx_valid:
            word_for_sfx = word
            def do_add_sfx(checked=False, w=word_for_sfx):
                self._add_to_whitelist("sfx", w)
            add_sfx_wl.triggered.connect(do_add_sfx)
        else:
            add_sfx_wl.setEnabled(False)
            add_sfx_wl.setToolTip(sfx_reason or "")
        whitelist_menu.addAction(add_sfx_wl)
        
        if first_action:
            menu.insertMenu(first_action, whitelist_menu)
        else:
            menu.addMenu(whitelist_menu)
        
        # ── REMOVE MARKUP (only if inside existing markup) ──
        if current_markup and markup_span:
            remove_action = QAction("Remove Markup", self)
            span_start, span_end = markup_span
            iw = inner_word
            def do_remove(checked=False, s=span_start, e=span_end, raw=iw):
                self._remove_markup(s, e, raw)
            remove_action.triggered.connect(do_remove)
            if first_action:
                menu.insertAction(first_action, remove_action)
            else:
                menu.addAction(remove_action)
        
        # ── IGNORE TOKEN ──
        ignore_act = QAction("Ignore Token", self)
        word_to_ignore = word
        def do_ignore(checked=False, w=word_to_ignore):
            self._ignore_token(w)
        ignore_act.triggered.connect(do_ignore)
        if first_action:
            menu.insertAction(first_action, ignore_act)
        else:
            menu.addAction(ignore_act)
        
        # ── SEPARATOR before standard actions ──
        if first_action:
            menu.insertSeparator(first_action)
        else:
            menu.addSeparator()
        
        menu.exec(event.globalPos())
    
    def _add_spellcheck_items(self, menu, cursor, word, first_action):
        """Add spell-check suggestions to the context menu."""
        spell_checker = self.property("spell_checker")
        if not spell_checker:
            return
        
        clean_word = word.strip("'-")
        if not clean_word:
            return
        
        try:
            misspelled = clean_word.lower() in spell_checker.unknown([clean_word.lower()])
        except Exception:
            return
        
        if not misspelled:
            return
        
        from core.spell_checker import _rank_suggestions, _match_case
        
        candidates = spell_checker.candidates(clean_word) or set()
        suggestions = _rank_suggestions(spell_checker, clean_word, candidates)[:5]
        
        if suggestions:
            for suggestion in suggestions:
                replacement = _match_case(word, suggestion)
                a = QAction(replacement, self)
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                def apply_repl(checked=False, repl=replacement, s=start, e=end):
                    rc = self.textCursor()
                    rc.setPosition(s)
                    rc.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                    rc.insertText(repl)
                a.triggered.connect(apply_repl)
                if first_action:
                    menu.insertAction(first_action, a)
                else:
                    menu.addAction(a)
        else:
            no_a = QAction("No suggestions", self)
            no_a.setEnabled(False)
            if first_action:
                menu.insertAction(first_action, no_a)
            else:
                menu.addAction(no_a)
        
        # Add to dictionary / Ignore word
        document = self.document()
        highlighter = self.property("spell_highlighter") or self.property("cinematic_highlighter")
        
        add_dict = QAction("Add to dictionary", self)
        def do_add_dict(checked=False, w=clean_word.lower()):
            try:
                spell_checker.word_frequency.add(w)
                if highlighter:
                    highlighter.rehighlight()
            except Exception:
                pass
        add_dict.triggered.connect(do_add_dict)
        
        ignore_spell = QAction("Ignore spelling", self)
        def do_ignore_spell(checked=False, w=clean_word.lower()):
            try:
                ignore_words = set(document.property("spell_ignore_words") or [])
                ignore_words.add(w)
                document.setProperty("spell_ignore_words", ignore_words)
                if highlighter:
                    highlighter.rehighlight()
            except Exception:
                pass
        ignore_spell.triggered.connect(do_ignore_spell)
        
        if first_action:
            menu.insertAction(first_action, add_dict)
            menu.insertAction(first_action, ignore_spell)
            menu.insertSeparator(first_action)
        else:
            menu.addAction(add_dict)
            menu.addAction(ignore_spell)
            menu.addSeparator()
    
    def _detect_markup_at_position(self, text: str, pos: int, word: str):
        """Return markup type if pos is inside markup, else None."""
        import re
        for pat, mtype, grp in self._MARKUP_PATTERNS:
            for m in re.finditer(pat, text):
                if m.start() <= pos <= m.end():
                    return mtype
        return None
    
    def _get_markup_span(self, full_text: str, sel_start: int, sel_end: int):
        """Find the full markup span containing the selection.
        
        Returns (replace_start, replace_end, inner_word) or None.
        """
        import re
        for pat, mtype, grp in self._MARKUP_PATTERNS:
            for m in re.finditer(pat, full_text):
                if m.start() <= sel_start and sel_end <= m.end():
                    return m.start(), m.end(), m.group(grp)
        return None
    
    def _apply_markup(self, ctype: str, word: str):
        """Apply cinematic markup to the current selection or word under cursor."""
        import re
        from core.markup_whitelist import normalize_sfx
        
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        full_text = self.toPlainText()
        inner_word = cursor.selectedText().strip() or word
        
        # Check if inside existing markup — expand selection to full span
        replace_start, replace_end = sel_start, sel_end
        span = self._get_markup_span(full_text, sel_start, sel_end)
        if span:
            replace_start, replace_end, inner_word = span
        
        # Build replacement text
        if ctype == "environment":
            new_text = f"_{inner_word}_"
        elif ctype == "character":
            new_text = inner_word.upper()
        elif ctype == "vehicle":
            new_text = "{" + inner_word + "}"
        elif ctype == "object":
            new_text = f"[{inner_word}]"
        elif ctype == "action":
            new_text = f"*{inner_word}*"
        elif ctype == "sfx":
            sfx_norm = normalize_sfx(inner_word)
            new_text = f"({sfx_norm})"
        else:
            return
        
        # Apply the replacement
        cursor.setPosition(replace_start)
        cursor.setPosition(replace_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_text)
        
        # For Action and SFX: offer whitelist addition via confirmation popup
        if ctype in ("action", "sfx"):
            self._offer_whitelist_addition(ctype, inner_word)
    
    def _offer_whitelist_addition(self, ctype: str, word: str):
        """Show confirmation popup to add word to whitelist after markup application."""
        from core.markup_whitelist import (
            add_to_action_whitelist, add_to_sfx_whitelist,
            is_valid_action_candidate, is_valid_sfx_candidate,
        )
        
        type_label = "Action" if ctype == "action" else "SFX"
        
        # Check safety first
        if ctype == "action":
            valid, reason = is_valid_action_candidate(word)
        else:
            valid, reason = is_valid_sfx_candidate(word)
        
        if not valid:
            return
        
        reply = QMessageBox.question(
            self, "Add to Whitelist",
            f'You marked "{word}" as {type_label}.\n\n'
            f'Would you like to permanently add it to the {type_label} Whitelist?\n'
            f'(This will auto-detect it in future scenes.)',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if ctype == "action":
                added = add_to_action_whitelist(word)
            else:
                added = add_to_sfx_whitelist(word)
            
            if added:
                self._refresh_highlighting()
    
    def _add_to_whitelist(self, ctype: str, word: str):
        """Directly add a word to the whitelist (from the Add to Whitelist submenu)."""
        from core.markup_whitelist import (
            add_to_action_whitelist, add_to_sfx_whitelist,
            is_valid_action_candidate, is_valid_sfx_candidate,
        )
        
        type_label = "Action" if ctype == "action" else "SFX"
        
        if ctype == "action":
            valid, reason = is_valid_action_candidate(word)
        else:
            valid, reason = is_valid_sfx_candidate(word)
        
        if not valid:
            QMessageBox.warning(
                self, "Cannot Add to Whitelist",
                f'"{word}" does not qualify as a physical {type_label}.\n\n{reason}'
            )
            return
        
        if ctype == "action":
            added = add_to_action_whitelist(word)
        else:
            added = add_to_sfx_whitelist(word)
        
        if added:
            self._show_status(f'"{word}" added to {type_label} Whitelist')
            self._refresh_highlighting()
        else:
            self._show_status(f'"{word}" is already in the {type_label} Whitelist')
    
    def _remove_markup(self, span_start: int, span_end: int, raw_word: str):
        """Remove markup delimiters without touching whitelists."""
        cursor = self.textCursor()
        cursor.setPosition(span_start)
        cursor.setPosition(span_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(raw_word)
    
    def _ignore_token(self, word: str):
        """Add word to instance-level ignore set and refresh highlighting."""
        self._cinematic_ignore_words.add(word)
        self._cinematic_ignore_words.add(word.lower())
        highlighter = self.property("cinematic_highlighter")
        if highlighter and hasattr(highlighter, 'add_cinematic_ignore_word'):
            highlighter.add_cinematic_ignore_word(word)
            highlighter.rehighlight()
    
    def _show_status(self, message: str, timeout: int = 3000):
        """Show a brief message on the main window's status bar (if available)."""
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, 'status_bar'):
                main_win.status_bar.showMessage(message, timeout)
        except Exception:
            pass

    def _refresh_highlighting(self):
        """Trigger a re-highlight after whitelist or markup changes."""
        from core.cinematic_token_detector import invalidate_cache
        invalidate_cache()
        highlighter = self.property("cinematic_highlighter") or self.property("spell_highlighter")
        if highlighter:
            try:
                highlighter.rehighlight()
            except Exception:
                pass


class AddEntityDialog(QDialog):
    """Dialog to select an entity (character, environment, vehicle, object) for insertion into scene description."""
    
    def __init__(self, entities: dict, parent=None):
        super().__init__(parent)
        self.entities = entities
        self.selected_name: Optional[str] = None
        self.selected_type: Optional[str] = None
        self.setWindowTitle("Add Entity")
        self.setMinimumSize(320, 360)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        type_labels = {
            "character": "Characters",
            "environment": "Environments / Locations",
            "vehicle": "Vehicles",
            "object": "Objects"
        }
        for etype in ["character", "environment", "vehicle", "object"]:
            names = self.entities.get(etype, [])
            if not names:
                continue
            header = QListWidgetItem(f"—— {type_labels[etype]} ——")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setData(Qt.ItemDataRole.UserRole, None)
            self.list_widget.addItem(header)
            for name in sorted(names, key=lambda x: (x or "").lower()):
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, {"name": name, "type": etype})
                self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
    
    def _get_selection(self) -> bool:
        cur = self.list_widget.currentItem()
        if not cur:
            return False
        data = cur.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("name") and data.get("type"):
            self.selected_name = data["name"]
            self.selected_type = data["type"]
            return True
        return False
    
    def _on_accept(self):
        if self._get_selection():
            self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select an entity from the list.")
    
    def _on_item_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if isinstance(data, dict) and data.get("name") and data.get("type"):
            self.selected_name = data["name"]
            self.selected_type = data["type"]
            self.accept()


class StoryStructureTreeWidget(QTreeWidget):
    """Custom tree widget that handles drag and drop for story structure."""
    
    items_reordered = pyqtSignal()  # Emitted when items are reordered
    
    def dragMoveEvent(self, event):
        """Handle drag move events to show proper drop indicators."""
        dragged_item = self.currentItem()
        if not dragged_item:
            event.ignore()
            return
        
        dragged_data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        if not dragged_data:
            event.ignore()
            return
        
        dragged_type = dragged_data[0]
        drop_item = self.itemAt(event.position().toPoint())
        
        # For scenes, only allow dropping on acts or as siblings of other scenes
        if dragged_type == "scene":
            if drop_item:
                drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)
                if drop_data:
                    drop_type = drop_data[0]
                    if drop_type == "act":
                        # Can drop on act
                        event.accept()
                        return
                    elif drop_type == "scene":
                        # Can drop on scene (will insert before/after)
                        event.accept()
                        return
                else:
                    # Dropping on root - not allowed
                    event.ignore()
                    return
            else:
                event.ignore()
                return
        
        # For acts, only allow dropping at root level
        elif dragged_type == "act":
            if not drop_item or not drop_item.data(0, Qt.ItemDataRole.UserRole):
                # Dropping at root level - allowed
                event.accept()
                return
            drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)
            if drop_data and drop_data[0] == "act":
                # Can drop on another act (will reorder)
                event.accept()
                return
            else:
                # Can't drop act on a scene
                event.ignore()
                return
        
        event.accept()
    
    def dropEvent(self, event):
        """Handle drop events and emit signal for reordering."""
        # Get the item being dragged
        dragged_item = self.currentItem()
        if not dragged_item:
            # Let parent handle it
            super().dropEvent(event)
            return
        
        # Get drop position
        drop_item = self.itemAt(event.position().toPoint())
        
        # Get dragged item data
        dragged_data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        if not dragged_data:
            # Let parent handle it
            super().dropEvent(event)
            return
        
        dragged_type = dragged_data[0]
        
        # Handle scene drops - scenes should only be reordered within their act or moved to another act
        if dragged_type == "scene":
            dragged_scene = dragged_data[1]
            dragged_parent = dragged_item.parent()
            
            # Determine target act
            target_act_item = None
            target_index = -1
            
            if drop_item:
                drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)
                if drop_data:
                    drop_type = drop_data[0]
                    if drop_type == "act":
                        # Dropping on an act - add to end of that act
                        target_act_item = drop_item
                        target_index = drop_item.childCount()
                    elif drop_type == "scene":
                        # Dropping on another scene - insert before/after that scene
                        target_act_item = drop_item.parent()
                        if target_act_item:
                            # Find the index of the drop target scene
                            for i in range(target_act_item.childCount()):
                                if target_act_item.child(i) == drop_item:
                                    # Determine if dropping above or below based on position
                                    item_rect = self.visualItemRect(drop_item)
                                    drop_y = event.position().toPoint().y()
                                    if drop_y < item_rect.center().y():
                                        target_index = i  # Insert before
                                    else:
                                        target_index = i + 1  # Insert after
                                    break
                else:
                    # Dropping on root - not allowed for scenes
                    event.ignore()
                    return
            else:
                # No drop target - ignore
                event.ignore()
                return
            
            if not target_act_item:
                event.ignore()
                return
            
            # Store scene data before any operations
            scene = dragged_data[1]
            scene_id = scene.scene_id
            item_data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
            
            # Get the index before moving (for same-act moves)
            old_index = -1
            if dragged_parent:
                old_index = dragged_parent.indexOfChild(dragged_item)
            
            # Use default drop behavior - this handles the move and keeps item in tree
            super().dropEvent(event)
            
            # Only proceed if drop was accepted
            if not event.isAccepted():
                return
            
            # After default drop, fix any nesting issues
            # The item should now be moved, but might be nested under another scene
            current_parent = dragged_item.parent()
            
            # If item is nested under another scene (wrong parent), move it to the act
            if current_parent and current_parent != target_act_item:
                parent_data = current_parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_data and parent_data[0] == "scene":
                    # Item is nested under a scene - move it to the act
                    current_parent.removeChild(dragged_item)
                    # Find correct index in target act
                    if dragged_parent == target_act_item and old_index >= 0:
                        # Moving within same act - use calculated index
                        if old_index < target_index:
                            target_index -= 1
                    target_act_item.insertChild(target_index, dragged_item)
                elif parent_data and parent_data[0] == "act":
                    # Parent is an act but not the target - fix it
                    if current_parent != target_act_item:
                        current_parent.removeChild(dragged_item)
                        target_act_item.insertChild(target_index, dragged_item)
            
            # If item has no parent (was lost), restore it
            if not dragged_item.parent():
                target_act_item.insertChild(target_index, dragged_item)
            
            # Verify and restore scene data
            final_data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
            if not final_data or final_data[0] != "scene" or final_data[1].scene_id != scene_id:
                dragged_item.setData(0, Qt.ItemDataRole.UserRole, item_data)
            
            # Remove any nested children (prevents submenu)
            while dragged_item.childCount() > 0:
                child = dragged_item.child(0)
                dragged_item.removeChild(child)
            
            # Expand target act to show the moved scene
            target_act_item.setExpanded(True)
            
            # Select the moved item and scroll to it
            self.setCurrentItem(dragged_item)
            self.scrollToItem(dragged_item)
            
            # Accept the event - DO NOT call parent dropEvent
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            
            # Force immediate UI update to show the moved item
            self.update()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Emit signal after delay to ensure tree is stable
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(150, self.items_reordered.emit)
            return
        
        # For acts, use default behavior but prevent nesting
        elif dragged_type == "act":
            # Acts can only be reordered at root level
            if drop_item:
                drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)
                if drop_data and drop_data[0] != "act":
                    # Can't drop act on a scene
                    event.ignore()
                    return
            
            # For acts, we can use default behavior but need to prevent nesting
            # Check if dropping would create nesting
            root_item = self.topLevelItem(0)
            if drop_item and drop_item.parent() and drop_item.parent() != root_item:
                # Would create nesting - prevent it
                event.ignore()
                return
            
            # Use default behavior for act reordering
            super().dropEvent(event)
            
            if event.isAccepted():
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, self.items_reordered.emit)
            return
        
        # Default behavior for other cases - ignore
        event.ignore()

class FrameworkGenerationThread(QThread):
    """Thread for generating story framework to avoid blocking UI."""
    
    finished = pyqtSignal(Screenplay)
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, title, length, atmosphere, genres, story_outline=None, intent="General Story", brand_context=None):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.title = title
        self.length = length
        self.atmosphere = atmosphere
        self.genres = genres
        self.story_outline = story_outline
        self.intent = intent
        self.brand_context = brand_context
    
    def run(self):
        """Generate framework in background thread."""
        try:
            screenplay = self.ai_generator.generate_story_framework(
                self.premise, self.title, self.length, self.atmosphere, self.genres, self.story_outline, self.intent, self.brand_context
            )
            self.finished.emit(screenplay)
        except Exception as e:
            self.error.emit(str(e))

class SceneContentGenerationThread(QThread):
    """Thread for generating full scene content from description."""
    
    finished = pyqtSignal(str, object)  # Emits (generated content, list of drift warnings)
    error = pyqtSignal(str)  # Emits error message
    
    def __init__(self, ai_generator: AIGenerator, scene_description: str, 
                 word_count: int, screenplay: Screenplay, scene: StoryScene):
        super().__init__()
        self.ai_generator = ai_generator
        self.scene_description = scene_description
        self.word_count = word_count
        self.screenplay = screenplay
        self.scene = scene
    
    def run(self):
        """Generate scene content."""
        try:
            result = self.ai_generator.generate_scene_content(
                scene_description=self.scene_description,
                word_count=self.word_count,
                screenplay=self.screenplay,
                scene=self.scene
            )
            content = result[0] if isinstance(result, tuple) else result
            drift_warnings = result[1] if isinstance(result, tuple) and len(result) > 1 else []
            self.finished.emit(content, drift_warnings)
        except Exception as e:
            self.error.emit(str(e))

class BatchPhysicalAppearanceThread(QThread):
    """Thread for regenerating physical appearance for multiple characters."""
    
    progress = pyqtSignal(int, int, int, dict)  # (index, total, result)
    finished_all = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, screenplay, indices_to_regenerate: list):
        super().__init__()
        self.ai_generator = ai_generator
        self.screenplay = screenplay
        self.indices_to_regenerate = indices_to_regenerate  # List of (index, char_dict) tuples
    
    def run(self):
        try:
            premise = getattr(self.screenplay, 'premise', '')
            title = getattr(self.screenplay, 'title', '')
            genres = getattr(self.screenplay, 'genres', [])
            atmosphere = getattr(self.screenplay, 'atmosphere', '')
            story_outline = getattr(self.screenplay, 'story_outline', {}) or {}
            main_storyline = story_outline.get("main_storyline", "")
            characters = story_outline.get("characters", []) or []
            total = len(self.indices_to_regenerate)
            max_retries = 2  # Up to 3 attempts per character (1 initial + 2 retries)
            for i, idx in enumerate(self.indices_to_regenerate):
                if idx < 0 or idx >= len(characters):
                    continue
                char = characters[idx] if isinstance(characters[idx], dict) else {}
                char_name = str(char.get("name", "Unnamed")).strip()
                char_outline = str(char.get("outline", "") or "").strip()
                char_species = str(char.get("species", "Human") or "Human").strip()
                other_chars = [c for j, c in enumerate(characters) if j != idx and isinstance(c, dict)]
                result = None
                for attempt in range(max_retries + 1):
                    result = self.ai_generator.regenerate_character_details(
                        premise, genres, atmosphere, title, main_storyline,
                        char_name, "physical_appearance", existing_characters=other_chars,
                        character_outline=char_outline, species=char_species
                    )
                    phys = str(result.get("physical_appearance", "") or "").strip()
                    if phys and len(phys) >= 50:
                        break
                    # Empty or too short - retry
                if result:
                    self.progress.emit(idx, i + 1, total, result)
            self.finished_all.emit()
        except Exception as e:
            self.error.emit(str(e))


class CharacterRegenerationThread(QThread):
    """Thread for regenerating character details to avoid blocking UI."""
    
    finished = pyqtSignal(int, dict)  # Emits (character_index, result_dict)
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, premise, genres, atmosphere, title, main_storyline, character_name, regenerate_type, existing_characters=None, character_outline="", species="Human"):
        super().__init__()
        self.ai_generator = ai_generator
        self.premise = premise
        self.genres = genres
        self.atmosphere = atmosphere
        self.title = title
        self.main_storyline = main_storyline
        self.character_name = character_name
        self.regenerate_type = regenerate_type
        self.existing_characters = existing_characters or []
        self.character_outline = character_outline or ""
        self.species = species or "Human"
        self.character_index = -1  # Will be set before starting
    
    def set_character_index(self, index):
        """Set the character index for this regeneration."""
        self.character_index = index
    
    def run(self):
        """Regenerate character details in background thread."""
        try:
            result = self.ai_generator.regenerate_character_details(
                self.premise, self.genres, self.atmosphere, self.title,
                self.main_storyline, self.character_name, self.regenerate_type,
                existing_characters=self.existing_characters,
                character_outline=self.character_outline,
                species=self.species
            )
            self.finished.emit(self.character_index, result)
        except Exception as e:
            self.error.emit(str(e))

class SceneStoryboardGenerationThread(QThread):
    """Thread for generating scene storyboard to avoid blocking UI."""
    
    finished = pyqtSignal(StoryScene)
    error = pyqtSignal(str)
    
    def __init__(self, ai_generator, scene, screenplay):
        super().__init__()
        self.ai_generator = ai_generator
        self.scene = scene
        self.screenplay = screenplay
    
    def run(self):
        """Generate scene storyboard in background thread."""
        try:
            self.ai_generator.generate_scene_storyboard(self.scene, self.screenplay)
            self.finished.emit(self.scene)
        except Exception as e:
            self.error.emit(str(e))

class StoryFrameworkView(QWidget):
    """Main view for story framework with acts and scenes."""
    
    scene_selected = pyqtSignal(StoryScene)
    scene_edit_requested = pyqtSignal(StoryScene)
    storyboard_item_edit_requested = pyqtSignal(StoryboardItem)
    storyboard_items_selected = pyqtSignal(list)  # Emits list of selected StoryboardItem objects
    data_changed = pyqtSignal()  # Emitted when scene data is modified and should be persisted
    
    def _show_status(self, message: str, timeout: int = 3000):
        """Show a brief message on the main window's status bar (if available)."""
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, 'status_bar'):
                main_win.status_bar.showMessage(message, timeout)
        except Exception:
            pass

    def _is_visual_art_mode(self) -> bool:
        """Return True if the current screenplay uses the Visual Art / Abstract intent."""
        if not self.screenplay:
            return False
        intent = getattr(self.screenplay, 'intent', '') or ''
        return 'visual art' in intent.lower() or 'abstract' in intent.lower()

    def _update_visual_art_visibility(self):
        """Show or hide UI elements that are not relevant in Visual Art mode."""
        is_art = self._is_visual_art_mode()
        if hasattr(self, 'generate_row_widget'):
            self.generate_row_widget.setVisible(not is_art)
        if hasattr(self, 'content_group'):
            self.content_group.setVisible(not is_art)
        if hasattr(self, 'reextract_entities_btn'):
            self.reextract_entities_btn.setVisible(not is_art)
        if hasattr(self, 'wardrobe_group'):
            self.wardrobe_group.setVisible(not is_art)
        if hasattr(self, 'visual_art_row'):
            self.visual_art_row.setVisible(is_art)

    def _on_visual_art_style_changed(self):
        """Handle visual art style combo change — persist to current scene."""
        if not self.current_scene:
            return
        style = self.visual_art_style_combo.currentData() or "progressive"
        self.current_scene.visual_art_style = style

    def _create_visual_art_environment(self):
        """Create an environment identity block for a Visual Art scene.

        Skips entity extraction (which relies on narrative markup) and instead
        generates a rich environment description directly from the scene's
        framework description using an AI call.
        """
        if not self.current_scene or not self.screenplay:
            return

        scene = self.current_scene
        env_id = getattr(scene, 'environment_id', None)

        # Reuse existing environment if already created and not empty
        if env_id and env_id in self.screenplay.identity_block_metadata:
            existing_notes = (self.screenplay.identity_block_metadata[env_id].get("user_notes") or "").strip()
            if existing_notes and not existing_notes.startswith("Setting:"):
                return

        env_name = f"{scene.title} Environment"
        env_id = self.screenplay.create_placeholder_identity_block(
            env_name, "environment", scene.scene_id
        )
        scene.environment_id = env_id
        self.screenplay.update_identity_block_metadata(
            env_id, extras_present=False, foreground_zone="clear",
            is_primary_environment=True,
        )

        description = (scene.description or "").strip()
        if not description:
            self.screenplay.update_identity_block_metadata(
                env_id, user_notes=f"Setting: {scene.title}"
            )
            return

        # Use AI to expand the short description into a rich environment note
        env_notes = self._extract_environment_from_content(description, scene.title)
        self.screenplay.update_identity_block_metadata(env_id, user_notes=env_notes)

        # Refresh identity blocks UI
        if hasattr(self, 'identity_blocks_tab') and self.identity_blocks_tab:
            self.identity_blocks_tab.refresh_entity_list()

    def _sanitize_character_registry(self):
        """Clean the character registry by removing non-person entities and folding body parts.
        
        Needed for stories created before the wizard cleanup was added, or when
        the AI generates bad registry entries.  Modifies the registry in-place.
        """
        if not self.screenplay or not self.ai_generator:
            return
        registry = getattr(self.screenplay, "character_registry", None)
        if not registry:
            return
        
        cleaned = []
        cleaned_lower = set()
        changed = False
        
        for name in registry:
            original = name
            
            # Filter non-person entities (UI, software, abstract visuals)
            if self.ai_generator._is_company_or_concept_entity(name):
                print(f"  [registry cleanup] removed non-person: {name}")
                changed = True
                continue
            
            # Fold body-part possessives ("filmmaker's hands" → "filmmaker")
            bp = self.ai_generator._split_possessive_body_part(name)
            if bp:
                name = self.ai_generator._normalize_character_name_for_identity(bp[0]) or bp[0]
                if name != original:
                    print(f"  [registry cleanup] folded body-part: {original} → {name}")
                    changed = True
            else:
                # Strip leading articles ("A Filmmaker" → "Filmmaker")
                stripped = self.ai_generator._normalize_character_name_for_identity(name)
                if stripped and stripped.lower() != name.lower():
                    print(f"  [registry cleanup] stripped article: {name} → {stripped}")
                    name = stripped
                    changed = True
            
            if name.lower() not in cleaned_lower:
                # Check for confusing word overlap with already-accepted names
                name_words = set(name.upper().split())
                is_overlap = False
                if len(name_words) >= 2:
                    for accepted in cleaned:
                        accepted_words = set(accepted.upper().split())
                        if len(name_words & accepted_words) >= 2 and name.upper() != accepted.upper():
                            print(f"  [registry cleanup] removing overlap: '{name}' conflicts with '{accepted}'")
                            is_overlap = True
                            changed = True
                            break
                if not is_overlap:
                    cleaned.append(name)
                    cleaned_lower.add(name.lower())
            elif name.lower() != original.lower():
                changed = True  # duplicate after folding
        
        if changed:
            self.screenplay.character_registry = cleaned
            print(f"  [registry cleanup] registry now: {cleaned}")

    def __init__(self, parent=None):
        try:
            from debug_log import debug_log, debug_exception
            debug_log("StoryFrameworkView.__init__ started")
        except:
            pass
        
        try:
            debug_log("Calling super().__init__() for StoryFrameworkView...")
            super().__init__(parent)
            debug_log("super().__init__() completed for StoryFrameworkView")
        except Exception as e:
            try:
                debug_exception("Error in StoryFrameworkView super().__init__()", e)
            except:
                pass
            raise
        
        try:
            debug_log("Initializing StoryFrameworkView attributes...")
            self.screenplay: Optional[Screenplay] = None
            self.char_regeneration_thread: Optional[CharacterRegenerationThread] = None
            self.batch_physical_thread: Optional[BatchPhysicalAppearanceThread] = None
            self.current_scene: Optional[StoryScene] = None
            self.ai_generator: Optional[AIGenerator] = None
            debug_log("Calling init_ui() for StoryFrameworkView...")
            self.init_ui()
            debug_log("StoryFrameworkView.__init__ completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in StoryFrameworkView.__init__", e)
            except:
                pass
            raise
    
    def init_ui(self):
        """Initialize the UI."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("StoryFrameworkView.init_ui() started")
        except:
            pass
        
        try:
            debug_log("Creating main layout...")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            debug_log("Main layout created")
            
            # Create splitter for resizable panels
            debug_log("Creating splitter...")
            splitter = QSplitter(Qt.Orientation.Horizontal)
            layout.addWidget(splitter)
            debug_log("Splitter created")
            
            # Left panel: Act/Scene tree
            debug_log("Creating left panel...")
            self.create_left_panel(splitter)
            debug_log("Left panel created")
            
            # Center panel: Scene editor and storyboard
            debug_log("Creating center panel...")
            self.create_center_panel(splitter)
            debug_log("Center panel created")
            
            # Right panel removed - user requested removal of plot points column
            
            # Set splitter proportions (only 2 panels now)
            debug_log("Setting splitter sizes...")
            splitter.setSizes([250, 800])
            debug_log("StoryFrameworkView.init_ui() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in StoryFrameworkView.init_ui()", e)
            except:
                pass
            raise
    
    def create_left_panel(self, parent):
        """Create the left panel with act/scene tree."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("create_left_panel() started")
        except:
            pass
        
        try:
            debug_log("Creating left widget and layout...")
            left_widget = QWidget()
            left_layout = QVBoxLayout(left_widget)
            left_layout.setContentsMargins(5, 5, 5, 5)
            debug_log("Left widget and layout created")
            
            # Button bar for add actions
            debug_log("Creating button bar...")
            button_layout = QHBoxLayout()
            self.add_act_btn = QPushButton("+ Act")
            self.add_act_btn.clicked.connect(self.on_add_act_clicked)
            self.add_act_btn.setToolTip("Add a new act")
            button_layout.addWidget(self.add_act_btn)
            
            self.add_scene_btn = QPushButton("+ Scene")
            self.add_scene_btn.clicked.connect(self.on_add_scene_clicked)
            self.add_scene_btn.setToolTip("Add a new scene to selected act")
            self.add_scene_btn.setEnabled(False)
            button_layout.addWidget(self.add_scene_btn)
            
            button_layout.addStretch()
            left_layout.addLayout(button_layout)
            debug_log("Button bar created")
            
            # Tree widget (custom class for drag and drop)
            debug_log("Creating tree widget...")
            self.tree = StoryStructureTreeWidget()
            debug_log("Tree widget created")
            self.tree.setHeaderLabel("Story Structure")
            debug_log("Tree header label set")
            self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
            self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
            self.tree.items_reordered.connect(self.on_tree_items_reordered)
            debug_log("Tree signals connected")
            
            # Enable drag and drop
            debug_log("Setting up drag and drop...")
            self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
            self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.tree.setDragEnabled(True)
            self.tree.setAcceptDrops(True)
            self.tree.setDropIndicatorShown(True)
            debug_log("Drag and drop configured")
            
            # Set selection mode to single selection for cleaner drag and drop
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
            
            # Context menu
            debug_log("Setting up context menu...")
            self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
            debug_log("Context menu configured")
            
            left_layout.addWidget(self.tree)
            debug_log("Tree added to layout")
            
            parent.addWidget(left_widget)
            debug_log("Left widget added to parent")
            debug_log("create_left_panel() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in create_left_panel()", e)
            except:
                pass
            raise
    
    def create_center_panel(self, parent):
        """Create the center panel with scene editor and storyboard."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("create_center_panel() started")
        except:
            pass
        
        try:
            debug_log("Creating center widget and layout...")
            center_widget = QWidget()
            center_layout = QVBoxLayout(center_widget)
            center_layout.setContentsMargins(5, 5, 5, 5)
            debug_log("Center widget and layout created")
            
            # Tab widget for different views
            debug_log("Creating tab widget...")
            self.tabs = QTabWidget()
            debug_log("Tab widget created")
            
            # Keep current scene highlighted when switching tabs
            try:
                self.tabs.currentChanged.connect(self._on_tab_changed)
            except Exception:
                pass
            
            # Premise tab
            debug_log("Creating premise tab...")
            self.premise_tab = self.create_premise_tab()
            self.tabs.addTab(self.premise_tab, "Premise")
            debug_log("Premise tab created")

            # Scene Content tab
            debug_log("Creating framework tab...")
            self.framework_tab = self.create_framework_tab()
            self.tabs.addTab(self.framework_tab, "Scene Content")
            debug_log("Framework tab created")

            # Identity Blocks tab
            debug_log("Creating identity blocks tab...")
            self.identity_blocks_tab = self.create_identity_blocks_tab()
            self.tabs.addTab(self.identity_blocks_tab, "Identity Blocks")
            debug_log("Identity blocks tab created")

            # Character Details tab
            debug_log("Creating character details tab...")
            self.character_details_tab = self.create_character_details_tab()
            self.tabs.addTab(self.character_details_tab, "Character Details")
            debug_log("Character details tab created")

            # Storyboard tab
            debug_log("Creating storyboard tab...")
            self.storyboard_tab = self.create_storyboard_tab()
            self.tabs.addTab(self.storyboard_tab, "Storyboard")
            debug_log("Storyboard tab created")

            # Story Settings (not a tab — opened from Settings menu)
            debug_log("Creating story settings tab...")
            self.story_settings_tab = StorySettingsTab()
            self.story_settings_tab.data_changed.connect(self.data_changed.emit)
            debug_log("Story settings tab created")
            
            center_layout.addWidget(self.tabs)
            debug_log("Tabs added to center layout")
            parent.addWidget(center_widget)
            debug_log("Center widget added to parent")
            debug_log("create_center_panel() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in create_center_panel()", e)
            except:
                pass
            raise
    
    def create_framework_tab(self) -> QWidget:
        """Create the framework editing tab."""
        # Outer scroll area so the entire tab is scrollable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Scene title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Scene Title:"))
        self.scene_title_label = QLabel("No scene selected")
        self.scene_title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_layout.addWidget(self.scene_title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # Scene description
        desc_group = QGroupBox("Scene Description")
        desc_layout = QVBoxLayout()
        self.scene_description_edit = SceneDescriptionTextEdit()
        self.scene_description_edit.setPlaceholderText("Scene description (3-5 sentences)...")
        self.scene_description_edit.setMaximumHeight(150)
        self.scene_description_edit.add_entity_requested.connect(self._on_add_entity_clicked)
        desc_layout.addWidget(self.scene_description_edit)
        
        # Generate with AI section (hidden in Visual Art mode)
        self.generate_row_widget = QWidget()
        generate_layout = QHBoxLayout(self.generate_row_widget)
        generate_layout.setContentsMargins(0, 0, 0, 0)
        generate_layout.addWidget(QLabel("Generate Full Scene Content:"))
        
        # Word count selector
        self.word_count_combo = QComboBox()
        self.word_count_combo.addItems(["200", "400", "600"])
        self.word_count_combo.setCurrentIndex(1)  # Default to 400
        generate_layout.addWidget(QLabel("Target words:"))
        generate_layout.addWidget(self.word_count_combo)
        
        self.generate_scene_content_btn = QPushButton("Generate with AI")
        self.generate_scene_content_btn.clicked.connect(self.on_generate_scene_content_clicked)
        generate_layout.addWidget(self.generate_scene_content_btn)
        generate_layout.addStretch()
        desc_layout.addWidget(self.generate_row_widget)
        
        # Visual Art style selector (shown only in Visual Art mode)
        self.visual_art_row = QWidget()
        va_layout = QHBoxLayout(self.visual_art_row)
        va_layout.setContentsMargins(0, 0, 0, 0)
        va_layout.addWidget(QLabel("Visual Style:"))
        self.visual_art_style_combo = QComboBox()
        self.visual_art_style_combo.addItem("Progressive (evolving visual)", "progressive")
        self.visual_art_style_combo.addItem("Looping (seamless loop)", "looping")
        self.visual_art_style_combo.setToolTip(
            "Progressive: the visual evolves and transforms over time.\n"
            "Looping: the final frame returns to the opening state for a seamless loop."
        )
        self.visual_art_style_combo.currentIndexChanged.connect(self._on_visual_art_style_changed)
        va_layout.addWidget(self.visual_art_style_combo)
        va_layout.addStretch()
        self.visual_art_row.setVisible(False)
        desc_layout.addWidget(self.visual_art_row)
        
        desc_group.setLayout(desc_layout)

        # Wardrobe State Selector (per character per scene) — collapsible, above scene description
        self.wardrobe_group = QGroupBox("Wardrobe State (per character)")
        self.wardrobe_group.setCheckable(True)
        self.wardrobe_group.setChecked(True)
        self.wardrobe_group.setToolTip(
            "Select wardrobe state for each character BEFORE generating scene content.\n"
            "Option 1: Keep same wardrobe from previous scene.\n"
            "Option 2: New wardrobe described in scene.\n"
            "Option 3: Clothing change happens during scene."
        )
        wardrobe_inner = QVBoxLayout()
        self.wardrobe_container = QWidget()
        self.wardrobe_form = QFormLayout(self.wardrobe_container)
        wardrobe_inner.addWidget(self.wardrobe_container)
        self.wardrobe_group.setLayout(wardrobe_inner)
        self.wardrobe_group.toggled.connect(self.wardrobe_container.setVisible)
        layout.addWidget(self.wardrobe_group)
        self.wardrobe_selectors: Dict[str, QComboBox] = {}
        self.wardrobe_edits: Dict[str, QLineEdit] = {}

        layout.addWidget(desc_group)
        
        # Generated scene content display (hidden in Visual Art mode)
        self.content_group = QGroupBox("Generated Scene Content")
        content_layout = QVBoxLayout()
        self.scene_content_display = SceneContentTextEdit()
        self.scene_content_display.setPlaceholderText("Generated scene content will appear here...")
        self.scene_content_display.setMinimumHeight(300)
        content_layout.addWidget(self.scene_content_display)
        self.content_group.setLayout(content_layout)
        layout.addWidget(self.content_group)
        
        # Approve and Re-extract buttons
        save_layout = QHBoxLayout()
        self.save_scene_btn = QPushButton("Approve")
        self.save_scene_btn.clicked.connect(self.on_save_scene_clicked)
        self.save_scene_btn.setEnabled(False)
        save_layout.addWidget(self.save_scene_btn)
        self.reextract_entities_btn = QPushButton("Re-extract Entities")
        self.reextract_entities_btn.setToolTip("Clear current entities and re-extract from scene content (for testing)")
        self.reextract_entities_btn.clicked.connect(self.on_reextract_entities_clicked)
        self.reextract_entities_btn.setEnabled(False)
        save_layout.addWidget(self.reextract_entities_btn)
        layout.addLayout(save_layout)
        
        layout.addStretch()
        
        # Enable spell checking for editable text widgets
        enable_spell_checking(self.scene_description_edit)
        # Scene content uses the combined cinematic markup + spell-check highlighter
        enable_cinematic_checking(self.scene_content_display)
        
        # Tab key moves focus (not indentation)
        self.scene_description_edit.setTabChangesFocus(True)
        self.scene_content_display.setTabChangesFocus(True)
        
        scroll_area.setWidget(inner_widget)
        return scroll_area
    
    def create_storyboard_tab(self) -> QWidget:
        """Create the storyboard items tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header_label = QLabel("Storyboard Items for Selected Scene")
        header_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header_label)
        
        # Storyboard items list
        self.storyboard_list = QListWidget()
        self.storyboard_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # Allow multiple selection
        self.storyboard_list.itemDoubleClicked.connect(self.on_storyboard_item_double_clicked)
        
        # Enable drag and drop for reordering
        self.storyboard_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.storyboard_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.storyboard_list.setDragEnabled(True)
        self.storyboard_list.setAcceptDrops(True)
        self.storyboard_list.setDropIndicatorShown(True)
        
        # Context menu for storyboard items
        self.storyboard_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.storyboard_list.customContextMenuRequested.connect(self.on_storyboard_context_menu)
        
        layout.addWidget(self.storyboard_list)
        
        # Storyboard action buttons
        button_layout = QHBoxLayout()
        
        self.add_storyboard_item_btn = QPushButton("+ Add Item")
        self.add_storyboard_item_btn.clicked.connect(self.on_add_storyboard_item_clicked)
        self.add_storyboard_item_btn.setEnabled(False)
        button_layout.addWidget(self.add_storyboard_item_btn)
        
        self.delete_storyboard_item_btn = QPushButton("Delete Item")
        self.delete_storyboard_item_btn.clicked.connect(self.on_delete_storyboard_item_clicked)
        self.delete_storyboard_item_btn.setEnabled(False)
        button_layout.addWidget(self.delete_storyboard_item_btn)
        
        self.select_all_storyboard_btn = QPushButton("Select All")
        self.select_all_storyboard_btn.clicked.connect(self.on_select_all_storyboard_items)
        self.select_all_storyboard_btn.setEnabled(False)
        button_layout.addWidget(self.select_all_storyboard_btn)
        
        self.move_up_btn = QPushButton("↑ Move Up")
        self.move_up_btn.clicked.connect(self.on_move_storyboard_item_up)
        self.move_up_btn.setEnabled(False)
        button_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("↓ Move Down")
        self.move_down_btn.clicked.connect(self.on_move_storyboard_item_down)
        self.move_down_btn.setEnabled(False)
        button_layout.addWidget(self.move_down_btn)
        
        # Generate button
        self.generate_storyboard_btn = QPushButton("Generate Storyboard for Scene")
        self.generate_storyboard_btn.clicked.connect(self.on_generate_storyboard_clicked)
        button_layout.addWidget(self.generate_storyboard_btn)
        
        layout.addLayout(button_layout)
        
        # Multi-shot clustering toggle
        multishot_row = QHBoxLayout()
        self.multishot_toggle = QCheckBox("Enable Multi-Shot Clustering")
        self.multishot_toggle.setToolTip(
            "When enabled, consecutive storyboard items sharing the same environment, "
            "characters, and vehicles are grouped into unified multi-shot sequences.\n"
            "Requires 'Supports Multi-Shot' in Story Settings tab."
        )
        self._sync_multishot_toggle_state()
        self.multishot_toggle.toggled.connect(self._on_multishot_toggled)
        multishot_row.addWidget(self.multishot_toggle)
        multishot_row.addStretch()
        layout.addLayout(multishot_row)
        
        # Shot breakdown preview panel (read-only, shown when a clustered item is selected)
        self.cluster_preview_group = QGroupBox("Multi-Shot Cluster Preview")
        cluster_preview_layout = QVBoxLayout(self.cluster_preview_group)
        self.cluster_preview_text = QTextEdit()
        self.cluster_preview_text.setReadOnly(True)
        self.cluster_preview_text.setMaximumHeight(160)
        self.cluster_preview_text.setPlaceholderText("Select a clustered storyboard item to see the shot breakdown.")
        cluster_preview_layout.addWidget(self.cluster_preview_text)
        self.cluster_preview_group.setVisible(False)
        layout.addWidget(self.cluster_preview_group)
        
        # Connect selection change to enable/disable buttons
        self.storyboard_list.itemSelectionChanged.connect(self.on_storyboard_selection_changed)
        self.storyboard_list.itemSelectionChanged.connect(self._update_cluster_preview)
        
        # Handle drag and drop reordering by monitoring when items are moved
        self.storyboard_list.model().rowsMoved.connect(self.on_storyboard_items_reordered)
        
        return widget
    
    # Timeline tab removed
    
    def create_character_details_tab(self) -> QWidget:
        """Create the character details tab (wizard-style: list left, editor right)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Add character button above the splitter
        add_char_layout = QHBoxLayout()
        add_char_layout.addStretch()
        self.add_character_btn = QPushButton("+ Add Character")
        self.add_character_btn.clicked.connect(self.on_add_character_clicked)
        add_char_layout.addWidget(self.add_character_btn)
        layout.addLayout(add_char_layout)
        
        # Horizontal splitter: character list (left) | editor (right)
        char_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: character list
        char_list_container = QWidget()
        char_list_layout = QVBoxLayout(char_list_container)
        char_list_layout.setContentsMargins(0, 0, 0, 0)
        self.char_details_list = QListWidget()
        self.char_details_list.setMaximumWidth(220)
        self.char_details_list.currentRowChanged.connect(self.on_char_details_selected)
        char_list_layout.addWidget(self.char_details_list)
        char_splitter.addWidget(char_list_container)
        
        # Right: scrollable character editor
        # Wrap the entire editor panel in a QScrollArea for vertical scrolling
        char_scroll_area = QScrollArea()
        char_scroll_area.setWidgetResizable(True)
        char_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        char_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        char_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        self.char_details_editor = QWidget()
        char_editor_layout = QVBoxLayout(self.char_details_editor)
        char_editor_layout.setContentsMargins(10, 10, 10, 10)
        char_editor_layout.setSpacing(8)
        
        # --- Character Name ---
        char_name_label = QLabel("Character Name:")
        char_name_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.char_details_name_edit = QLineEdit()
        self.char_details_name_edit.setPlaceholderText("Enter character name...")
        self.char_details_name_edit.setMinimumHeight(32)
        self.char_details_name_edit.textChanged.connect(self.on_char_details_name_changed)
        char_editor_layout.addWidget(char_name_label)
        char_editor_layout.addWidget(self.char_details_name_edit)
        
        # --- Role Toggle + Generate Details ---
        role_row_layout = QHBoxLayout()
        role_label = QLabel("Role:")
        role_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        role_row_layout.addWidget(role_label)
        
        self.char_role_toggle = QPushButton("Main Character")
        self.char_role_toggle.setCheckable(True)
        self.char_role_toggle.setMinimumWidth(130)
        self.char_role_toggle.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:checked { background-color: #FF9800; }"
        )
        self.char_role_toggle.setToolTip("Toggle between Main Character and Minor Character")
        self.char_role_toggle.toggled.connect(self._on_char_role_toggled)
        role_row_layout.addWidget(self.char_role_toggle)
        
        role_row_layout.addSpacing(16)
        
        self.generate_char_details_btn = QPushButton("Generate Details")
        self.generate_char_details_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 4px; padding: 4px 12px;")
        self.generate_char_details_btn.setToolTip("Generate character details using AI based on the current role")
        self.generate_char_details_btn.clicked.connect(self._on_generate_char_details_clicked)
        role_row_layout.addWidget(self.generate_char_details_btn)
        
        role_row_layout.addStretch()
        char_editor_layout.addLayout(role_row_layout)
        
        # --- Species / Form ---
        species_row_layout = QHBoxLayout()
        species_label = QLabel("Species / Form:")
        species_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        species_row_layout.addWidget(species_label)
        
        self.char_species_combo = QComboBox()
        self.char_species_combo.setMinimumWidth(160)
        self._populate_species_combo()
        self.char_species_combo.currentTextChanged.connect(self._on_char_species_changed)
        species_row_layout.addWidget(self.char_species_combo)
        
        self.char_species_custom_edit = QLineEdit()
        self.char_species_custom_edit.setPlaceholderText("Enter custom species...")
        self.char_species_custom_edit.setMinimumWidth(160)
        self.char_species_custom_edit.setVisible(False)
        self.char_species_custom_edit.textChanged.connect(self._on_char_species_custom_changed)
        self.char_species_custom_edit.editingFinished.connect(self._on_char_species_custom_committed)
        species_row_layout.addWidget(self.char_species_custom_edit)
        
        species_row_layout.addStretch()
        char_editor_layout.addLayout(species_row_layout)
        
        # --- Physical Appearance ---
        self.char_physical_label = QLabel("Physical Appearance:")
        self.char_physical_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.char_details_physical_edit = QTextEdit()
        self.char_details_physical_edit.setPlaceholderText("Gender, height, face, hair, eyes, skin, age, build, scars. No character name.")
        self.char_details_physical_edit.setMinimumHeight(140)
        self.char_details_physical_edit.textChanged.connect(self.on_char_details_physical_changed)
        char_editor_layout.addWidget(self.char_physical_label)
        char_editor_layout.addWidget(self.char_details_physical_edit)
        
        self._first_scene_wardrobe_suffix = ""
        
        # --- Generated Identity Block ---
        ib_label = QLabel("Generated Identity Block:")
        ib_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        char_editor_layout.addWidget(ib_label)
        
        ib_btn_layout = QHBoxLayout()
        self.char_generate_ib_btn = QPushButton("Generate Identity Block")
        self.char_generate_ib_btn.setStyleSheet("background-color: #2196F3; color: white;")
        self.char_generate_ib_btn.setToolTip("Physical Appearance must be defined first.")
        self.char_generate_ib_btn.setEnabled(False)
        self.char_generate_ib_btn.clicked.connect(self._on_generate_char_identity_block)
        ib_btn_layout.addWidget(self.char_generate_ib_btn)
        ib_btn_layout.addStretch()
        char_editor_layout.addLayout(ib_btn_layout)
        
        self.char_identity_block_edit = QTextEdit()
        self.char_identity_block_edit.setPlaceholderText(
            "Click 'Generate Identity Block' to expand the physical appearance and wardrobe "
            "into a detailed identity block. Editable after generation."
        )
        self.char_identity_block_edit.setMinimumHeight(120)
        self.char_identity_block_edit.textChanged.connect(self._on_char_identity_block_changed)
        char_editor_layout.addWidget(self.char_identity_block_edit)
        
        # --- Reference Image Prompt (approved from identity block) ---
        rip_label = QLabel("Reference Image Prompt:")
        rip_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        char_editor_layout.addWidget(rip_label)
        
        rip_btn_layout = QHBoxLayout()
        self.char_approve_ib_btn = QPushButton("Approve")
        self.char_approve_ib_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.char_approve_ib_btn.setToolTip("Approve the identity block and generate the reference image prompt.")
        self.char_approve_ib_btn.setEnabled(False)
        self.char_approve_ib_btn.clicked.connect(self._on_approve_char_identity_block)
        rip_btn_layout.addWidget(self.char_approve_ib_btn)
        
        self.char_copy_rip_btn = QPushButton("Copy to Clipboard")
        self.char_copy_rip_btn.setEnabled(False)
        self.char_copy_rip_btn.clicked.connect(self._on_copy_char_ref_prompt)
        rip_btn_layout.addWidget(self.char_copy_rip_btn)
        rip_btn_layout.addStretch()
        char_editor_layout.addLayout(rip_btn_layout)
        
        self.char_ref_prompt_edit = QTextEdit()
        self.char_ref_prompt_edit.setPlaceholderText(
            "Approve the identity block above to generate the reference image prompt."
        )
        self.char_ref_prompt_edit.setMinimumHeight(100)
        self.char_ref_prompt_edit.setReadOnly(True)
        char_editor_layout.addWidget(self.char_ref_prompt_edit)

        # --- Reference Image Thumbnail ---
        ref_img_label = QLabel("Reference Image:")
        ref_img_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        char_editor_layout.addWidget(ref_img_label)

        char_ref_img_row = QHBoxLayout()
        self.char_ref_thumb = ClickableImageLabel(max_short=120, max_long=160)
        char_ref_img_row.addWidget(self.char_ref_thumb)

        char_ref_btn_col = QVBoxLayout()
        self.char_upload_ref_btn = QPushButton("Upload Image")
        self.char_upload_ref_btn.setFixedWidth(120)
        self.char_upload_ref_btn.clicked.connect(self._on_upload_char_ref_image)
        char_ref_btn_col.addWidget(self.char_upload_ref_btn)

        self.char_clear_ref_btn = QPushButton("Clear")
        self.char_clear_ref_btn.setFixedWidth(120)
        self.char_clear_ref_btn.clicked.connect(self._on_clear_char_ref_image)
        char_ref_btn_col.addWidget(self.char_clear_ref_btn)
        char_ref_btn_col.addStretch()
        char_ref_img_row.addLayout(char_ref_btn_col)
        char_ref_img_row.addStretch()
        char_editor_layout.addLayout(char_ref_img_row)

        char_editor_layout.addSpacing(8)

        # --- Wardrobe Variants Section ---
        wardrobe_variants_label = QLabel("Wardrobe Variants:")
        wardrobe_variants_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        char_editor_layout.addWidget(wardrobe_variants_label)

        self.wardrobe_variants_container = QVBoxLayout()
        char_editor_layout.addLayout(self.wardrobe_variants_container)
        self._wardrobe_variant_widgets: List[Dict] = []

        add_variant_btn = QPushButton("+ Add Wardrobe Variant")
        add_variant_btn.setFixedWidth(200)
        add_variant_btn.clicked.connect(self._on_add_wardrobe_variant)
        char_editor_layout.addWidget(add_variant_btn)

        char_editor_layout.addSpacing(8)
        
        # --- Character Outline ---
        self.char_outline_label = QLabel("Character Outline:")
        self.char_outline_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.char_details_outline_edit = QTextEdit()
        self.char_details_outline_edit.setPlaceholderText("Character description, role, background, motivation...")
        self.char_details_outline_edit.setMinimumHeight(180)
        self.char_details_outline_edit.textChanged.connect(self.on_char_details_outline_changed)
        char_editor_layout.addWidget(self.char_outline_label)
        char_editor_layout.addWidget(self.char_details_outline_edit)
        
        # --- Character Growth Arc ---
        self.char_growth_label = QLabel("Character Growth Arc:")
        self.char_growth_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.char_details_growth_edit = QTextEdit()
        self.char_details_growth_edit.setPlaceholderText("Character development: starting point, challenges, changes, ending...")
        self.char_details_growth_edit.setMinimumHeight(180)
        self.char_details_growth_edit.textChanged.connect(self.on_char_details_growth_changed)
        char_editor_layout.addWidget(self.char_growth_label)
        char_editor_layout.addWidget(self.char_details_growth_edit)
        
        # --- Delete button ---
        char_editor_layout.addSpacing(12)
        delete_char_btn = QPushButton("Delete Character")
        delete_char_btn.setStyleSheet("background-color: #cc4444; color: white;")
        delete_char_btn.clicked.connect(self.on_delete_char_detail_clicked)
        char_editor_layout.addWidget(delete_char_btn)
        
        char_editor_layout.addSpacing(20)
        
        # Set the editor widget inside the scroll area
        char_scroll_area.setWidget(self.char_details_editor)
        char_splitter.addWidget(char_scroll_area)
        char_splitter.setSizes([220, 500])
        
        layout.addWidget(char_splitter)
        
        enable_spell_checking(self.char_details_outline_edit)
        enable_spell_checking(self.char_details_growth_edit)
        enable_spell_checking(self.char_details_physical_edit)
        self.char_details_outline_edit.setTabChangesFocus(True)
        self.char_details_growth_edit.setTabChangesFocus(True)
        self.char_details_physical_edit.setTabChangesFocus(True)
        self.char_identity_block_edit.setTabChangesFocus(True)
        self.char_ref_prompt_edit.setTabChangesFocus(True)
        
        # Block saving while we load selection (set in update_character_details / on_char_details_selected)
        self._loading_char_selection = False
        # Track last selected row so we save editor content to the correct character when selection changes
        self._char_details_last_row = -1
        
        return widget

    def create_premise_tab(self) -> QWidget:
        """Create the premise summary tab."""
        # Create scroll area to contain all content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Metadata section (editable)
        metadata_group = QGroupBox("Story Metadata (for reference)")
        metadata_layout = QVBoxLayout(metadata_group)
        
        # Title field
        title_layout = QHBoxLayout()
        title_label = QLabel("Title:")
        title_label.setMinimumWidth(120)
        title_layout.addWidget(title_label)
        self.premise_title_edit = QLineEdit()
        self.premise_title_edit.setPlaceholderText("Enter story title...")
        self.premise_title_edit.setMinimumHeight(30)
        title_layout.addWidget(self.premise_title_edit)
        metadata_layout.addLayout(title_layout)
        
        # Genres field (narrative-only; hidden for promotional)
        self.premise_genres_row = QWidget()
        genres_layout = QHBoxLayout(self.premise_genres_row)
        genres_layout.setContentsMargins(0, 0, 0, 0)
        genres_label = QLabel("Genres:")
        genres_label.setMinimumWidth(120)
        genres_layout.addWidget(genres_label)
        self.premise_genres_edit = QTextEdit()
        self.premise_genres_edit.setPlaceholderText("Enter genres separated by commas (e.g., Action, Drama, Thriller)...")
        self.premise_genres_edit.setMaximumHeight(60)
        self.premise_genres_edit.setMinimumHeight(50)
        self.premise_genres_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.premise_genres_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.premise_genres_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        genres_layout.addWidget(self.premise_genres_edit)
        metadata_layout.addWidget(self.premise_genres_row)
        
        # Atmosphere field (label changes to "Brand Tone" for promotional)
        atmosphere_layout = QHBoxLayout()
        self.premise_atmosphere_label = QLabel("Atmosphere/Tone:")
        self.premise_atmosphere_label.setMinimumWidth(120)
        atmosphere_layout.addWidget(self.premise_atmosphere_label)
        self.premise_atmosphere_edit = QTextEdit()
        self.premise_atmosphere_edit.setPlaceholderText("Enter atmosphere/tone (e.g., Suspenseful, Dark, Lighthearted)...")
        self.premise_atmosphere_edit.setMaximumHeight(60)
        self.premise_atmosphere_edit.setMinimumHeight(50)
        self.premise_atmosphere_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.premise_atmosphere_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.premise_atmosphere_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        atmosphere_layout.addWidget(self.premise_atmosphere_edit)
        metadata_layout.addLayout(atmosphere_layout)
        
        # Audio strategy (project-level)
        audio_strategy_layout = QHBoxLayout()
        audio_strategy_layout.addWidget(QLabel("Audio strategy:"))
        self.premise_audio_strategy_combo = QComboBox()
        self.premise_audio_strategy_combo.addItem("Generated with video", "generated_with_video")
        self.premise_audio_strategy_combo.addItem("Added in post", "added_in_post")
        self.premise_audio_strategy_combo.addItem("No audio", "no_audio")
        self.premise_audio_strategy_combo.setToolTip(
            "Generated with video: audio fields suggested but optional.\n"
            "Added in post: audio fields are sound-design notes only.\n"
            "No audio: audio fields hidden; silence is valid."
        )
        audio_strategy_layout.addWidget(self.premise_audio_strategy_combo)
        audio_strategy_layout.addStretch()
        metadata_layout.addLayout(audio_strategy_layout)
        
        layout.addWidget(metadata_group)
        
        # Promotional section (Brand/Product context; shown only for promotional profile)
        self.premise_promotional_group = QGroupBox("Brand / Product Context")
        promo_layout = QFormLayout(self.premise_promotional_group)
        self.premise_brand_name_edit = QTextEdit()
        self.premise_brand_name_edit.setMaximumHeight(30)
        self.premise_brand_name_edit.setPlaceholderText("e.g., Acme Corp")
        promo_layout.addRow("Brand / Product Name:", self.premise_brand_name_edit)
        self.premise_product_description_edit = QTextEdit()
        self.premise_product_description_edit.setMinimumHeight(60)
        self.premise_product_description_edit.setMaximumHeight(100)
        self.premise_product_description_edit.setPlaceholderText("Describe the product in 1-2 sentences.")
        promo_layout.addRow("Product Description:", self.premise_product_description_edit)
        self.premise_core_benefit_edit = QTextEdit()
        self.premise_core_benefit_edit.setMinimumHeight(60)
        self.premise_core_benefit_edit.setMaximumHeight(100)
        self.premise_core_benefit_edit.setPlaceholderText("Core benefit or promise.")
        promo_layout.addRow("Core Benefit:", self.premise_core_benefit_edit)
        self.premise_target_audience_edit = QTextEdit()
        self.premise_target_audience_edit.setMinimumHeight(50)
        self.premise_target_audience_edit.setMaximumHeight(60)
        self.premise_target_audience_edit.setPlaceholderText("e.g., Young professionals, Parents")
        promo_layout.addRow("Target Audience:", self.premise_target_audience_edit)
        self.premise_brand_personality_edit = QTextEdit()
        self.premise_brand_personality_edit.setMinimumHeight(50)
        self.premise_brand_personality_edit.setMaximumHeight(60)
        self.premise_brand_personality_edit.setPlaceholderText("e.g., Innovative, Trustworthy (comma-separated)")
        promo_layout.addRow("Brand Personality:", self.premise_brand_personality_edit)
        self.premise_mandatory_inclusions_edit = QTextEdit()
        self.premise_mandatory_inclusions_edit.setMinimumHeight(50)
        self.premise_mandatory_inclusions_edit.setMaximumHeight(60)
        self.premise_mandatory_inclusions_edit.setPlaceholderText("e.g., logo reveal, product shot (comma-separated)")
        promo_layout.addRow("Mandatory Inclusions:", self.premise_mandatory_inclusions_edit)
        self.premise_promotional_group.setVisible(False)
        layout.addWidget(self.premise_promotional_group)
        
        # Expanded Storyline section (main story arc from outline; was "Original Premise")
        header = QLabel("Expanded Storyline")
        header.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(header)
        
        self.premise_text = QTextEdit()
        self.premise_text.setReadOnly(False)  # Make editable
        self.premise_text.setPlaceholderText("Enter or edit the expanded storyline (main story arc)...")
        self.premise_text.setMinimumHeight(200)
        self.premise_text.setMaximumHeight(300)
        self.premise_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.premise_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.premise_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.premise_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.premise_text)
        
        # Subplots section (narrative-only; hidden for promotional)
        self.premise_subplots_header = QLabel("Subplots and Secondary Storylines")
        self.premise_subplots_header.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(self.premise_subplots_header)
        
        self.subplots_text = QTextEdit()
        self.subplots_text.setReadOnly(False)  # Make editable
        self.subplots_text.setPlaceholderText("Enter or edit subplots and secondary storylines...")
        self.subplots_text.setMinimumHeight(150)
        self.subplots_text.setMaximumHeight(250)
        self.subplots_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.subplots_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.subplots_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.subplots_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.subplots_text)
        
        # Final Conclusion section (narrative-only; hidden for promotional)
        self.premise_conclusion_header = QLabel("Final Conclusion")
        self.premise_conclusion_header.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(self.premise_conclusion_header)
        
        self.conclusion_text = QTextEdit()
        self.conclusion_text.setReadOnly(False)  # Make editable
        self.conclusion_text.setPlaceholderText("Enter or edit the final conclusion...")
        self.conclusion_text.setMinimumHeight(150)
        self.conclusion_text.setMaximumHeight(250)
        self.conclusion_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.conclusion_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.conclusion_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.conclusion_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.conclusion_text)
        
        # Save button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.save_premise_btn = QPushButton("Save Changes")
        self.save_premise_btn.clicked.connect(self.on_save_premise_changes)
        self.save_premise_btn.setToolTip("Save all premise changes to the screenplay")
        button_layout.addWidget(self.save_premise_btn)
        layout.addLayout(button_layout)
        
        # Tab key moves focus (not indentation) in form-style fields
        for w in (self.premise_genres_edit, self.premise_atmosphere_edit, self.premise_text,
                  self.subplots_text, self.conclusion_text,
                  self.premise_brand_name_edit, self.premise_product_description_edit,
                  self.premise_core_benefit_edit, self.premise_target_audience_edit,
                  self.premise_brand_personality_edit, self.premise_mandatory_inclusions_edit):
            w.setTabChangesFocus(True)
        
        # Set the widget in the scroll area
        scroll_area.setWidget(widget)
        
        # Return the scroll area as the tab content
        return scroll_area
    
    def create_identity_blocks_tab(self) -> QWidget:
        """Create the identity blocks management tab."""
        self.identity_block_manager = IdentityBlockManager()
        
        # Connect signals
        self.identity_block_manager.identity_blocks_changed.connect(self.on_identity_blocks_changed)
        
        return self.identity_block_manager
    
    def create_right_panel(self, parent):
        """Create the right panel with scene details."""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # Plot point
        plot_group = QGroupBox("Plot Point")
        plot_layout = QVBoxLayout()
        self.plot_point_label = QLabel("None")
        plot_layout.addWidget(self.plot_point_label)
        plot_group.setLayout(plot_layout)
        right_layout.addWidget(plot_group)
        
        # Character focus
        char_group = QGroupBox("Character Focus")
        char_layout = QVBoxLayout()
        self.character_list = QListWidget()
        self.character_list.setMaximumHeight(100)
        char_layout.addWidget(self.character_list)
        char_group.setLayout(char_layout)
        right_layout.addWidget(char_group)
        
        # Pacing
        pacing_group = QGroupBox("Pacing")
        pacing_layout = QVBoxLayout()
        self.pacing_label = QLabel("Medium")
        pacing_layout.addWidget(self.pacing_label)
        pacing_group.setLayout(pacing_layout)
        right_layout.addWidget(pacing_group)
        
        # Estimated duration
        duration_group = QGroupBox("Estimated Duration")
        duration_layout = QVBoxLayout()
        duration_input_layout = QHBoxLayout()
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(5)
        self.duration_spinbox.setMaximum(600)  # Max 10 minutes
        self.duration_spinbox.setSingleStep(5)  # Increment by 5 seconds
        self.duration_spinbox.setSuffix(" seconds")
        self.duration_spinbox.setValue(0)
        duration_input_layout.addWidget(self.duration_spinbox)
        duration_input_layout.addStretch()
        duration_layout.addLayout(duration_input_layout)
        duration_group.setLayout(duration_layout)
        right_layout.addWidget(duration_group)
        
        # Compression strategy
        compression_group = QGroupBox("Compression Strategy")
        compression_layout = QVBoxLayout()
        self.compression_strategy_label = QLabel("Beat-by-Beat")
        self.compression_strategy_label.setToolTip(
            "Montage: Fewer, richer prompts (fast-paced scenes)\n"
            "Beat-by-Beat: Many micro-actions (detailed sequences)\n"
            "Atmospheric Hold: Single extended shot (mood scenes)"
        )
        compression_layout.addWidget(self.compression_strategy_label)
        compression_group.setLayout(compression_layout)
        right_layout.addWidget(compression_group)
        
        # Advertisement mode info group
        ad_info_group = QGroupBox("Advertisement Beat")
        ad_info_layout = QFormLayout()
        self.ad_beat_type_header = QLabel("Beat Type:")
        self.ad_beat_type_label = QLabel("")
        self.ad_beat_type_label.setWordWrap(True)
        ad_info_layout.addRow(self.ad_beat_type_header, self.ad_beat_type_label)
        self.ad_flags_header = QLabel("Flags:")
        self.ad_flags_label = QLabel("None")
        ad_info_layout.addRow(self.ad_flags_header, self.ad_flags_label)
        ad_info_group.setLayout(ad_info_layout)
        ad_info_group.setVisible(False)
        self.ad_info_group = ad_info_group
        right_layout.addWidget(ad_info_group)
        
        right_layout.addStretch()
        
        parent.addWidget(right_widget)
    
    def set_screenplay(self, screenplay: Screenplay):
        """Set the screenplay to display."""
        try:
            self.screenplay = screenplay
            self.update_tree()
            # Timeline visualization removed
            self.update_character_details()
            self.update_premise_tab()
            # Update identity blocks manager
            if hasattr(self, 'identity_block_manager'):
                self.identity_block_manager.set_screenplay(screenplay)
            # Update story settings tab
            if hasattr(self, 'story_settings_tab'):
                self.story_settings_tab.load_settings(screenplay)
            # Adapt UI for Visual Art mode
            self._update_visual_art_visibility()
        except Exception as e:
            # Silently handle errors during initialization
            try:
                log_exception("Error in set_screenplay", e)
            except:
                import traceback
                print(f"Error updating framework view: {e}")
                traceback.print_exc()

    def update_premise_tab_for_profile(self):
        """Show/hide premise tab sections and relabel fields based on workflow profile."""
        if not hasattr(self, "premise_promotional_group"):
            return
        if not self.screenplay:
            self.premise_promotional_group.setVisible(False)
            if hasattr(self, "premise_genres_row"):
                self.premise_genres_row.setVisible(True)
            if hasattr(self, "premise_subplots_header"):
                self.premise_subplots_header.setVisible(True)
                self.subplots_text.setVisible(True)
            if hasattr(self, "premise_conclusion_header"):
                self.premise_conclusion_header.setVisible(True)
                self.conclusion_text.setVisible(True)
            if hasattr(self, "premise_atmosphere_label"):
                self.premise_atmosphere_label.setText("Atmosphere/Tone:")
            return
        length = getattr(self.screenplay, "story_length", "medium") or "medium"
        intent = getattr(self.screenplay, "intent", "General Story") or "General Story"
        profile = WorkflowProfileManager.get_profile(length, intent)
        ui_config = WorkflowProfileManager.get_premise_ui_config(profile, intent)
        if profile == WorkflowProfile.PROMOTIONAL:
            self.premise_promotional_group.setVisible(True)
            if hasattr(self, "premise_genres_row"):
                self.premise_genres_row.setVisible(False)
            if hasattr(self, "premise_subplots_header"):
                self.premise_subplots_header.setVisible(False)
                self.subplots_text.setVisible(False)
            if hasattr(self, "premise_conclusion_header"):
                self.premise_conclusion_header.setVisible(False)
                self.conclusion_text.setVisible(False)
            if hasattr(self, "premise_atmosphere_label"):
                self.premise_atmosphere_label.setText(f"{ui_config['atmosphere_label']}:")
        else:
            self.premise_promotional_group.setVisible(False)
            if hasattr(self, "premise_genres_row"):
                self.premise_genres_row.setVisible(True)
            if hasattr(self, "premise_subplots_header"):
                self.premise_subplots_header.setVisible(True)
                self.subplots_text.setVisible(True)
            if hasattr(self, "premise_conclusion_header"):
                self.premise_conclusion_header.setVisible(True)
                self.conclusion_text.setVisible(True)
            if hasattr(self, "premise_atmosphere_label"):
                self.premise_atmosphere_label.setText(f"{ui_config['atmosphere_label']}:")

    def update_premise_tab(self):
        """Update the premise tab with current screenplay data."""
        if not hasattr(self, "premise_text"):
            return
        
        if not self.screenplay:
            # Clear all fields
            if hasattr(self, "premise_title_edit"):
                self.premise_title_edit.setText("")
            if hasattr(self, "premise_genres_edit"):
                self.premise_genres_edit.setPlainText("")
            if hasattr(self, "premise_atmosphere_edit"):
                self.premise_atmosphere_edit.setPlainText("")
            if hasattr(self, "premise_audio_strategy_combo"):
                idx = self.premise_audio_strategy_combo.findData("generated_with_video")
                if idx >= 0:
                    self.premise_audio_strategy_combo.setCurrentIndex(idx)
            self.premise_text.setPlainText("")
            if hasattr(self, "subplots_text"):
                self.subplots_text.setPlainText("")
            if hasattr(self, "conclusion_text"):
                self.conclusion_text.setPlainText("")
            if hasattr(self, "premise_promotional_group"):
                for w in (self.premise_brand_name_edit, self.premise_product_description_edit,
                          self.premise_core_benefit_edit, self.premise_target_audience_edit,
                          self.premise_brand_personality_edit, self.premise_mandatory_inclusions_edit):
                    w.setPlainText("")
            self.update_premise_tab_for_profile()
            return
        
        # Get values from screenplay
        title = getattr(self.screenplay, "title", "") or ""
        genres = getattr(self.screenplay, "genre", []) or []
        atmosphere = getattr(self.screenplay, "atmosphere", "") or ""
        
        # Get expanded storyline (main_storyline) and subplots/conclusion from story_outline
        story_outline = getattr(self.screenplay, "story_outline", {}) or {}
        main_storyline = story_outline.get("main_storyline", "") or ""
        subplots = story_outline.get("subplots", "") or ""
        conclusion = story_outline.get("conclusion", "") or ""
        # Fallback to short premise if no expanded storyline yet (e.g. before outline step)
        if not main_storyline:
            main_storyline = getattr(self.screenplay, "premise", "") or ""
        
        # Update editable fields
        if hasattr(self, "premise_title_edit"):
            self.premise_title_edit.setText(title)
        if hasattr(self, "premise_genres_edit"):
            genre_text = ", ".join(genres) if isinstance(genres, list) and genres else ""
            self.premise_genres_edit.setPlainText(genre_text)
        if hasattr(self, "premise_atmosphere_edit"):
            self.premise_atmosphere_edit.setPlainText(atmosphere)
        if hasattr(self, "premise_audio_strategy_combo"):
            audio_strategy = getattr(self.screenplay, "audio_strategy", "generated_with_video") or "generated_with_video"
            idx = self.premise_audio_strategy_combo.findData(audio_strategy)
            if idx >= 0:
                self.premise_audio_strategy_combo.setCurrentIndex(idx)
        
        self.premise_text.setPlainText(main_storyline)
        
        # Update subplots and conclusion if the widgets exist
        if hasattr(self, "subplots_text"):
            self.subplots_text.setPlainText(subplots)
        if hasattr(self, "conclusion_text"):
            self.conclusion_text.setPlainText(conclusion)
        
        # Populate promotional fields from brand_context
        bc = getattr(self.screenplay, "brand_context", None)
        if bc and hasattr(self, "premise_brand_name_edit"):
            self.premise_brand_name_edit.setPlainText(bc.brand_name or "")
            self.premise_product_description_edit.setPlainText(bc.product_description or "")
            self.premise_core_benefit_edit.setPlainText(bc.core_benefit or "")
            self.premise_target_audience_edit.setPlainText(bc.target_audience or "")
            self.premise_brand_personality_edit.setPlainText(", ".join(bc.brand_personality) if bc.brand_personality else "")
            self.premise_mandatory_inclusions_edit.setPlainText(", ".join(bc.mandatory_elements) if bc.mandatory_elements else "")
        
        self.update_premise_tab_for_profile()
    
    def on_save_premise_changes(self):
        """Save all premise tab changes back to the screenplay."""
        if not self.screenplay:
            QMessageBox.warning(self, "No Screenplay", "No screenplay is currently loaded.")
            return
        
        try:
            # Update title
            if hasattr(self, "premise_title_edit"):
                self.screenplay.title = self.premise_title_edit.text().strip()
            
            # Update genres
            if hasattr(self, "premise_genres_edit"):
                genre_text = self.premise_genres_edit.toPlainText().strip()
                if genre_text:
                    # Split by comma and clean up
                    genres = [g.strip() for g in genre_text.split(",") if g.strip()]
                    self.screenplay.genre = genres
                else:
                    self.screenplay.genre = []
            
            # Update atmosphere
            if hasattr(self, "premise_atmosphere_edit"):
                self.screenplay.atmosphere = self.premise_atmosphere_edit.toPlainText().strip()
            if hasattr(self, "premise_audio_strategy_combo"):
                val = self.premise_audio_strategy_combo.currentData()
                if val in ("generated_with_video", "added_in_post", "no_audio"):
                    self.screenplay.audio_strategy = val
            
            # Ensure story_outline exists
            if not hasattr(self.screenplay, "story_outline") or self.screenplay.story_outline is None:
                self.screenplay.story_outline = {}
            
            # Update expanded storyline (main_storyline) from premise tab; keep short premise unchanged unless empty
            expanded = self.premise_text.toPlainText().strip()
            self.screenplay.story_outline["main_storyline"] = expanded
            if not getattr(self.screenplay, "premise", "").strip() and expanded:
                self.screenplay.premise = expanded[:500].strip()  # keep a short premise for backwards compatibility
            
            if hasattr(self, "subplots_text"):
                self.screenplay.story_outline["subplots"] = self.subplots_text.toPlainText().strip()
            
            if hasattr(self, "conclusion_text"):
                self.screenplay.story_outline["conclusion"] = self.conclusion_text.toPlainText().strip()
            
            # Save promotional fields when profile is promotional
            length = getattr(self.screenplay, "story_length", "medium") or "medium"
            intent = getattr(self.screenplay, "intent", "General Story") or "General Story"
            profile = WorkflowProfileManager.get_profile(length, intent)
            if profile == WorkflowProfile.PROMOTIONAL and hasattr(self, "premise_brand_name_edit"):
                personality_text = self.premise_brand_personality_edit.toPlainText().strip()
                brand_personality = [p.strip() for p in personality_text.split(",") if p.strip()] if personality_text else []
                mandatory_text = self.premise_mandatory_inclusions_edit.toPlainText().strip()
                mandatory_elements = [e.strip() for e in mandatory_text.split(",") if e.strip()] if mandatory_text else []
                if self.screenplay.brand_context is None:
                    self.screenplay.brand_context = BrandContext(
                        brand_name=self.premise_brand_name_edit.toPlainText().strip(),
                        product_name="",
                        product_description=self.premise_product_description_edit.toPlainText().strip(),
                        core_benefit=self.premise_core_benefit_edit.toPlainText().strip(),
                        target_audience=self.premise_target_audience_edit.toPlainText().strip(),
                        brand_personality=brand_personality,
                        mandatory_elements=mandatory_elements
                    )
                else:
                    self.screenplay.brand_context.brand_name = self.premise_brand_name_edit.toPlainText().strip()
                    self.screenplay.brand_context.product_description = self.premise_product_description_edit.toPlainText().strip()
                    self.screenplay.brand_context.core_benefit = self.premise_core_benefit_edit.toPlainText().strip()
                    self.screenplay.brand_context.target_audience = self.premise_target_audience_edit.toPlainText().strip()
                    self.screenplay.brand_context.brand_personality = brand_personality
                    self.screenplay.brand_context.mandatory_elements = mandatory_elements
            
            # Update timestamp
            from datetime import datetime
            if hasattr(self.screenplay, "updated_at"):
                self.screenplay.updated_at = datetime.now().isoformat()
            
            self._show_status("Premise changes saved")
            
            # Refresh the tree to show updated title if it changed
            self.update_tree()
            
        except Exception as e:
            try:
                log_exception("Error saving premise changes", e)
            except:
                pass
            QMessageBox.critical(self, "Save Error", 
                f"An error occurred while saving premise changes:\n{str(e)}")
    
    def set_ai_generator(self, ai_generator: Optional[AIGenerator]):
        """Set the AI generator."""
        self.ai_generator = ai_generator
        # Update identity blocks manager
        if hasattr(self, 'identity_block_manager'):
            self.identity_block_manager.set_ai_generator(ai_generator)
        self._update_identity_block_buttons()
    
    def update_tree(self):
        """Update the act/scene tree."""
        try:
            self.tree.clear()
            
            if not self.screenplay or not self.screenplay.acts:
                return
            
            # Create root item
            root = QTreeWidgetItem(self.tree)
            title = getattr(self.screenplay, 'title', 'Untitled Story') or 'Untitled Story'
            root.setText(0, f"📖 {title}")
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            
            # Add acts and scenes
            acts = getattr(self.screenplay, 'acts', []) or []
            for act in sorted(acts, key=lambda x: getattr(x, 'act_number', 0)):
                try:
                    act_number = getattr(act, 'act_number', 0)
                    act_title = getattr(act, 'title', f'Act {act_number}') or f'Act {act_number}'
                    act_item = QTreeWidgetItem(root)
                    act_item.setText(0, f"Act {act_number}: {act_title}")
                    act_item.setData(0, Qt.ItemDataRole.UserRole, ("act", act))
                    
                    # Add scenes
                    scenes = getattr(act, 'scenes', []) or []
                    for scene in sorted(scenes, key=lambda x: getattr(x, 'scene_number', 0)):
                        try:
                            # Get scene attributes safely
                            title = getattr(scene, 'title', 'Untitled Scene') or 'Untitled Scene'
                            is_complete = getattr(scene, 'is_complete', False)
                            plot_point = getattr(scene, 'plot_point', None)
                            pacing = getattr(scene, 'pacing', 'Medium') or 'Medium'
                            scene_number = getattr(scene, 'scene_number', 1)
                            
                            scene_item = QTreeWidgetItem(act_item)
                            # Completion indicator (complete / partial / not started)
                            generated_content = ""
                            try:
                                metadata = getattr(scene, 'metadata', {}) or {}
                                if isinstance(metadata, dict):
                                    generated_content = (metadata.get("generated_content", "") or "").strip()
                            except Exception:
                                generated_content = ""
                            has_storyboard_items = bool(getattr(scene, 'storyboard_items', []) or [])
                            
                            # Identity placeholder heuristic: environment_id or any per-scene environment metadata exists
                            has_identity_placeholders = bool(getattr(scene, 'environment_id', "") or "")
                            try:
                                if self.screenplay and getattr(self.screenplay, "identity_block_metadata", None):
                                    for _, meta in self.screenplay.identity_block_metadata.items():
                                        if meta.get("scene_id") == getattr(scene, "scene_id", ""):
                                            has_identity_placeholders = True
                                            break
                            except Exception:
                                pass
                            
                            is_complete_state = bool(generated_content) and has_storyboard_items
                            is_partial_state = (bool(generated_content) or has_storyboard_items or has_identity_placeholders) and not is_complete_state
                            
                            if is_complete_state:
                                completion_icon = "✓"
                            elif is_partial_state:
                                completion_icon = "⏳"
                            else:
                                completion_icon = "○"
                            plot_point_indicator = f" [{plot_point}]" if plot_point else ""
                            pacing_indicator = f" ({pacing})" if pacing else ""
                            # Show ad beat type label in advertisement mode
                            ad_beat_label = ""
                            ad_beat_type = getattr(scene, "ad_beat_type", "") or ""
                            if ad_beat_type and self.screenplay and self.screenplay.is_advertisement_mode():
                                from core.ad_framework import AD_BEAT_LABELS
                                ad_beat_label = f" [{AD_BEAT_LABELS.get(ad_beat_type, ad_beat_type)}]"
                            scene_item.setText(0, f"{completion_icon} Scene {scene_number}: {title}{ad_beat_label or plot_point_indicator}{pacing_indicator}")
                            scene_item.setData(0, Qt.ItemDataRole.UserRole, ("scene", scene))
                            
                            # Color code by pacing and plot points
                            if plot_point:
                                # Plot points get special color
                                if plot_point in ["Inciting Incident", "First Plot Point"]:
                                    scene_item.setForeground(0, QColor("#ff6f00"))  # Orange
                                elif plot_point == "Midpoint":
                                    scene_item.setForeground(0, QColor("#f57c00"))  # Dark orange
                                elif plot_point == "Climax":
                                    scene_item.setForeground(0, QColor("#d32f2f"))  # Red
                                elif plot_point == "Resolution":
                                    scene_item.setForeground(0, QColor("#388e3c"))  # Green
                            elif pacing == "Fast":
                                scene_item.setForeground(0, QColor("#d32f2f"))  # Red
                            elif pacing == "Slow":
                                scene_item.setForeground(0, QColor("#1976d2"))  # Blue
                            else:
                                scene_item.setForeground(0, QColor("#666666"))  # Gray for medium
                        except Exception as e:
                            try:
                                log_exception(f"Error adding scene to tree", e)
                            except:
                                pass
                            continue
                except Exception as e:
                    try:
                        log_exception(f"Error adding act to tree", e)
                    except:
                        pass
                    continue
        except Exception as e:
            try:
                log_exception("Error updating tree", e)
            except:
                pass
        
        self.tree.expandAll()
        
        # Keep the current scene highlighted after refresh
        try:
            if self.current_scene:
                self._reselect_current_scene_in_tree()
        except Exception:
            pass
    
    def on_tree_selection_changed(self):
        """Handle tree selection change."""
        current_item = self.tree.currentItem()
        if not current_item:
            self.add_scene_btn.setEnabled(False)
            return
        
        data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            # Root item selected - can add act
            self.add_scene_btn.setEnabled(False)
            return
        
        item_type, item = data
        if item_type == "scene":
            self.current_scene = item
            self.load_scene_data(item)
            self.scene_selected.emit(item)
            # Notify identity block manager of new scene context
            if hasattr(self, 'identity_block_manager'):
                self.identity_block_manager.set_current_scene(item)
            if hasattr(self, 'save_scene_btn'):
                self.save_scene_btn.setEnabled(True)
            if hasattr(self, 'reextract_entities_btn'):
                self.reextract_entities_btn.setEnabled(not self._is_visual_art_mode())
            if hasattr(self, 'generate_storyboard_btn'):
                self.generate_storyboard_btn.setEnabled(True)
            # Can add scene to parent act
            parent_item = current_item.parent()
            if parent_item:
                self.add_scene_btn.setEnabled(True)
            else:
                self.add_scene_btn.setEnabled(False)
        else:
            # Act selected - can add scene
            self.current_scene = None
            self.clear_scene_data()
            # Notify identity block manager that no scene is active
            if hasattr(self, 'identity_block_manager'):
                self.identity_block_manager.set_current_scene(None)
            if hasattr(self, 'save_scene_btn'):
                self.save_scene_btn.setEnabled(False)
            if hasattr(self, 'reextract_entities_btn'):
                self.reextract_entities_btn.setEnabled(False)
            if hasattr(self, 'generate_storyboard_btn'):
                self.generate_storyboard_btn.setEnabled(False)
            self.add_scene_btn.setEnabled(True)

    def _on_tab_changed(self, index: int):
        """Ensure the currently selected scene stays highlighted across tabs."""
        try:
            # Re-select the current scene in the tree so highlight persists
            if self.current_scene:
                self._reselect_current_scene_in_tree()
        except Exception:
            # Never let tab switching crash the UI
            pass

    def _reselect_current_scene_in_tree(self):
        """Re-select current scene in the story structure tree (visual persistence)."""
        if not self.current_scene or not hasattr(self, "tree") or not self.tree:
            return
        
        scene_id = getattr(self.current_scene, "scene_id", None)
        if not scene_id:
            return
        
        # Avoid triggering selection-change side effects while we reselect
        was_blocked = self.tree.signalsBlocked()
        if not was_blocked:
            self.tree.blockSignals(True)
        
        try:
            for i in range(self.tree.topLevelItemCount()):
                act_item = self.tree.topLevelItem(i)
                if not act_item:
                    continue
                for j in range(act_item.childCount()):
                    child = act_item.child(j)
                    if not child:
                        continue
                    data = child.data(0, Qt.ItemDataRole.UserRole)
                    if not data:
                        continue
                    item_type, obj = data
                    if item_type == "scene" and getattr(obj, "scene_id", None) == scene_id:
                        # Ensure act expanded and scene selected
                        act_item.setExpanded(True)
                        self.tree.setCurrentItem(child)
                        child.setSelected(True)
                        self.tree.scrollToItem(child)
                        return
        finally:
            if not was_blocked:
                self.tree.blockSignals(False)
    
    def on_tree_item_double_clicked(self, item, column):
        """Handle tree item double click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_type, item_obj = data
        if item_type == "scene":
            self.scene_edit_requested.emit(item_obj)
    
    def load_scene_data(self, scene: StoryScene):
        """Load scene data into the framework editor."""
        if not scene:
            return
        
        try:
            # Get scene attributes safely - don't modify the scene object
            title = getattr(scene, 'title', 'Untitled Scene') or 'Untitled Scene'
            description = getattr(scene, 'description', '') or ''
            metadata = getattr(scene, 'metadata', None)
            if not isinstance(metadata, dict):
                metadata = {}
            
            if hasattr(self, 'scene_title_label'):
                self.scene_title_label.setText(title)
            if hasattr(self, 'scene_description_edit'):
                self.scene_description_edit.setPlainText(description)
            
            # Load generated content if available
            generated_content = ""
            if isinstance(metadata, dict):
                generated_content = metadata.get("generated_content", "")
            if hasattr(self, 'scene_content_display'):
                # Add paragraph numbers for display
                numbered_content = self._add_paragraph_numbers(generated_content)
                self.scene_content_display.setPlainText(numbered_content)
            
            # Update right panel details
            if hasattr(self, 'plot_point_label'):
                plot_point = getattr(scene, 'plot_point', None)
                self.plot_point_label.setText(plot_point if plot_point else "None")
            
            if hasattr(self, 'character_list'):
                character_focus = getattr(scene, 'character_focus', []) or []
                self.character_list.clear()
                for char in character_focus:
                    self.character_list.addItem(char)
            
            # Populate character wardrobe for this scene
            self._refresh_wardrobe_ui(scene)
            
            if hasattr(self, 'pacing_label'):
                pacing = getattr(scene, 'pacing', 'Medium') or 'Medium'
                self.pacing_label.setText(pacing)
            
            if hasattr(self, 'duration_spinbox'):
                estimated_duration = getattr(scene, 'estimated_duration', 0) or 0
                self.duration_spinbox.setValue(estimated_duration)
            
            if hasattr(self, 'compression_strategy_label'):
                compression_strategy = getattr(scene, 'compression_strategy', 'beat_by_beat') or 'beat_by_beat'
                # Format for display
                strategy_display = {
                    'montage': 'Montage',
                    'beat_by_beat': 'Beat-by-Beat',
                    'atmospheric_hold': 'Atmospheric Hold'
                }.get(compression_strategy, compression_strategy.title().replace('_', '-'))
                self.compression_strategy_label.setText(strategy_display)
            
            # Advertisement mode: show beat type info
            if hasattr(self, 'ad_info_group'):
                ad_beat_type = getattr(scene, 'ad_beat_type', '') or ''
                if ad_beat_type and self.screenplay and self.screenplay.is_advertisement_mode():
                    self.ad_info_group.setVisible(True)
                    from core.ad_framework import AD_BEAT_LABELS, AD_BEAT_GUIDANCE
                    label = AD_BEAT_LABELS.get(ad_beat_type, ad_beat_type)
                    guidance = AD_BEAT_GUIDANCE.get(ad_beat_type, '')
                    self.ad_beat_type_label.setText(label)
                    self.ad_beat_type_label.setToolTip(guidance)
                    # Show product reveal / brand hero shot flags
                    flags = []
                    if getattr(scene, 'is_product_reveal', False):
                        flags.append("Product Reveal")
                    if getattr(scene, 'is_brand_hero_shot', False):
                        flags.append("Brand Hero Shot")
                    self.ad_flags_label.setText(", ".join(flags) if flags else "None")
                else:
                    self.ad_info_group.setVisible(False)
            
            # Visual Art mode: load style selector
            if hasattr(self, 'visual_art_style_combo'):
                style = getattr(scene, 'visual_art_style', 'progressive') or 'progressive'
                idx = self.visual_art_style_combo.findData(style)
                if idx >= 0:
                    self.visual_art_style_combo.blockSignals(True)
                    self.visual_art_style_combo.setCurrentIndex(idx)
                    self.visual_art_style_combo.blockSignals(False)
            
            # Storyboard items
            if hasattr(self, 'load_storyboard_items'):
                self.load_storyboard_items()
            
            # Sync multi-shot toggle to reflect current scene's clustering state
            if hasattr(self, 'multishot_toggle') and self.multishot_toggle.isEnabled():
                has_clusters = bool(getattr(scene, 'multishot_clusters', None))
                self.multishot_toggle.blockSignals(True)
                self.multishot_toggle.setChecked(has_clusters)
                self.multishot_toggle.blockSignals(False)
            
            # Enable add button when scene is selected
            if hasattr(self, 'add_storyboard_item_btn'):
                self.add_storyboard_item_btn.setEnabled(True)
        except Exception as e:
            # Silently handle errors - don't show message box during initialization
            try:
                log_exception("Error loading scene data", e)
            except:
                pass
    
    def sync_current_scene_to_model(self):
        """Sync the current UI state (scene content, description, wardrobe) back to the model.
        
        MUST be called before any save-to-disk to capture manual edits.
        """
        if not self.current_scene:
            return
        
        # Sync scene description
        if hasattr(self, 'scene_description_edit'):
            new_desc = self.scene_description_edit.toPlainText().strip()
            if new_desc:
                self.current_scene.description = new_desc
        
        # Sync generated content from the display widget to metadata
        if hasattr(self, 'scene_content_display'):
            display_text = self.scene_content_display.toPlainText().strip()
            if display_text:
                clean_text = self._remove_paragraph_numbers(display_text)
                if self.current_scene.metadata is None:
                    self.current_scene.metadata = {}
                self.current_scene.metadata["generated_content"] = clean_text
            elif self.current_scene.metadata and "generated_content" in self.current_scene.metadata:
                del self.current_scene.metadata["generated_content"]
        
        # Sync wardrobe selector state
        if hasattr(self, 'wardrobe_selectors') and self.screenplay and self.current_scene:
            if not hasattr(self.current_scene, 'character_wardrobe_selector'):
                self.current_scene.character_wardrobe_selector = {}
            for entity_id, combo in self.wardrobe_selectors.items():
                self.current_scene.character_wardrobe_selector[entity_id] = combo.currentData() or ""

    def _is_first_scene(self, scene: StoryScene) -> bool:
        """Return True if *scene* is the very first scene across all acts."""
        if not self.screenplay:
            return False
        all_scenes = self.screenplay.get_all_scenes()
        return bool(all_scenes) and getattr(all_scenes[0], 'scene_id', None) == getattr(scene, 'scene_id', None)

    def _refresh_wardrobe_ui(self, scene: StoryScene):
        """Populate the wardrobe state selector for each character in the scene."""
        if not hasattr(self, 'wardrobe_form') or not self.screenplay:
            return

        if self._is_first_scene(scene):
            self.wardrobe_group.setVisible(False)
            return
        self.wardrobe_group.setVisible(True)
        while self.wardrobe_form.rowCount() > 0:
            self.wardrobe_form.removeRow(0)
        self.wardrobe_selectors.clear()
        self.wardrobe_edits.clear()

        seen_lower: Dict[str, str] = {}
        for name in (getattr(scene, 'character_focus', []) or []):
            key = name.strip().lower()
            if key and key not in seen_lower:
                seen_lower[key] = name.strip()
        wardrobe = getattr(scene, 'character_wardrobe', None) or {}
        for entity_id in wardrobe:
            meta = self.screenplay.identity_block_metadata.get(entity_id, {})
            if meta.get("type") == "character" and meta.get("name"):
                block_name = meta["name"].strip()
                key = block_name.lower()
                if key not in seen_lower:
                    display_name = block_name.title() if block_name == block_name.upper() else block_name
                    seen_lower[key] = display_name

        char_names = sorted(seen_lower.values())
        selector_state = getattr(scene, 'character_wardrobe_selector', {}) or {}
        last_variants = getattr(self.screenplay, 'character_last_wardrobe_variant', {}) or {}

        for char_name in char_names:
            lookup = f"character:{char_name}".lower()
            entity_id = self.screenplay.identity_block_ids.get(lookup)
            if not entity_id and getattr(self.screenplay, "character_registry_frozen", False):
                canonical = self.screenplay.resolve_character_to_canonical(char_name)
                if canonical:
                    entity_id = self.screenplay.identity_block_ids.get(f"character:{canonical}".lower())
            if not entity_id:
                continue

            has_previous = bool(last_variants.get(entity_id))
            combo = QComboBox()
            combo.addItem("-- Select wardrobe state --", "")
            if has_previous:
                prev_var = self.screenplay.get_wardrobe_variant_by_id(entity_id, last_variants[entity_id])
                prev_label = prev_var.get("label", "previous") if prev_var else "previous"
                combo.addItem(f"Same wardrobe from last scene ({prev_label})", "same")
            combo.addItem("Wardrobe change (new outfit)", "change")
            combo.addItem("Wardrobe change seen in this scene", "change_in_scene")

            saved = selector_state.get(entity_id, "")
            idx = combo.findData(saved)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif has_previous and not saved:
                combo.setCurrentIndex(combo.findData("same"))

            def _on_changed(_, eid=entity_id, cb=combo):
                self._on_wardrobe_selector_changed(eid, cb)
            combo.currentIndexChanged.connect(_on_changed)

            self.wardrobe_form.addRow(f"{char_name}:", combo)
            self.wardrobe_selectors[entity_id] = combo

    def _on_wardrobe_selector_changed(self, entity_id: str, combo: QComboBox):
        """Persist the wardrobe selector choice to the current scene."""
        if not self.screenplay or not hasattr(self, 'current_scene') or not self.current_scene:
            return
        value = combo.currentData()
        if not hasattr(self.current_scene, 'character_wardrobe_selector'):
            self.current_scene.character_wardrobe_selector = {}
        self.current_scene.character_wardrobe_selector[entity_id] = value or ""
    
    def clear_scene_data(self):
        """Clear the scene data display."""
        self.scene_title_label.setText("No scene selected")
        self.scene_description_edit.clear()
        if hasattr(self, 'scene_content_display'):
            self.scene_content_display.clear()
        # Right panel widgets removed
        self.storyboard_list.clear()
    
    def _is_micro_narrative(self) -> bool:
        """Return True when the story is micro length with a narrative workflow."""
        if not self.screenplay:
            return False
        length = getattr(self.screenplay, "story_length", "medium") or "medium"
        intent = getattr(self.screenplay, "intent", "General Story") or "General Story"
        profile = WorkflowProfileManager.get_profile(length, intent)
        return length == "micro" and profile == WorkflowProfile.NARRATIVE

    def _update_char_tab_for_micro(self):
        """Legacy wrapper — delegates to role-aware visibility."""
        self._update_char_fields_visibility(None)

    def _update_char_fields_visibility(self, char: dict = None):
        """Hide outline/growth_arc for minor characters or micro stories."""
        is_minor = isinstance(char, dict) and char.get("role", "main") == "minor"
        is_micro = self._is_micro_narrative()
        hide_details = is_minor or is_micro
        if hasattr(self, 'char_outline_label'):
            self.char_outline_label.setVisible(not hide_details)
        if hasattr(self, 'char_details_outline_edit'):
            self.char_details_outline_edit.setVisible(not hide_details)
        if hasattr(self, 'char_growth_label'):
            self.char_growth_label.setVisible(not hide_details)
        if hasattr(self, 'char_details_growth_edit'):
            self.char_details_growth_edit.setVisible(not hide_details)
        if hasattr(self, 'generate_char_details_btn'):
            if hide_details:
                self.generate_char_details_btn.setToolTip("Generate physical appearance using AI")
            else:
                self.generate_char_details_btn.setToolTip("Generate full profile (physical appearance, outline, growth arc) using AI")

    def update_character_details(self):
        """Update the character details list and show selected character in the right panel."""
        if not hasattr(self, 'char_details_list'):
            return
        # Show/hide outline and growth arc based on story mode
        self._update_char_tab_for_micro()
        # Save current edits to the character that was selected (if any) before clearing
        self._save_current_char_details_to_data()
        
        if not self.screenplay:
            self.char_details_list.clear()
            self._load_char_into_editor(None)
            return
        
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            story_outline = {}
            self.screenplay.story_outline = story_outline
        if "characters" not in story_outline:
            story_outline["characters"] = []
        
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list):
            characters = []
            story_outline["characters"] = characters
        
        # Populate list only (wizard-style: list left, editor right)
        self.char_details_list.blockSignals(True)
        self.char_details_list.clear()
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = str(char.get("name", "Unnamed Character")).strip() or "Unnamed Character"
            role = char.get("role", "main")
            species = char.get("species", "Human")
            prefix = "[Minor] " if role == "minor" else ""
            suffix = f"  ({species})" if species and species != "Human" else ""
            self.char_details_list.addItem(QListWidgetItem(f"{prefix}{name}{suffix}"))
        self.char_details_list.blockSignals(False)
        
        if len(characters) == 0:
            self._load_char_into_editor(None)
            return
        
        # Select first character and load into editor
        self.char_details_list.setCurrentRow(0)
        self._load_char_into_editor(0)
        self._char_details_last_row = 0
    
    def _save_char_details_to_row(self, row: int):
        """Save the current editor contents to the character at the given list index."""
        if not hasattr(self, 'char_details_list') or not self.screenplay or getattr(self, '_loading_char_selection', False):
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            return
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list) or row < 0 or row >= len(characters):
            return
        char = characters[row]
        if not isinstance(char, dict):
            return
        char["name"] = self.char_details_name_edit.text().strip() or "Unnamed Character"
        char["outline"] = self.char_details_outline_edit.toPlainText().strip()
        char["growth_arc"] = self.char_details_growth_edit.toPlainText().strip()
        phys = self._strip_wardrobe_suffix(self.char_details_physical_edit.toPlainText().strip())
        char["physical_appearance"] = phys
        # Save role from toggle
        if hasattr(self, 'char_role_toggle'):
            char["role"] = "minor" if self.char_role_toggle.isChecked() else "main"
        # Save species
        char["species"] = self._get_current_species()
        item = self.char_details_list.item(row)
        if item:
            role = char.get("role", "main")
            species = char.get("species", "Human")
            prefix = "[Minor] " if role == "minor" else ""
            suffix = f"  ({species})" if species and species != "Human" else ""
            item.setText(f"{prefix}{char['name']}{suffix}")
    
    def _save_current_char_details_to_data(self):
        """Save the current editor contents to the character at the selected list index."""
        if not hasattr(self, 'char_details_list') or not self.screenplay or getattr(self, '_loading_char_selection', False):
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            return
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list):
            return
        row = self.char_details_list.currentRow()
        if row < 0 or row >= len(characters):
            return
        char = characters[row]
        if not isinstance(char, dict):
            return
        char["name"] = self.char_details_name_edit.text().strip() or "Unnamed Character"
        char["outline"] = self.char_details_outline_edit.toPlainText().strip()
        char["growth_arc"] = self.char_details_growth_edit.toPlainText().strip()
        char["physical_appearance"] = self._strip_wardrobe_suffix(self.char_details_physical_edit.toPlainText().strip())
        # Save role from toggle
        if hasattr(self, 'char_role_toggle'):
            char["role"] = "minor" if self.char_role_toggle.isChecked() else "main"
        # Save species
        char["species"] = self._get_current_species()
        # Keep list item text in sync with name, role badge, and species
        item = self.char_details_list.item(row)
        if item:
            role = char.get("role", "main")
            species = char.get("species", "Human")
            prefix = "[Minor] " if role == "minor" else ""
            suffix = f"  ({species})" if species and species != "Human" else ""
            item.setText(f"{prefix}{char['name']}{suffix}")
    
    def _load_char_into_editor(self, index: Optional[int]):
        """Load character at index into the right-panel editor. None = empty/placeholder."""
        self._loading_char_selection = True
        try:
            if index is None or not self.screenplay:
                self.char_details_name_edit.clear()
                self.char_details_outline_edit.clear()
                self.char_details_growth_edit.clear()
                self.char_details_physical_edit.clear()
                if hasattr(self, 'char_identity_block_edit'):
                    self.char_identity_block_edit.clear()
                if hasattr(self, 'char_ref_prompt_edit'):
                    self.char_ref_prompt_edit.clear()
                self._first_scene_wardrobe_suffix = ""
                self._clear_wardrobe_variant_widgets()
                self.char_details_editor.setEnabled(False)
                self._update_identity_block_buttons()
                return
            story_outline = getattr(self.screenplay, 'story_outline', {})
            characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
            if index < 0 or index >= len(characters):
                self.char_details_editor.setEnabled(False)
                self._update_identity_block_buttons()
                return
            char = characters[index]
            if not isinstance(char, dict):
                self.char_details_editor.setEnabled(False)
                self._update_identity_block_buttons()
                return
            self.char_details_name_edit.setText(str(char.get("name", "")).strip() or "Unnamed Character")
            self.char_details_outline_edit.setPlainText(str(char.get("outline", "")).strip())
            self.char_details_growth_edit.setPlainText(str(char.get("growth_arc", "")).strip())
            self.char_details_physical_edit.setPlainText(str(char.get("physical_appearance", "")).strip())
            # Set role toggle state (checked = minor, unchecked = main)
            if hasattr(self, 'char_role_toggle'):
                is_minor = char.get("role", "main") == "minor"
                self.char_role_toggle.blockSignals(True)
                self.char_role_toggle.setChecked(is_minor)
                self.char_role_toggle.setText("Minor Character" if is_minor else "Main Character")
                self.char_role_toggle.blockSignals(False)
            # Set species / form
            if hasattr(self, 'char_species_combo'):
                species = str(char.get("species", "Human")).strip() or "Human"
                combo_idx = self.char_species_combo.findText(species)
                self.char_species_combo.blockSignals(True)
                if combo_idx >= 0:
                    self.char_species_combo.setCurrentIndex(combo_idx)
                    self.char_species_custom_edit.setVisible(False)
                else:
                    self.char_species_combo.setCurrentText("Custom...")
                    self.char_species_custom_edit.setVisible(True)
                    self.char_species_custom_edit.setText(species)
                self.char_species_combo.blockSignals(False)
                self._update_physical_placeholder()
            self.char_details_editor.setEnabled(True)
            # Load identity block and reference prompt from identity_block_metadata
            self._load_char_identity_block_data()
            self._update_identity_block_buttons()
            # Update field visibility based on character role and story mode
            self._update_char_fields_visibility(char)
            # Load wardrobe variants for this character
            self._load_wardrobe_variants_for_character(char)
            # Load first scene wardrobe display
            self._load_first_scene_wardrobe(char)
        finally:
            self._loading_char_selection = False
    
    def _populate_species_combo(self):
        """Fill the species combo with built-in + user-custom species + 'Custom...'."""
        from core.ai_generator import get_all_species_options
        combo = self.char_species_combo
        prev = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(get_all_species_options() + ["Custom..."])
        if prev:
            idx = combo.findText(prev)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _on_char_species_changed(self, text: str):
        """Handle species combo change."""
        if getattr(self, '_loading_char_selection', False):
            return
        show_custom = (text == "Custom...")
        if hasattr(self, 'char_species_custom_edit'):
            self.char_species_custom_edit.setVisible(show_custom)
            if show_custom:
                self.char_species_custom_edit.setFocus()
        self._update_physical_placeholder()
        self._save_species_to_current_char()

    def _on_char_species_custom_changed(self, text: str):
        """Handle custom species text change."""
        if getattr(self, '_loading_char_selection', False):
            return
        self._update_physical_placeholder()
        self._save_species_to_current_char()

    def _get_current_species(self) -> str:
        """Return the resolved species string for the currently selected character."""
        if not hasattr(self, 'char_species_combo'):
            return "Human"
        selected = self.char_species_combo.currentText()
        if selected == "Custom..." and hasattr(self, 'char_species_custom_edit'):
            custom = self.char_species_custom_edit.text().strip()
            return custom if custom else "Human"
        return selected or "Human"

    def _sync_character_registry(self):
        """Rebuild character_registry from the current story_outline characters list.
        Keeps the registry in sync when characters are added, removed, or renamed."""
        if not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            return
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list):
            return
        registry = []
        seen = set()
        for ch in characters:
            if not isinstance(ch, dict):
                continue
            name = str(ch.get("name", "")).strip()
            if name and name.lower() not in seen:
                registry.append(name)
                seen.add(name.lower())
        self.screenplay.character_registry = registry
        self.screenplay.character_registry_frozen = bool(registry)

    def _save_species_to_current_char(self):
        """Persist the current species selection to the character data."""
        if not self.screenplay or getattr(self, '_loading_char_selection', False):
            return
        row = self.char_details_list.currentRow() if hasattr(self, 'char_details_list') else -1
        if row < 0:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        char = characters[row]
        if not isinstance(char, dict):
            return
        char["species"] = self._get_current_species()

    def _on_char_species_custom_committed(self):
        """Called when the user presses Enter or leaves the custom species field.

        Saves the custom species to the global config so it appears in the
        dropdown for all future stories.
        """
        if getattr(self, '_loading_char_selection', False):
            return
        species = self._get_current_species()
        self._maybe_persist_custom_species(species)

    def _maybe_persist_custom_species(self, species: str):
        """If *species* is a new custom value, persist it globally and refresh the dropdown."""
        if not species or species == "Custom...":
            return
        from core.ai_generator import _SPECIES_DROPDOWN_OPTIONS
        if species in _SPECIES_DROPDOWN_OPTIONS:
            return
        from config import config
        if config.add_custom_species(species):
            self._populate_species_combo()
            idx = self.char_species_combo.findText(species)
            if idx >= 0:
                self.char_species_combo.blockSignals(True)
                self.char_species_combo.setCurrentIndex(idx)
                self.char_species_combo.blockSignals(False)
                if hasattr(self, 'char_species_custom_edit'):
                    self.char_species_custom_edit.setVisible(False)

    def _update_physical_placeholder(self):
        """Update the physical appearance placeholder text based on species."""
        if not hasattr(self, 'char_details_physical_edit'):
            return
        species = self._get_current_species()
        if species == "Human":
            self.char_details_physical_edit.setPlaceholderText(
                "Gender, height, face, hair, eyes, skin, age, build, scars. No character name."
            )
        elif species == "Dragon":
            self.char_details_physical_edit.setPlaceholderText(
                "Size, scale colour/texture, wing span, eye colour, horn/crest shape, body build, tail, claws, distinguishing marks."
            )
        elif species in ("Robot / Android",):
            self.char_details_physical_edit.setPlaceholderText(
                "Height, chassis design, plating colour, eye/sensor style, build, distinguishing marks, humanoid features."
            )
        elif species in ("Ghost / Spirit",):
            self.char_details_physical_edit.setPlaceholderText(
                "Apparition form, translucency, glow colour, visible features (face, hair, build), distinguishing marks."
            )
        elif species == "Animal":
            self.char_details_physical_edit.setPlaceholderText(
                "Animal type, size, fur/feather/scale colour, eye colour, build, distinguishing marks."
            )
        else:
            self.char_details_physical_edit.setPlaceholderText(
                f"Describe the physical appearance of this {species}. Include size, colouring, distinguishing features, build."
            )

    def _on_char_role_toggled(self, checked: bool):
        """Handle role toggle: checked = minor, unchecked = main."""
        if getattr(self, '_loading_char_selection', False):
            return
        self.char_role_toggle.setText("Minor Character" if checked else "Main Character")
        row = self.char_details_list.currentRow() if hasattr(self, 'char_details_list') else -1
        if row < 0 or not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        char = characters[row]
        if not isinstance(char, dict):
            return
        new_role = "minor" if checked else "main"
        char["role"] = new_role
        # If switching to minor, clear outline and growth arc
        if new_role == "minor":
            char["outline"] = ""
            char["growth_arc"] = ""
            self.char_details_outline_edit.blockSignals(True)
            self.char_details_outline_edit.clear()
            self.char_details_outline_edit.blockSignals(False)
            self.char_details_growth_edit.blockSignals(True)
            self.char_details_growth_edit.clear()
            self.char_details_growth_edit.blockSignals(False)
        # Update visibility
        self._update_char_fields_visibility(char)
        # Update list display
        item = self.char_details_list.item(row)
        if item:
            name = char.get("name", "Unnamed Character")
            item.setText(f"[Minor] {name}" if new_role == "minor" else name)

    def _on_generate_char_details_clicked(self):
        """Generate character details via AI based on the current role."""
        if not self.screenplay or not self.ai_generator:
            return
        row = self.char_details_list.currentRow() if hasattr(self, 'char_details_list') else -1
        if row < 0:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        char = characters[row]
        if not isinstance(char, dict):
            return
        char_name = (char.get("name", "") or "").strip()
        if not char_name or char_name == "New Character":
            self._show_status("Please enter a character name before generating details.")
            return
        is_minor = char.get("role", "main") == "minor"
        is_micro = self._is_micro_narrative()
        # Determine generation type
        if is_minor or is_micro:
            gen_type = "physical_appearance"
            gen_label = "physical appearance"
        else:
            gen_type = "both"
            gen_label = "full profile"
        # Disable button during generation
        self.generate_char_details_btn.setEnabled(False)
        self.generate_char_details_btn.setText("Generating...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            premise = getattr(self.screenplay, 'premise', '') or ''
            genres = getattr(self.screenplay, 'genre', []) or []
            atmosphere = getattr(self.screenplay, 'atmosphere', '') or ''
            title = getattr(self.screenplay, 'title', '') or ''
            storyline = story_outline.get("main_storyline", "") or ""
            other_chars = [c for c in characters if isinstance(c, dict) and c.get("name", "").lower() != char_name.lower()]
            char_species = char.get("species", "Human") or "Human"
            result = self.ai_generator.regenerate_character_details(
                premise=premise,
                genres=genres,
                atmosphere=atmosphere,
                title=title,
                main_storyline=storyline,
                character_name=char_name,
                regenerate_type=gen_type,
                existing_characters=other_chars,
                species=char_species,
            )
            # Apply results
            phys = (result.get("physical_appearance", "") or "").strip()
            if phys:
                char["physical_appearance"] = phys
                self.char_details_physical_edit.blockSignals(True)
                wardrobe_sfx = getattr(self, '_first_scene_wardrobe_suffix', "")
                self.char_details_physical_edit.setPlainText(phys + wardrobe_sfx)
                self.char_details_physical_edit.blockSignals(False)
            if not is_minor and not is_micro:
                outline = (result.get("outline", "") or "").strip()
                growth = (result.get("growth_arc", "") or "").strip()
                if outline:
                    char["outline"] = outline
                    self.char_details_outline_edit.blockSignals(True)
                    self.char_details_outline_edit.setPlainText(outline)
                    self.char_details_outline_edit.blockSignals(False)
                if growth:
                    char["growth_arc"] = growth
                    self.char_details_growth_edit.blockSignals(True)
                    self.char_details_growth_edit.setPlainText(growth)
                    self.char_details_growth_edit.blockSignals(False)
            self._show_status(f"Generated {gen_label} for {char_name}.")
        except Exception as e:
            self._show_status(f"Failed to generate details for {char_name}: {e}")
        finally:
            self.generate_char_details_btn.setEnabled(True)
            self.generate_char_details_btn.setText("Generate Details")

    def on_char_details_selected(self, row: int):
        """When user selects a character in the list: save previous character, then load selected."""
        prev = getattr(self, '_char_details_last_row', -1)
        if prev >= 0:
            self._save_char_details_to_row(prev)
        if row >= 0:
            self._load_char_into_editor(row)
        elif not (hasattr(self, 'char_details_list') and self.char_details_list.count() > 0):
            self._load_char_into_editor(None)
        self._char_details_last_row = row
    
    def on_char_details_name_changed(self, text: str):
        if getattr(self, '_loading_char_selection', False):
            return
        row = self.char_details_list.currentRow()
        if row < 0 or not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        display = (text or "Unnamed Character").strip() or "Unnamed Character"
        characters[row]["name"] = display
        item = self.char_details_list.item(row)
        if item:
            role = characters[row].get("role", "main")
            species = characters[row].get("species", "Human")
            prefix = "[Minor] " if role == "minor" else ""
            suffix = f"  ({species})" if species and species != "Human" else ""
            item.setText(f"{prefix}{display}{suffix}")
        self._sync_character_registry()
    
    def on_char_details_outline_changed(self):
        if getattr(self, '_loading_char_selection', False):
            return
        row = self.char_details_list.currentRow()
        if row < 0 or not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row < len(characters):
            characters[row]["outline"] = self.char_details_outline_edit.toPlainText().strip()
    
    def on_char_details_growth_changed(self):
        if getattr(self, '_loading_char_selection', False):
            return
        row = self.char_details_list.currentRow()
        if row < 0 or not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row < len(characters):
            characters[row]["growth_arc"] = self.char_details_growth_edit.toPlainText().strip()
    
    def on_char_details_physical_changed(self):
        if getattr(self, '_loading_char_selection', False):
            return
        row = self.char_details_list.currentRow()
        if row < 0 or not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row < len(characters):
            characters[row]["physical_appearance"] = self._strip_wardrobe_suffix(self.char_details_physical_edit.toPlainText().strip())
        self._update_identity_block_buttons()
    
    def _on_char_identity_block_changed(self):
        """Handle edits to the identity block text area."""
        if getattr(self, '_loading_char_selection', False):
            return
        entity_id = self._get_current_char_entity_id()
        if entity_id and self.screenplay:
            ib_text = self.char_identity_block_edit.toPlainText().strip()
            self.screenplay.update_identity_block_metadata(entity_id, identity_block=ib_text)
        self._update_identity_block_buttons()
    
    def _update_identity_block_buttons(self):
        """Update enabled/disabled state of identity block and reference prompt buttons."""
        if not hasattr(self, 'char_generate_ib_btn'):
            return
        has_physical = bool(self.char_details_physical_edit.toPlainText().strip()) if hasattr(self, 'char_details_physical_edit') else False
        has_ai = self.ai_generator is not None
        has_ib = bool(self.char_identity_block_edit.toPlainText().strip()) if hasattr(self, 'char_identity_block_edit') else False
        has_rip = bool(self.char_ref_prompt_edit.toPlainText().strip()) if hasattr(self, 'char_ref_prompt_edit') else False
        
        self.char_generate_ib_btn.setEnabled(has_physical and has_ai)
        if not has_physical:
            self.char_generate_ib_btn.setToolTip("Physical Appearance must be defined first.")
        elif not has_ai:
            self.char_generate_ib_btn.setToolTip("AI Generator not available. Check settings.")
        else:
            self.char_generate_ib_btn.setToolTip("Generate a detailed identity block from physical appearance and wardrobe.")
        self.char_generate_ib_btn.setText(
            "Regenerate Identity Block" if has_ib else "Generate Identity Block"
        )
        self.char_approve_ib_btn.setEnabled(has_ib)
        self.char_copy_rip_btn.setEnabled(has_rip)
    
    # ── Wardrobe Variant Management ────────────────────────────────────

    def _get_current_char_entity_id(self) -> str:
        """Return the identity-block entity_id for the currently selected character, or ''."""
        row = self.char_details_list.currentRow()
        if row < 0 or not self.screenplay:
            return ""
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return ""
        char_name = str(characters[row].get("name", "")).strip()
        if not char_name:
            return ""
        lookup = f"character:{char_name}".lower()
        entity_id = self.screenplay.identity_block_ids.get(lookup, "")
        if not entity_id:
            canonical = self.screenplay.resolve_character_to_canonical(char_name) if hasattr(self.screenplay, 'resolve_character_to_canonical') else None
            if canonical:
                entity_id = self.screenplay.identity_block_ids.get(f"character:{canonical}".lower(), "")
        return entity_id

    def _clear_wardrobe_variant_widgets(self):
        """Remove all dynamically created wardrobe variant widgets."""
        for w_info in getattr(self, '_wardrobe_variant_widgets', []):
            group = w_info.get("group")
            if group:
                group.setParent(None)
                group.deleteLater()
        self._wardrobe_variant_widgets = []

    def _load_wardrobe_variants_for_character(self, char: dict):
        """Populate the wardrobe variants section from screenplay data.

        The first-scene wardrobe variant is shown with a read-only description
        only (no identity block / reference image prompt).  Detection uses the
        variant_id stored on the first scene rather than string comparison.
        """
        self._clear_wardrobe_variant_widgets()
        entity_id = self._get_current_char_entity_id()
        if not entity_id or not self.screenplay:
            return

        # Find the variant_id assigned to this character in the first scene
        first_variant_id = ""
        for scene in self.screenplay.get_all_scenes():
            vids = getattr(scene, "character_wardrobe_variant_ids", {}) or {}
            if entity_id in vids:
                first_variant_id = vids[entity_id]
                break

        variants = self.screenplay.get_wardrobe_variants(entity_id)
        seen_first = False
        for v in variants:
            vid = v.get("variant_id", "")
            is_first = not seen_first and bool(first_variant_id) and vid == first_variant_id
            if is_first:
                seen_first = True
            self._add_wardrobe_variant_widget(v, entity_id, is_first_scene=is_first)

    def _load_char_identity_block_data(self):
        """Load identity block, reference prompt, and reference image from identity_block_metadata."""
        entity_id = self._get_current_char_entity_id()
        ib_text = ""
        rip_text = ""
        img_path = ""
        if entity_id and self.screenplay:
            metadata = self.screenplay.get_identity_block_metadata_by_id(entity_id)
            if metadata:
                ib_text = str(metadata.get("identity_block", "") or "").strip()
                rip_text = str(metadata.get("reference_image_prompt", "") or "").strip()
                img_path = str(metadata.get("image_path", "") or "").strip()
        if hasattr(self, 'char_identity_block_edit'):
            self.char_identity_block_edit.setPlainText(ib_text)
        if hasattr(self, 'char_ref_prompt_edit'):
            self.char_ref_prompt_edit.setPlainText(rip_text)
        if hasattr(self, 'char_ref_thumb'):
            if img_path:
                self.char_ref_thumb.setImageFromPath(img_path)
            else:
                self.char_ref_thumb.clearImage()

    def _load_first_scene_wardrobe(self, char: dict):
        """Append the first scene wardrobe to the physical appearance text field."""
        self._first_scene_wardrobe_suffix = ""
        entity_id = self._get_current_char_entity_id()
        if not entity_id or not self.screenplay:
            return
        all_scenes = self.screenplay.get_all_scenes()
        for scene in all_scenes:
            wardrobe = (getattr(scene, "character_wardrobe", None) or {}).get(entity_id, "")
            if wardrobe.strip():
                suffix = f" Wearing {wardrobe.strip()}"
                self._first_scene_wardrobe_suffix = suffix
                self.char_details_physical_edit.blockSignals(True)
                current = self.char_details_physical_edit.toPlainText()
                self.char_details_physical_edit.setPlainText(current + suffix)
                self.char_details_physical_edit.blockSignals(False)
                return

    def _strip_wardrobe_suffix(self, text: str) -> str:
        """Strip the dynamically-appended wardrobe suffix from physical appearance text."""
        suffix = getattr(self, '_first_scene_wardrobe_suffix', "")
        if suffix and text.endswith(suffix):
            return text[:-len(suffix)]
        return text

    def _add_wardrobe_variant_widget(
        self, variant_data: dict, entity_id: str, *, is_first_scene: bool = False
    ):
        """Create a single wardrobe variant group box and add it to the container.

        When *is_first_scene* is True the variant represents Scene 1 and only
        shows a read-only wardrobe description — no identity block, reference
        image prompt, or image upload (those come from the main character
        identity block above).
        """
        from PyQt6.QtWidgets import QFileDialog
        import uuid as _uuid

        vid = variant_data.get("variant_id", str(_uuid.uuid4())[:8])
        group = QGroupBox()
        group.setStyleSheet("QGroupBox { border: 1px solid #555555; border-radius: 4px; margin-top: 6px; padding-top: 14px; }")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)

        img_path = variant_data.get("image_path", "")

        if is_first_scene:
            # ── Scene 1: minimal card — label + read-only description only ──
            header = QHBoxLayout()
            label_edit = QLineEdit(variant_data.get("label", "") or "Scene 1 (Default)")
            label_edit.setMaximumWidth(260)
            header.addWidget(QLabel("Label:"))
            header.addWidget(label_edit)
            header.addStretch()
            layout.addLayout(header)

            desc_label = QLabel("Wardrobe Description (Scene 1):")
            desc_edit = QTextEdit()
            desc_edit.setPlainText(variant_data.get("description", ""))
            desc_edit.setReadOnly(True)
            desc_edit.setMaximumHeight(80)
            desc_edit.setStyleSheet(
                "QTextEdit { background-color: #353535; color: #cccccc; border: 1px solid #555555; }"
            )
            desc_edit.setToolTip(
                "Scene 1 wardrobe is defined during scene setup.\n"
                "The identity block and reference image are handled by the\n"
                "main character identity block above."
            )
            layout.addWidget(desc_label)
            layout.addWidget(desc_edit)

            note = QLabel(
                "Identity block and reference image use the main character "
                "identity block above."
            )
            note.setStyleSheet("color: #888; font-style: italic; font-size: 10px;")
            note.setWordWrap(True)
            layout.addWidget(note)

            self.wardrobe_variants_container.addWidget(group)

            w_info = {
                "group": group,
                "variant_id": vid,
                "entity_id": entity_id,
                "label_edit": label_edit,
                "desc_edit": desc_edit,
                "ib_edit": None,
                "rip_edit": None,
                "approve_btn": None,
                "copy_btn": None,
                "thumb": None,
                "status_label": None,
                "image_path": img_path,
                "is_first_scene": True,
            }
            self._wardrobe_variant_widgets.append(w_info)

            def _save_s1():
                self._save_wardrobe_variant(w_info)
            label_edit.textChanged.connect(_save_s1)
            return

        # ── All other scenes: full variant card ─────────────────────

        # Label row
        lbl_row = QHBoxLayout()
        lbl_label = QLabel("Label:")
        label_edit = QLineEdit(variant_data.get("label", ""))
        label_edit.setPlaceholderText("e.g. Mill Outfit, Night Coat")
        label_edit.setMaximumWidth(260)
        lbl_row.addWidget(lbl_label)
        lbl_row.addWidget(label_edit)

        status_label = QLabel("")
        if not img_path:
            status_label.setText("Image Required")
            status_label.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 10px;")
        else:
            status_label.setText("Ready")
            status_label.setStyleSheet("color: #44bb44; font-weight: bold; font-size: 10px;")
        lbl_row.addWidget(status_label)
        lbl_row.addStretch()

        delete_btn = QPushButton("Delete")
        delete_btn.setFixedWidth(70)
        delete_btn.setStyleSheet("color: #ff4444;")
        lbl_row.addWidget(delete_btn)
        layout.addLayout(lbl_row)

        # Description notes
        desc_label = QLabel("Wardrobe Description Notes:")
        desc_edit = QTextEdit()
        desc_edit.setPlainText(variant_data.get("description", ""))
        desc_edit.setPlaceholderText("Clothing, accessories, condition...")
        desc_edit.setMaximumHeight(80)
        layout.addWidget(desc_label)
        layout.addWidget(desc_edit)

        # Generate Identity Block button
        gen_ib_row = QHBoxLayout()
        gen_ib_btn = QPushButton("Generate Identity Block")
        gen_ib_btn.setStyleSheet("background-color: #2196F3; color: white;")
        gen_ib_btn.setFixedWidth(220)
        gen_ib_row.addWidget(gen_ib_btn)
        gen_ib_row.addStretch()
        layout.addLayout(gen_ib_row)

        # Variant identity block (editable)
        ib_edit = QTextEdit()
        ib_edit.setPlainText(variant_data.get("identity_block", ""))
        ib_edit.setMaximumHeight(100)
        ib_edit.setPlaceholderText("Generated identity block for this wardrobe variant...")
        layout.addWidget(ib_edit)

        # Approve + Copy row
        approve_row = QHBoxLayout()
        approve_btn = QPushButton("Approve")
        approve_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        approve_btn.setFixedWidth(100)
        approve_btn.setEnabled(bool(variant_data.get("identity_block", "").strip()))
        approve_row.addWidget(approve_btn)
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setFixedWidth(140)
        copy_btn.setEnabled(bool(variant_data.get("reference_image_prompt", "").strip()))
        approve_row.addWidget(copy_btn)
        approve_row.addStretch()
        layout.addLayout(approve_row)

        # Reference image prompt (read-only)
        rip_edit = QTextEdit()
        rip_edit.setPlainText(variant_data.get("reference_image_prompt", ""))
        rip_edit.setReadOnly(True)
        rip_edit.setMaximumHeight(80)
        rip_edit.setPlaceholderText("Approve to generate the reference image prompt...")
        layout.addWidget(rip_edit)

        # Image row: thumbnail + upload/clear buttons
        img_row = QHBoxLayout()
        thumb = ClickableImageLabel(max_short=100, max_long=133)
        if img_path:
            thumb.setImageFromPath(img_path)
        img_row.addWidget(thumb)

        img_btn_col = QVBoxLayout()
        upload_btn = QPushButton("Upload Image")
        upload_btn.setFixedWidth(120)
        clear_img_btn = QPushButton("Clear")
        clear_img_btn.setFixedWidth(120)
        img_btn_col.addWidget(upload_btn)
        img_btn_col.addWidget(clear_img_btn)
        img_btn_col.addStretch()
        img_row.addLayout(img_btn_col)
        img_row.addStretch()
        layout.addLayout(img_row)

        self.wardrobe_variants_container.addWidget(group)

        w_info = {
            "group": group,
            "variant_id": vid,
            "entity_id": entity_id,
            "label_edit": label_edit,
            "desc_edit": desc_edit,
            "ib_edit": ib_edit,
            "rip_edit": rip_edit,
            "approve_btn": approve_btn,
            "copy_btn": copy_btn,
            "thumb": thumb,
            "status_label": status_label,
            "image_path": img_path,
            "is_first_scene": False,
        }
        self._wardrobe_variant_widgets.append(w_info)

        # Connections
        def _save():
            self._save_wardrobe_variant(w_info)

        label_edit.textChanged.connect(_save)
        desc_edit.textChanged.connect(_save)
        ib_edit.textChanged.connect(_save)

        def _update_approve_state():
            approve_btn.setEnabled(bool(ib_edit.toPlainText().strip()))
        ib_edit.textChanged.connect(_update_approve_state)

        def _gen_ib():
            self._on_generate_variant_identity_block(w_info)
        gen_ib_btn.clicked.connect(_gen_ib)

        def _approve():
            self._on_approve_variant_identity_block(w_info)
        approve_btn.clicked.connect(_approve)

        def _copy():
            from PyQt6.QtWidgets import QApplication
            txt = rip_edit.toPlainText()
            if txt:
                QApplication.clipboard().setText(txt)
        copy_btn.clicked.connect(_copy)

        def _upload():
            self._on_upload_wardrobe_image(w_info)
        upload_btn.clicked.connect(_upload)

        def _clear_img():
            self._on_clear_wardrobe_image(w_info)
        clear_img_btn.clicked.connect(_clear_img)

        def _delete():
            self._on_delete_wardrobe_variant(w_info)
        delete_btn.clicked.connect(_delete)

    def _save_wardrobe_variant(self, w_info: dict):
        """Persist the current widget state back to screenplay data."""
        if not self.screenplay or getattr(self, '_loading_char_selection', False):
            return
        eid = w_info["entity_id"]
        vid = w_info["variant_id"]
        ib_edit = w_info.get("ib_edit")
        rip_edit = w_info.get("rip_edit")
        self.screenplay.update_wardrobe_variant(
            eid, vid,
            label=w_info["label_edit"].text().strip(),
            description=w_info["desc_edit"].toPlainText().strip(),
            identity_block=ib_edit.toPlainText().strip() if ib_edit else "",
            reference_image_prompt=rip_edit.toPlainText().strip() if rip_edit else "",
            image_path=w_info.get("image_path", ""),
        )

    def _on_generate_variant_identity_block(self, w_info: dict):
        """Generate an identity block for a wardrobe variant."""
        if not self.ai_generator or not self.screenplay:
            QMessageBox.warning(self, "Not Available", "AI Generator not available.")
            return
        row = self.char_details_list.currentRow()
        if row < 0:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        char_name = str(characters[row].get("name", "")).strip() or "CHARACTER"
        wardrobe_desc = w_info["desc_edit"].toPlainText().strip()
        if not wardrobe_desc:
            QMessageBox.warning(self, "Missing Description", "Please enter a wardrobe description first.")
            return

        physical_only = self._strip_wardrobe_suffix(
            self.char_details_physical_edit.toPlainText().strip())
        scene_context = ""
        if self.current_scene:
            scene_context = getattr(self.current_scene, "description", "") or ""

        progress = QProgressDialog(
            f"Generating wardrobe identity block...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        progress.raise_()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            ib_text = self.ai_generator.generate_identity_block_from_notes(
                entity_name=char_name,
                entity_type="character",
                user_notes=wardrobe_desc,
                scene_context=scene_context,
                screenplay=self.screenplay,
                wizard_physical_appearance=physical_only,
            )
            if ib_text and ib_text.strip():
                w_info["ib_edit"].setPlainText(ib_text.strip())
                self._save_wardrobe_variant(w_info)
                progress.close()
                self._show_status("Wardrobe identity block generated", 3000)
            else:
                progress.close()
                QMessageBox.warning(self, "Generation Failed", "AI returned an empty result.")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Failed to generate:\n\n{str(e)}")

    def _on_approve_variant_identity_block(self, w_info: dict):
        """Approve a variant identity block and generate its reference image prompt."""
        if not self.ai_generator or not self.screenplay:
            QMessageBox.warning(self, "Not Available", "AI Generator not available.")
            return
        row = self.char_details_list.currentRow()
        if row < 0:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters):
            return
        char_name = str(characters[row].get("name", "")).strip() or "CHARACTER"
        ib_text = w_info["ib_edit"].toPlainText().strip()
        if not ib_text:
            QMessageBox.warning(self, "No Identity Block", "Generate an identity block first.")
            return

        progress = QProgressDialog(
            f"Generating wardrobe reference prompt...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        progress.raise_()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            ref_prompt = self.ai_generator.generate_reference_image_prompt(
                entity_name=char_name,
                entity_type="character",
                identity_block=ib_text,
            )
            if ref_prompt and ref_prompt.strip():
                w_info["rip_edit"].setPlainText(ref_prompt.strip())
                w_info["copy_btn"].setEnabled(True)
                self._save_wardrobe_variant(w_info)
                progress.close()
                self._show_status("Wardrobe variant approved", 3000)
            else:
                progress.close()
                QMessageBox.warning(self, "Generation Failed", "AI returned an empty prompt.")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Failed to generate:\n\n{str(e)}")

    def _on_upload_wardrobe_image(self, w_info: dict):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Wardrobe Image",
            "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        w_info["image_path"] = path
        w_info["thumb"].setImageFromPath(path)
        w_info["status_label"].setText("Ready")
        w_info["status_label"].setStyleSheet("color: #44bb44; font-weight: bold; font-size: 10px;")
        self._save_wardrobe_variant(w_info)

    def _on_clear_wardrobe_image(self, w_info: dict):
        w_info["image_path"] = ""
        w_info["thumb"].clearImage()
        w_info["status_label"].setText("Image Required")
        w_info["status_label"].setStyleSheet("color: #ff4444; font-weight: bold; font-size: 10px;")
        self._save_wardrobe_variant(w_info)

    def _on_delete_wardrobe_variant(self, w_info: dict):
        if not self.screenplay:
            return
        reply = QMessageBox.question(
            self, "Delete Variant",
            f"Delete wardrobe variant '{w_info['label_edit'].text().strip() or 'Untitled'}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.screenplay.delete_wardrobe_variant(w_info["entity_id"], w_info["variant_id"])
        w_info["group"].setParent(None)
        w_info["group"].deleteLater()
        self._wardrobe_variant_widgets = [w for w in self._wardrobe_variant_widgets if w is not w_info]

    def _on_add_wardrobe_variant(self):
        """Add a new empty wardrobe variant for the currently selected character."""
        import uuid as _uuid
        entity_id = self._get_current_char_entity_id()
        if not entity_id or not self.screenplay:
            QMessageBox.information(self, "No Character",
                                    "Select a character and ensure identity blocks are created first.")
            return
        vid = str(_uuid.uuid4())[:8]
        variant_data = {
            "variant_id": vid,
            "label": "",
            "description": "",
            "identity_block": "",
            "reference_image_prompt": "",
            "image_path": "",
            "created_at": "",
        }
        self.screenplay.add_wardrobe_variant(entity_id, variant_data)
        self._add_wardrobe_variant_widget(variant_data, entity_id)

    # ── Character Identity Block handlers ─────────────────────────────

    def _on_generate_char_identity_block(self):
        """Generate an identity block from the full physical appearance description (traits + wardrobe)."""
        if not self.ai_generator or not self.screenplay:
            QMessageBox.warning(self, "Not Available", "AI Generator not available. Check settings.")
            return
        row = self.char_details_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Character", "Please select a character first.")
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters) or not isinstance(characters[row], dict):
            return
        char = characters[row]
        char_name = char.get("name", "Unknown Character")
        full_text = self.char_details_physical_edit.toPlainText().strip()

        if not full_text:
            QMessageBox.warning(self, "No Physical Appearance",
                                "Physical Appearance must be defined first.")
            return

        entity_id = self._get_current_char_entity_id()
        scene_context = ""
        if self.current_scene:
            scene_context = getattr(self.current_scene, "description", "") or ""

        progress = QProgressDialog(
            f"Generating identity block for {char_name}...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setWindowTitle("Generating Identity Block")
        progress.setCancelButton(None)
        progress.show()
        progress.raise_()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            ib_text = self.ai_generator.generate_identity_block_from_notes(
                entity_name=char_name,
                entity_type="character",
                user_notes=full_text,
                scene_context=scene_context,
                screenplay=self.screenplay,
                include_physical_traits=True,
            )
            if ib_text and ib_text.strip():
                self._loading_char_selection = True
                self.char_identity_block_edit.setPlainText(ib_text.strip())
                self._loading_char_selection = False
                if entity_id:
                    self.screenplay.update_identity_block_metadata(
                        entity_id, identity_block=ib_text.strip(), status="generating")
                self._update_identity_block_buttons()
                progress.close()
                self._show_status(f"Identity block generated for '{char_name}'", 4000)
            else:
                progress.close()
                QMessageBox.warning(self, "Generation Failed", "AI returned an empty result. Please try again.")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Generation Error",
                                 f"Failed to generate identity block:\n\n{str(e)}")

    def _on_approve_char_identity_block(self):
        """Approve the identity block and generate the reference image prompt."""
        if not self.ai_generator or not self.screenplay:
            QMessageBox.warning(self, "Not Available", "AI Generator not available.")
            return
        row = self.char_details_list.currentRow()
        if row < 0:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {})
        characters = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
        if row >= len(characters) or not isinstance(characters[row], dict):
            return
        char = characters[row]
        char_name = char.get("name", "Unknown Character")
        ib_text = self.char_identity_block_edit.toPlainText().strip()
        if not ib_text:
            QMessageBox.warning(self, "No Identity Block", "Generate an identity block first.")
            return

        entity_id = self._get_current_char_entity_id()

        progress = QProgressDialog(
            f"Approving and generating reference prompt for {char_name}...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setWindowTitle("Approving Identity Block")
        progress.setCancelButton(None)
        progress.show()
        progress.raise_()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            metadata = None
            if entity_id:
                metadata = self.screenplay.get_identity_block_metadata_by_id(entity_id)
            ref_prompt = self.ai_generator.generate_reference_image_prompt(
                entity_name=char_name,
                entity_type="character",
                identity_block=ib_text,
                metadata=metadata,
            )
            if ref_prompt and ref_prompt.strip():
                self._loading_char_selection = True
                self.char_ref_prompt_edit.setPlainText(ref_prompt.strip())
                self._loading_char_selection = False
                if entity_id:
                    self.screenplay.update_identity_block_metadata(
                        entity_id,
                        identity_block=ib_text,
                        reference_image_prompt=ref_prompt.strip(),
                        status="approved",
                    )
                self._update_identity_block_buttons()
                progress.close()
                self._show_status(f"Identity block approved for '{char_name}'", 4000)
            else:
                progress.close()
                QMessageBox.warning(self, "Generation Failed", "AI returned an empty prompt.")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Approval Error",
                                 f"Failed to generate reference image prompt:\n\n{str(e)}")

    def _on_copy_char_ref_prompt(self):
        """Copy the reference image prompt to clipboard."""
        prompt = self.char_ref_prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "No Prompt", "No reference image prompt to copy.")
            return
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(prompt)
        self._show_status("Reference image prompt copied to clipboard")

    def _on_upload_char_ref_image(self):
        """Upload a reference image for the current character."""
        entity_id = self._get_current_char_entity_id()
        if not entity_id or not self.screenplay:
            return
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        self.screenplay.update_identity_block_metadata(entity_id, image_path=path)
        self.char_ref_thumb.setImageFromPath(path)

    def _on_clear_char_ref_image(self):
        """Clear the reference image for the current character."""
        entity_id = self._get_current_char_entity_id()
        if not entity_id or not self.screenplay:
            return
        self.screenplay.update_identity_block_metadata(entity_id, image_path="")
        self.char_ref_thumb.clearImage()
    
    def _on_regenerate_char_detail(self, regenerate_type: str):
        """Regenerate outline/growth_arc/both for the currently selected character."""
        row = self.char_details_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Character", "Please select a character first.")
            return
        self._regenerate_character_field(row, regenerate_type)
    
    def _on_regenerate_all_physical_appearances(self):
        """Regenerate physical appearance for all characters that have none."""
        if not self.ai_generator or not self.screenplay:
            QMessageBox.warning(self, "Not Available", "AI generator or screenplay not available.")
            return
        story_outline = getattr(self.screenplay, 'story_outline', {}) or {}
        characters = story_outline.get("characters", []) or []
        if not characters:
            QMessageBox.warning(self, "No Characters", "No characters to regenerate.")
            return
        indices_needing = []
        for i, c in enumerate(characters):
            if isinstance(c, dict) and not str(c.get("physical_appearance", "") or "").strip():
                indices_needing.append(i)
        if not indices_needing:
            QMessageBox.information(self, "Already Complete", "All characters already have physical appearance.")
            return
        if self.batch_physical_thread and self.batch_physical_thread.isRunning():
            QMessageBox.warning(self, "Busy", "A batch regeneration is already in progress.")
            return
        progress = QProgressDialog(
            f"Regenerating physical appearance for {len(indices_needing)} character(s)...",
            None, 0, len(indices_needing), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.show()
        self.batch_physical_thread = BatchPhysicalAppearanceThread(
            self.ai_generator, self.screenplay, indices_needing
        )
        self.batch_physical_thread.progress.connect(
            lambda idx, done, total, result: self._on_batch_physical_progress(idx, done, total, result, progress)
        )
        self.batch_physical_thread.finished_all.connect(
            lambda: self._on_batch_physical_finished(progress)
        )
        self.batch_physical_thread.error.connect(
            lambda err: self._on_batch_physical_error(err, progress)
        )
        self.batch_physical_thread.start()
    
    def _on_batch_physical_progress(self, index: int, done: int, total: int, result: dict, progress: QProgressDialog):
        """Handle progress from batch physical appearance regeneration."""
        if progress:
            progress.setValue(done)
            progress.setLabelText(f"Regenerating physical appearance ({done} of {total})...")
        if not self.screenplay:
            return
        story_outline = getattr(self.screenplay, 'story_outline', {}) or {}
        characters = story_outline.get("characters", []) or []
        if 0 <= index < len(characters) and "physical_appearance" in result and result.get("physical_appearance") is not None:
            characters[index]["physical_appearance"] = result["physical_appearance"]
        if hasattr(self, 'char_details_list') and self.char_details_list.currentRow() == index:
            if "physical_appearance" in result and result.get("physical_appearance") is not None:
                wardrobe_sfx = getattr(self, '_first_scene_wardrobe_suffix', "")
                self.char_details_physical_edit.setPlainText(result["physical_appearance"] + wardrobe_sfx)
        self.update_character_details()
    
    def _on_batch_physical_finished(self, progress: QProgressDialog):
        """Handle batch physical appearance completion."""
        if progress:
            progress.close()
        self.update_character_details()
        self._show_status("Physical appearances generated for all characters", 4000)
    
    def _on_batch_physical_error(self, error_message: str, progress: QProgressDialog):
        """Handle batch physical appearance error."""
        if progress:
            progress.close()
        QMessageBox.critical(self, "Error", f"Failed to regenerate physical appearance:\n{error_message}")
    
    def on_delete_char_detail_clicked(self):
        """Delete the currently selected character."""
        row = self.char_details_list.currentRow()
        if row < 0:
            return
        self.on_delete_character_clicked(row)
    
    def on_add_character_clicked(self):
        """Add a new character."""
        if not self.screenplay:
            return
        
        # Ensure story_outline exists
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            story_outline = {}
            self.screenplay.story_outline = story_outline
        
        if "characters" not in story_outline:
            story_outline["characters"] = []
        
        story_outline["characters"].append({
            "name": "New Character",
            "role": "main",
            "species": "Human",
            "outline": "",
            "growth_arc": "",
            "physical_appearance": ""
        })
        self._sync_character_registry()
        
        # Refresh list and select the new (last) character so it shows in the editor
        self.update_character_details()
        if hasattr(self, 'char_details_list') and self.char_details_list.count() > 0:
            last_row = self.char_details_list.count() - 1
            self.char_details_list.setCurrentRow(last_row)
            self._load_char_into_editor(last_row)
            self._char_details_last_row = last_row
    
    def on_delete_character_clicked(self, index: int):
        """Delete a character."""
        if not self.screenplay:
            return
        
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            return
        
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list) or index < 0 or index >= len(characters):
            return
        
        # Confirm deletion
        char_name = characters[index].get("name", "this character")
        reply = QMessageBox.question(
            self, "Delete Character",
            f"Are you sure you want to delete '{char_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            characters.pop(index)
            self._sync_character_registry()
            self.update_character_details()
    
    def _regenerate_character_field(self, index: int, regenerate_type: str):
        """Internal method to regenerate character details."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        if not self.screenplay:
            return
        
        story_outline = getattr(self.screenplay, 'story_outline', {})
        if not isinstance(story_outline, dict):
            return
        
        characters = story_outline.get("characters", [])
        if not isinstance(characters, list) or index < 0 or index >= len(characters):
            return
        
        char = characters[index]
        char_name = str(char.get("name", "Unnamed Character")).strip()
        
        # Get story context
        premise = getattr(self.screenplay, 'premise', '')
        title = getattr(self.screenplay, 'title', '')
        genres = getattr(self.screenplay, 'genres', [])
        atmosphere = getattr(self.screenplay, 'atmosphere', '')
        main_storyline = story_outline.get("main_storyline", "")
        
        # Clean up any existing thread
        if self.char_regeneration_thread and self.char_regeneration_thread.isRunning():
            self.char_regeneration_thread.terminate()
            self.char_regeneration_thread.wait()
        
        # Show progress dialog
        progress = QProgressDialog(f"Regenerating character details for {char_name}...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        
        # Get all existing characters (excluding the one being regenerated) to avoid role duplication
        other_characters = [c for i, c in enumerate(characters) if i != index and isinstance(c, dict)]
        
        # Pass character outline when regenerating physical_appearance (for age extraction)
        char_outline = str(char.get("outline", "") or "").strip() if regenerate_type == "physical_appearance" else ""
        
        # Create and start generation thread
        self.char_regeneration_thread = CharacterRegenerationThread(
            self.ai_generator, premise, genres, atmosphere, title,
            main_storyline, char_name, regenerate_type, existing_characters=other_characters,
            character_outline=char_outline
        )
        self.char_regeneration_thread.set_character_index(index)
        self.char_regeneration_thread.finished.connect(
            lambda idx, result: self.on_character_regenerated(idx, result, progress)
        )
        self.char_regeneration_thread.error.connect(
            lambda error: self.on_character_regeneration_error(error, progress)
        )
        self.char_regeneration_thread.start()
    
    def on_character_regenerated(self, index: int, result: dict, progress: QProgressDialog):
        """Handle successful character regeneration."""
        try:
            if progress:
                progress.close()
            
            if not self.screenplay:
                return
            
            story_outline = getattr(self.screenplay, 'story_outline', {})
            if not isinstance(story_outline, dict):
                return
            
            characters = story_outline.get("characters", [])
            if not isinstance(characters, list) or index < 0 or index >= len(characters):
                return
            
            # Update character data
            if "outline" in result and result.get("outline"):
                characters[index]["outline"] = result["outline"]
            if "growth_arc" in result and result.get("growth_arc"):
                characters[index]["growth_arc"] = result["growth_arc"]
            if "physical_appearance" in result and result.get("physical_appearance") is not None:
                characters[index]["physical_appearance"] = result["physical_appearance"]
            if "name" in result and result.get("name"):
                characters[index]["name"] = result["name"]
            
            # If this character is currently selected, update the single editor
            if hasattr(self, 'char_details_list') and self.char_details_list.currentRow() == index:
                try:
                    if "outline" in result and result.get("outline"):
                        self.char_details_outline_edit.setPlainText(result["outline"])
                    if "growth_arc" in result and result.get("growth_arc"):
                        self.char_details_growth_edit.setPlainText(result["growth_arc"])
                    if "physical_appearance" in result and result.get("physical_appearance") is not None:
                        wardrobe_sfx = getattr(self, '_first_scene_wardrobe_suffix', "")
                        self.char_details_physical_edit.setPlainText(result["physical_appearance"] + wardrobe_sfx)
                    if "name" in result and result.get("name"):
                        self.char_details_name_edit.setText(result["name"])
                        item = self.char_details_list.item(index)
                        if item:
                            item.setText(result["name"])
                except Exception as e:
                    print(f"Error updating character editor: {e}")
                    self.update_character_details()
        except Exception as e:
            import traceback
            print(f"Error in on_character_regenerated: {e}")
            traceback.print_exc()
            if progress:
                progress.close()
            QMessageBox.critical(self, "Error", f"Failed to update character details:\n{str(e)}")
    
    def on_character_regeneration_error(self, error_message: str, progress: QProgressDialog):
        """Handle character regeneration error."""
        try:
            if progress:
                progress.close()
            QMessageBox.critical(self, "Generation Failed", f"Failed to regenerate character details:\n{error_message}")
        except Exception as e:
            import traceback
            print(f"Error in on_character_regeneration_error: {e}")
            traceback.print_exc()
    
    def on_generate_framework_clicked(self):
        """Handle generate framework button click."""
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        # This should be called from main window with premise, title, etc.
        # For now, just emit a signal
        QMessageBox.information(self, "Generate Framework", 
            "Please use 'Generate Story Framework' from the main menu or toolbar.")
    
    def on_generate_storyboard_clicked(self):
        """Handle generate storyboard button click."""
        if not self.current_scene:
            QMessageBox.warning(self, "No Scene Selected", "Please select a scene first.")
            return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Available", "AI generator is not configured.")
            return
        
        if not self.screenplay:
            QMessageBox.warning(self, "No Screenplay", "No screenplay loaded.")
            return
        
        # Show progress dialog
        progress = QProgressDialog("Generating storyboard for scene...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        
        # Create and start generation thread
        self.storyboard_thread = SceneStoryboardGenerationThread(
            self.ai_generator, self.current_scene, self.screenplay
        )
        self.storyboard_thread.finished.connect(
            lambda scene: self.on_storyboard_generated(scene, progress)
        )
        self.storyboard_thread.error.connect(
            lambda error: self.on_storyboard_error(error, progress)
        )
        self.storyboard_thread.start()
    
    def on_storyboard_generated(self, scene: StoryScene, progress: QProgressDialog):
        """Handle storyboard generation completion."""
        progress.close()
        self.load_scene_data(scene)
        self.update_tree()
        # Refresh storyboard items display
        if hasattr(self, 'load_storyboard_items'):
            self.load_storyboard_items()
        self._show_status(f"Storyboard generated for {scene.title}", 4000)

    def validate_storyboard_for_export(self) -> bool:
        """Run Video Prompt Builder validation on all storyboard items.

        Shows a warning with specific errors and returns False if any item
        with image assignments fails validation.
        """
        if not self.current_scene:
            return True
        from core.video_prompt_builder import validate_for_generation
        all_errors: list = []
        for item in self.current_scene.storyboard_items:
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
                label = f"Item #{item.sequence_number}"
                all_errors.extend(f"{label}: {e}" for e in errors)
        if all_errors:
            QMessageBox.warning(
                self, "Validation Errors",
                "Some storyboard items have image-mapping issues:\n\n"
                + "\n".join(all_errors)
                + "\n\nPlease fix these before exporting for video generation.")
            return False
        return True
    
    def on_storyboard_error(self, error: str, progress: QProgressDialog):
        """Handle storyboard generation error."""
        progress.close()
        QMessageBox.critical(self, "Error", f"Failed to generate storyboard: {error}")
    
    def on_storyboard_item_double_clicked(self, item: QListWidgetItem):
        """Handle storyboard item double click."""
        storyboard_item = item.data(Qt.ItemDataRole.UserRole)
        if storyboard_item:
            self.storyboard_item_edit_requested.emit(storyboard_item)
    
    def on_storyboard_selection_changed(self):
        """Handle storyboard item selection change."""
        has_selection = len(self.storyboard_list.selectedItems()) > 0
        has_items = self.storyboard_list.count() > 0
        self.delete_storyboard_item_btn.setEnabled(has_selection and self.current_scene is not None)
        if hasattr(self, 'select_all_storyboard_btn'):
            self.select_all_storyboard_btn.setEnabled(has_items and self.current_scene is not None)
        
        # Enable regenerate button if scene has items
        
        # Enable move buttons only if one item is selected
        if has_selection and len(self.storyboard_list.selectedItems()) == 1:
            current_row = self.storyboard_list.currentRow()
            self.move_up_btn.setEnabled(current_row > 0)
            self.move_down_btn.setEnabled(current_row < self.storyboard_list.count() - 1)
        else:
            self.move_up_btn.setEnabled(False)
            self.move_down_btn.setEnabled(False)
    
    def on_storyboard_context_menu(self, position):
        """Show context menu for storyboard items."""
        item = self.storyboard_list.itemAt(position)
        menu = QMenu(self)
        
        if item:
            edit_action = QAction("Edit Item", self)
            edit_action.triggered.connect(lambda: self.on_storyboard_item_double_clicked(item))
            menu.addAction(edit_action)
            
            menu.addSeparator()
            
            select_all_action = QAction("Select All", self)
            select_all_action.triggered.connect(self.on_select_all_storyboard_items)
            menu.addAction(select_all_action)
            
            menu.addSeparator()
            
            delete_action = QAction("Delete Item", self)
            delete_action.triggered.connect(lambda: self.on_delete_storyboard_item_clicked())
            menu.addAction(delete_action)
            
            menu.addSeparator()
            
            move_up_action = QAction("Move Up", self)
            move_up_action.triggered.connect(self.on_move_storyboard_item_up)
            move_up_action.setEnabled(self.storyboard_list.currentRow() > 0)
            menu.addAction(move_up_action)
            
            move_down_action = QAction("Move Down", self)
            move_down_action.triggered.connect(self.on_move_storyboard_item_down)
            move_down_action.setEnabled(self.storyboard_list.currentRow() < self.storyboard_list.count() - 1)
            menu.addAction(move_down_action)
        else:
            add_action = QAction("Add Item", self)
            add_action.triggered.connect(self.on_add_storyboard_item_clicked)
            menu.addAction(add_action)
        
        menu.exec(self.storyboard_list.mapToGlobal(position))
    
    def on_add_storyboard_item_clicked(self):
        """Add a new storyboard item."""
        if not self.current_scene:
            QMessageBox.warning(self, "No Scene", "Please select a scene first.")
            return
        
        # Create a new storyboard item
        import uuid
        from datetime import datetime
        from core.screenplay_engine import StoryboardItem, SceneType
        
        # Determine sequence number (next available)
        max_seq = max([item.sequence_number for item in self.current_scene.storyboard_items], default=0)
        new_seq = max_seq + 1
        
        new_item = StoryboardItem(
            item_id=str(uuid.uuid4()),
            sequence_number=new_seq,
            duration=5,  # Default to 5 seconds
            storyline="",
            image_prompt="",
            prompt="",
            visual_description="",
            dialogue="",
            scene_type=SceneType.ACTION,
            camera_notes="",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # Add to scene
        self.current_scene.add_storyboard_item(new_item)
        
        # Refresh display
        self.load_storyboard_items()
        
        # Select the new item
        for i in range(self.storyboard_list.count()):
            list_item = self.storyboard_list.item(i)
            if list_item.data(Qt.ItemDataRole.UserRole) == new_item:
                self.storyboard_list.setCurrentItem(list_item)
                break
        
        # Open editor for the new item
        self.storyboard_item_edit_requested.emit(new_item)
    
    def on_delete_storyboard_item_clicked(self):
        """Delete selected storyboard item."""
        try:
            if not self.current_scene:
                return
            
            selected_items = self.storyboard_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(self, "No Selection", "Please select an item to delete.")
                return
            
            # Confirm deletion
            reply = QMessageBox.question(
                self, "Delete Item",
                f"Delete {len(selected_items)} storyboard item(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Delete items from scene
                items_to_delete = []
                for list_item in selected_items:
                    storyboard_item = list_item.data(Qt.ItemDataRole.UserRole)
                    if storyboard_item and storyboard_item in self.current_scene.storyboard_items:
                        items_to_delete.append(storyboard_item)
                
                # Remove items from scene
                for item in items_to_delete:
                    if item in self.current_scene.storyboard_items:
                        self.current_scene.storyboard_items.remove(item)
                
                # Renumber sequence numbers
                if self.current_scene.storyboard_items:
                    self.renumber_storyboard_items()
                
                # Refresh display
                self.load_storyboard_items()
                
                # Duration editing removed with right panel
                # Duration can be set via scene framework editor if needed
        except Exception as e:
            import traceback
            error_msg = f"Error deleting storyboard item: {str(e)}\n\n{traceback.format_exc()}"
            QMessageBox.critical(self, "Error", error_msg)
            print(error_msg)
    
    def on_select_all_storyboard_items(self):
        """Select all storyboard items."""
        if not self.current_scene or self.storyboard_list.count() == 0:
            return
        
        # Select all items by iterating through them
        self.storyboard_list.selectAll()
        
        # Ensure all items are actually selected (sometimes selectAll() doesn't work with drag-drop enabled)
        for i in range(self.storyboard_list.count()):
            item = self.storyboard_list.item(i)
            if item:
                item.setSelected(True)
    
    def on_move_storyboard_item_up(self):
        """Move selected storyboard item up."""
        current_row = self.storyboard_list.currentRow()
        if current_row <= 0 or not self.current_scene:
            return
        
        # Get the item
        list_item = self.storyboard_list.item(current_row)
        storyboard_item = list_item.data(Qt.ItemDataRole.UserRole)
        if not storyboard_item:
            return
        
        # Swap in the scene's list
        items = self.current_scene.storyboard_items
        item_index = items.index(storyboard_item)
        if item_index > 0:
            items[item_index], items[item_index - 1] = items[item_index - 1], items[item_index]
            
            # Renumber sequence numbers
            self.renumber_storyboard_items()
            
            # Refresh display
            self.load_storyboard_items()
            
            # Reselect the moved item
            self.storyboard_list.setCurrentRow(current_row - 1)
    
    def on_move_storyboard_item_down(self):
        """Move selected storyboard item down."""
        current_row = self.storyboard_list.currentRow()
        if current_row >= self.storyboard_list.count() - 1 or not self.current_scene:
            return
        
        # Get the item
        list_item = self.storyboard_list.item(current_row)
        storyboard_item = list_item.data(Qt.ItemDataRole.UserRole)
        if not storyboard_item:
            return
        
        # Swap in the scene's list
        items = self.current_scene.storyboard_items
        item_index = items.index(storyboard_item)
        if item_index < len(items) - 1:
            items[item_index], items[item_index + 1] = items[item_index + 1], items[item_index]
            
            # Renumber sequence numbers
            self.renumber_storyboard_items()
            
            # Refresh display
            self.load_storyboard_items()
            
            # Reselect the moved item
            self.storyboard_list.setCurrentRow(current_row + 1)
    
    def renumber_storyboard_items(self):
        """Renumber storyboard items to maintain sequential order."""
        if not self.current_scene:
            return
        
        for i, item in enumerate(self.current_scene.storyboard_items, start=1):
            item.sequence_number = i
            from datetime import datetime
            item.updated_at = datetime.now().isoformat()
    
    def on_storyboard_items_reordered(self, parent, start, end, destination, row):
        """Handle storyboard items being reordered via drag and drop."""
        if not self.current_scene:
            return
        
        # Rebuild the scene's storyboard_items list based on list widget order
        new_items = []
        for i in range(self.storyboard_list.count()):
            list_item = self.storyboard_list.item(i)
            storyboard_item = list_item.data(Qt.ItemDataRole.UserRole)
            if storyboard_item:
                new_items.append(storyboard_item)
        
        # Update the scene's list
        self.current_scene.storyboard_items = new_items
        
        # Renumber sequence numbers
        self.renumber_storyboard_items()
        
        # Refresh display
        self.load_storyboard_items()
    
    def load_storyboard_items(self):
        """Load storyboard items into the list widget."""
        if not self.current_scene:
            self.storyboard_list.clear()
            return
        
        self.storyboard_list.clear()
        for item in self.current_scene.storyboard_items:
            # Use storyline text, fallback to prompt if storyline is empty
            text_source = item.storyline if item.storyline else item.prompt
            # Shorten to first part of text (e.g., first 60 characters)
            text_preview = text_source[:60] + "..." if len(text_source) > 60 else text_source
            
            # Validation status indicator
            validation_status = getattr(item, "validation_status", "")
            if validation_status == "validation_failed":
                prefix = "[FAILED] "
            elif validation_status == "passed":
                prefix = ""
            else:
                prefix = ""
            
            # Paragraph index indicator for strict 1:1 mapping
            para_idx = getattr(item, "source_paragraph_index", -1)
            para_label = f" [P{para_idx + 1}]" if para_idx >= 0 else ""
            
            # Cluster badge for multi-shot items
            cluster_label = ""
            cluster_id = getattr(item, "cluster_id", None)
            shot_num = getattr(item, "shot_number_in_cluster", None)
            if cluster_id and shot_num is not None:
                # Find total shots in this cluster
                total_in_cluster = 1
                for cl in getattr(self.current_scene, "multishot_clusters", []):
                    if cl.cluster_id == cluster_id:
                        total_in_cluster = len(cl.item_ids)
                        break
                cluster_short = cluster_id[-4:] if len(cluster_id) > 4 else cluster_id
                cluster_label = f" [Cluster {cluster_short}: Shot {shot_num}/{total_in_cluster}]"
            
            list_item = QListWidgetItem(
                f"{prefix}Item {item.sequence_number}{para_label}{cluster_label}: {text_preview}"
            )
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            
            # Color validation failures red
            if validation_status == "validation_failed":
                list_item.setForeground(QColor(220, 50, 50))
                errors = getattr(item, "validation_errors", [])
                if errors:
                    list_item.setToolTip("Validation errors:\n" + "\n".join(errors))
            
            # Cluster duration warning tooltip
            if cluster_id:
                for cl in getattr(self.current_scene, "multishot_clusters", []):
                    if cl.cluster_id == cluster_id:
                        ss = getattr(self.screenplay, "story_settings", None) if self.screenplay else None
                        max_dur = ss.get("max_generation_duration_seconds", 10) if ss else 10
                        tip = f"Cluster duration: {cl.total_duration}s"
                        if cl.total_duration > max_dur:
                            tip += f" (exceeds max {max_dur}s)"
                        existing = list_item.toolTip()
                        if existing:
                            tip = existing + "\n" + tip
                        list_item.setToolTip(tip)
                        break
            
            self.storyboard_list.addItem(list_item)
        
        # Enable/disable add button based on scene selection
        if hasattr(self, 'add_storyboard_item_btn'):
            self.add_storyboard_item_btn.setEnabled(self.current_scene is not None)
        
        # Enable/disable select all button based on items
        if hasattr(self, 'select_all_storyboard_btn'):
            has_items = self.storyboard_list.count() > 0
            self.select_all_storyboard_btn.setEnabled(has_items and self.current_scene is not None)
        
        self._sync_multishot_toggle_state()
    
    def _sync_multishot_toggle_state(self):
        """Enable/disable the multi-shot toggle based on per-project story settings."""
        if not hasattr(self, 'multishot_toggle'):
            return
        ss = getattr(self.screenplay, "story_settings", None) if self.screenplay else None
        supported = ss.get("supports_multishot", False) if ss else False
        self.multishot_toggle.setEnabled(supported)
        if not supported:
            self.multishot_toggle.setChecked(False)
            self.multishot_toggle.setToolTip(
                "Enable 'Supports Multi-Shot' in the Story Settings tab to use this feature."
            )
        else:
            self.multishot_toggle.setToolTip(
                "When enabled, consecutive storyboard items sharing the same environment, "
                "characters, and vehicles are grouped into unified multi-shot sequences.\n"
                "Configure in Story Settings tab."
            )

    def _on_multishot_toggled(self, checked: bool):
        """Apply or revert multi-shot clustering when the toggle is changed."""
        if not self.current_scene or not self.screenplay:
            return

        from config import config
        ms = config.get_model_settings()

        if checked:
            from core.multishot_engine import apply_multishot_clustering
            try:
                apply_multishot_clustering(self.current_scene, self.screenplay, ms)  # screenplay.story_settings used internally
                cluster_count = sum(
                    1 for c in self.current_scene.multishot_clusters
                    if len(c.item_ids) > 1
                )
                self._show_status(
                    f"Multi-shot clustering applied: {cluster_count} cluster(s) formed", 4000
                )
            except Exception as e:
                self.current_scene.generation_strategy = "single_shot"
                self.current_scene.multishot_clusters = []
                for item in self.current_scene.storyboard_items:
                    item.cluster_id = None
                    item.shot_number_in_cluster = None
                QMessageBox.warning(
                    self, "Clustering Failed",
                    f"Multi-shot clustering failed, reverting to single-shot:\n{e}"
                )
                self.multishot_toggle.blockSignals(True)
                self.multishot_toggle.setChecked(False)
                self.multishot_toggle.blockSignals(False)
        else:
            self.current_scene.generation_strategy = "single_shot"
            self.current_scene.multishot_clusters = []
            for item in self.current_scene.storyboard_items:
                item.cluster_id = None
                item.shot_number_in_cluster = None
            self._show_status("Multi-shot clustering removed", 4000)

        self.load_storyboard_items()
        self._update_cluster_preview()
        self.data_changed.emit()

    def _update_cluster_preview(self):
        """Show a shot-breakdown preview when a clustered storyboard item is selected."""
        if not hasattr(self, 'cluster_preview_group'):
            return
        selected = self.storyboard_list.selectedItems()
        if not selected or not self.current_scene:
            self.cluster_preview_group.setVisible(False)
            return

        item = selected[0].data(Qt.ItemDataRole.UserRole)
        if not item or not getattr(item, 'cluster_id', None):
            self.cluster_preview_group.setVisible(False)
            return

        cluster = None
        for cl in getattr(self.current_scene, 'multishot_clusters', []):
            if cl.cluster_id == item.cluster_id:
                cluster = cl
                break
        if not cluster or len(cluster.item_ids) <= 1:
            self.cluster_preview_group.setVisible(False)
            return

        ss = getattr(self.screenplay, "story_settings", None) if self.screenplay else None
        max_dur = ss.get("max_generation_duration_seconds", 10) if ss else 10

        lines = []
        lines.append(f"<b>Cluster:</b> {cluster.cluster_id}")
        lines.append(f"<b>Total Duration:</b> {cluster.total_duration}s")
        if cluster.total_duration > max_dur:
            lines.append(
                f"<span style='color:red;'><b>Warning:</b> cluster duration "
                f"({cluster.total_duration}s) exceeds max ({max_dur}s)</span>"
            )
        lines.append("")
        for idx, shot in enumerate(cluster.shots):
            dur = shot.get("duration", 5)
            desc = shot.get("description", "")[:80]
            lines.append(f"<b>Shot {shot.get('shot_number', idx + 1)}</b> ({dur}s): {desc}")
            if idx < len(cluster.transitions):
                t = cluster.transitions[idx]
                label = t.transition_type.replace("_", " ").title()
                lines.append(f"  <i>Transition: {label}</i>")

        self.cluster_preview_text.setHtml("<br>".join(lines))
        self.cluster_preview_group.setVisible(True)

    # Timeline visualization method removed
    
    def _get_all_entities_for_insert(self) -> dict:
        """Collect entities from character registry, identity blocks, and story outline for Add Entity dialog."""
        result = {
            "character": [],
            "environment": [],
            "vehicle": [],
            "object": []
        }
        if not self.screenplay:
            return result
        
        seen = set()
        def add_unique(etype: str, name: str) -> None:
            if not name or not isinstance(name, str):
                return
            key = (etype, (name or "").strip())
            if key in seen:
                return
            seen.add(key)
            result[etype].append((name or "").strip())
        
        # From identity_block_metadata (wizard + extracted)
        meta = getattr(self.screenplay, "identity_block_metadata", None) or {}
        for _eid, m in meta.items():
            etype = (m.get("type") or "").lower()
            name = (m.get("name") or "").strip()
            if etype in result and name:
                add_unique(etype, name)
        
        # Character registry (main characters from wizard) - ensure we have them even if not in metadata yet
        registry = getattr(self.screenplay, "character_registry", None) or []
        for name in registry:
            if name:
                add_unique("character", name)
        
        # Story outline locations (environments from wizard)
        outline = getattr(self.screenplay, "story_outline", None) or {}
        if isinstance(outline, dict):
            for loc in outline.get("locations", []) or []:
                if loc and isinstance(loc, str):
                    add_unique("environment", loc.strip())
        
        return result
    
    def _on_add_entity_clicked(self):
        """Open Add Entity dialog and insert selected entity at cursor with markup."""
        entities = self._get_all_entities_for_insert()
        total = sum(len(v) for v in entities.values())
        if total == 0:
            QMessageBox.information(
                self,
                "No Entities",
                "No entities available yet. Entities come from:\n"
                "• Main characters (wizard Step 1)\n"
                "• Story outline locations\n"
                "• Identity blocks (extracted from scene content or added manually)"
            )
            return
        
        dialog = AddEntityDialog(entities, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        name = dialog.selected_name
        etype = dialog.selected_type
        if not name or not etype:
            return
        
        # Apply markup per entity type
        if etype == "character":
            insert_text = name.upper()
        elif etype == "environment":
            insert_text = f"_{name}_"
        elif etype == "vehicle":
            insert_text = f"{{{name}}}"
        elif etype == "object":
            insert_text = f"[{name}]"
        else:
            insert_text = name
        
        cursor = self.scene_description_edit.textCursor()
        cursor.insertText(insert_text)
    
    def on_save_scene_clicked(self):
        """Handle save scene button click."""
        if not self.current_scene:
            QMessageBox.warning(self, "No Scene", "No scene selected to save.")
            return
        
        # Update scene description from editor - always save when user clicks save
        new_description = self.scene_description_edit.toPlainText().strip()
        self.current_scene.description = new_description
        
        # Duration editing removed with right panel - estimated_duration remains unchanged
        # (Duration can still be set via scene framework editor if needed)
        
        # Save wardrobe selector state to scene
        if hasattr(self, 'wardrobe_selectors') and self.screenplay and self.current_scene:
            if not hasattr(self.current_scene, 'character_wardrobe_selector'):
                self.current_scene.character_wardrobe_selector = {}
            for entity_id, combo in self.wardrobe_selectors.items():
                self.current_scene.character_wardrobe_selector[entity_id] = combo.currentData() or ""
        
        # Save generated content to metadata
        generated_content = self.scene_content_display.toPlainText().strip()
        if generated_content:
            # Remove paragraph numbers before saving
            generated_content = self._remove_paragraph_numbers(generated_content)
            # Ensure metadata dict exists
            if self.current_scene.metadata is None:
                self.current_scene.metadata = {}
            # Save the generated content (without numbers)
            self.current_scene.metadata["generated_content"] = generated_content
        elif self.current_scene.metadata and "generated_content" in self.current_scene.metadata:
            # If content is cleared, remove it from metadata
            del self.current_scene.metadata["generated_content"]
        
        from datetime import datetime
        self.current_scene.updated_at = datetime.now().isoformat()
        
        # Refresh display to show updated description
        self.update_tree()
        # Timeline visualization removed - method no longer exists
        # self.update_timeline_visualization()
        
        # Reload scene data to ensure UI is in sync
        self.load_scene_data(self.current_scene)
        
        if self._is_visual_art_mode():
            # Visual Art mode: create environment directly from scene description (no entity extraction)
            self._create_visual_art_environment()
            status_msg = f"Scene '{self.current_scene.title}' approved — environment created"
        else:
            # Standard mode: extract entities from generated content
            generated_content = self.current_scene.metadata.get("generated_content", "") if self.current_scene.metadata else ""
            if generated_content:
                progress = QProgressDialog(
                    "Extracting entities from scene content...",
                    None, 0, 0, self
                )
                progress.setWindowTitle("Extracting Entities")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setCancelButton(None)
                progress.setMinimumDuration(0)
                progress.setMinimumWidth(350)
                progress.show()
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                try:
                    self.extract_entities_from_scene_content(generated_content, progress=progress)
                finally:
                    progress.close()
            status_msg = f"Scene '{self.current_scene.title}' approved — entities extracted"
        
        # Refresh character tab to show any newly added minor characters
        self.update_character_details()
        
        # Update wardrobe variant continuity tracking
        if self.screenplay and self.current_scene:
            variant_ids = getattr(self.current_scene, 'character_wardrobe_variant_ids', {}) or {}
            if not hasattr(self.screenplay, 'character_last_wardrobe_variant'):
                self.screenplay.character_last_wardrobe_variant = {}
            for eid, vid in variant_ids.items():
                self.screenplay.character_last_wardrobe_variant[eid] = vid

        # Notify main window to persist to disk
        self.data_changed.emit()
        
        self._show_status(status_msg, 4000)
    
    def on_reextract_entities_clicked(self):
        """Clear current entities for this scene and re-extract from scene content (for testing)."""
        if not self.current_scene:
            QMessageBox.warning(self, "No Scene", "Please select a scene first.")
            return
        content = self.scene_content_display.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "No Content", "No scene content to extract from. Generate content first.")
            return
        if not self.screenplay or not self.ai_generator:
            QMessageBox.warning(self, "Not Ready", "Screenplay or AI not available.")
            return
        content = self._remove_paragraph_numbers(content)
        removed = self.screenplay.remove_identity_blocks_for_scene(self.current_scene.scene_id)
        progress = QProgressDialog(
            "Re-extracting entities from scene content...",
            None, 0, 0, self
        )
        progress.setWindowTitle("Extracting Entities")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(350)
        progress.show()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            self.extract_entities_from_scene_content(content, progress=progress)
        finally:
            progress.close()
        self.update_character_details()
        self._show_status(f"Cleared {removed} entity block(s) and re-extracted", 4000)

    def on_generate_scene_content_clicked(self):
        """Handle generate scene content button click."""
        if not self.current_scene:
            QMessageBox.warning(self, "No Scene", "Please select a scene first.")
            return
        
        if not self.ai_generator:
            QMessageBox.warning(self, "AI Not Configured", "Please configure AI settings first.")
            return
        
        # Get scene description (use what's in the editor or the scene's description)
        scene_description = self.scene_description_edit.toPlainText().strip()
        if not scene_description:
            scene_description = self.current_scene.description
        
        if not scene_description:
            QMessageBox.warning(self, "No Description", "Please enter a scene description first.")
            return
        
        # Get word count
        word_count = int(self.word_count_combo.currentText())
        
        # Advertisement mode: run narrative complexity check before generation
        if self.screenplay and self.screenplay.is_advertisement_mode():
            from core.ad_framework import check_narrative_complexity
            chars = (self.screenplay.story_outline or {}).get("characters", []) if isinstance(self.screenplay.story_outline, dict) else []
            env_count = sum(1 for m in (self.screenplay.identity_block_metadata or {}).values()
                           if isinstance(m, dict) and m.get("type") == "environment")
            complexity = check_narrative_complexity(chars, env_count, self.screenplay.story_outline)
            if complexity.warnings:
                warnings_text = "\n".join(f"- {w}" for w in complexity.warnings)
                reply = QMessageBox.question(
                    self, "Advertisement Mode — Complexity Warning",
                    f"The following narrative complexity warnings were detected:\n\n{warnings_text}\n\n"
                    f"Continue generating anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.No:
                    return
        
        # Wardrobe state validation — every character must have a selection
        if hasattr(self, 'wardrobe_selectors') and self.wardrobe_selectors:
            unset_chars = []
            for eid, combo in self.wardrobe_selectors.items():
                val = combo.currentData()
                if not val:
                    meta = self.screenplay.identity_block_metadata.get(eid, {})
                    unset_chars.append(meta.get("name", eid))
            if unset_chars:
                QMessageBox.warning(
                    self, "Wardrobe State Required",
                    "Wardrobe state must be selected for all characters before scene generation.\n\n"
                    "Unset: " + ", ".join(unset_chars)
                )
                return

        # Disable button during generation
        self.generate_scene_content_btn.setEnabled(False)
        self.generate_scene_content_btn.setText("Generating...")
        
        # Show progress dialog
        progress = QProgressDialog("Generating scene content...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Don't allow canceling
        progress.show()
        
        # Create and start thread
        self.scene_content_thread = SceneContentGenerationThread(
            self.ai_generator,
            scene_description,
            word_count,
            self.screenplay,
            self.current_scene
        )
        self.scene_content_thread.finished.connect(
            lambda content, drift_warnings: self.on_scene_content_generated(content, progress, drift_warnings)
        )
        self.scene_content_thread.error.connect(
            lambda error: self.on_scene_content_error(error, progress)
        )
        self.scene_content_thread.start()
    
    def on_scene_content_generated(self, content: str, progress: QProgressDialog, drift_warnings=None):
        """Handle successful scene content generation."""
        if drift_warnings is None:
            drift_warnings = []
        # Keep progress dialog open for identity extraction phase
        try:
            progress.setLabelText("Saving scene content...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass
        # Merge orphaned character-name paragraphs with following dialogue
        content = self._merge_dialogue_blocks(content)

        # Add paragraph numbers for display
        numbered_content = self._add_paragraph_numbers(content)
        self.scene_content_display.setPlainText(numbered_content)
        
        # Automatically save the generated content to the scene (merged, without numbers)
        if self.current_scene:
            if self.current_scene.metadata is None:
                self.current_scene.metadata = {}
            self.current_scene.metadata["generated_content"] = content
            from datetime import datetime
            self.current_scene.updated_at = datetime.now().isoformat()
        
        self.generate_scene_content_btn.setEnabled(True)
        self.generate_scene_content_btn.setText("Generate with AI")
        
        # Close progress dialog
        try:
            progress.close()
        except Exception:
            pass
        
        if drift_warnings:
            QMessageBox.warning(self, "Narrative Drift Detected",
                "Possible narrative drift detected; review recommended.\n\n" + "\n".join(drift_warnings))
        
        self._show_status("Scene content generated — review then click Approve", 5000)
    
    def _extract_environment_from_content(self, content: str, scene_title: str) -> str:
        """Extract environment description from scene content using AI.
        Includes furniture, fixtures, and significant objects that define the space."""
        if not self.ai_generator or not self.ai_generator._adapter:
            return f"Setting: {scene_title}"
        
        try:
            prompt = f"""Analyze the following scene and extract environmental/setting details.

Scene: {scene_title}

Content:
{content[:4000]}

Extract the following if mentioned:
- Location type (indoor/outdoor, room type, town, city, etc.)
- Time period, weather, time of day
- Architectural style or notable features
- Furniture, fixtures, and significant objects that define the space (e.g. desk, sofa, laptop, posters, table, TV)
- Light sources and lighting conditions: which objects emit light (torches, lamps, candles, fires, screens, neon signs, chandeliers, sconces, braziers), the quality of light they produce (colour, warmth, intensity, flicker, direction of shadows), and any objects that are specifically dark or unlit
- Atmosphere or mood of the setting

Provide a concise 4-6 sentence description that includes the space, furniture/objects, AND lighting. Do NOT include character actions or dialogue.

Example: "A cluttered living room with faded comedy posters on the walls. A worn sofa against one wall, piled with scripts and notebooks. A coffee table littered with empty mugs and papers. A laptop sits open. Warm light from a desk lamp pools across scattered papers, the rest of the room lit only by the pale glow of the laptop screen and dim city lights visible through the window. Quiet, reflective atmosphere."

Respond with ONLY the environment description, no preamble."""

            response = self.ai_generator._chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert at extracting environmental descriptions from scene text. Include furniture, fixtures, significant objects that define the space, and especially light sources and their effect on the environment."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=350
            )
            
            env_desc = response.choices[0].message.content.strip()
            
            # Clean up any markdown or quotes
            env_desc = env_desc.strip('"""').strip("'''").strip('"').strip("'")
            
            # Make sure it's not too long (allow more for furniture/objects)
            if len(env_desc) > 450:
                env_desc = env_desc[:450] + "..."
            
            return env_desc if env_desc else f"Setting: {scene_title}"
            
        except Exception as e:
            print(f"Error extracting environment: {e}")
            return f"Setting: {scene_title}"
    
    def _extract_environment_description_from_content(self, content: str, env_name: str) -> str:
        """Extract the environment/location description from scene content.
        
        Splits paragraphs into sentences and keeps only sentences that describe the
        physical setting (architecture, light, weather, objects). Sentences about
        characters, actions, or dialogue are discarded.
        
        Sentence-level relevance filtering ensures that only sentences which
        actually describe THIS environment are returned — not sentences from
        the same paragraph that describe a different location.
        Rule-based, no AI call.
        """
        import re
        if not content or not env_name:
            return ""
        
        core_name = re.sub(r'^[_\{\[]|[_\}\]]$', '', env_name.strip()).strip()
        if not core_name:
            return ""
        
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        if not paragraphs:
            return ""
        
        name_lower = core_name.lower()
        name_parts = [p for p in re.split(r"[\s'\"]+", core_name) if len(p) >= 3]

        all_env_names = set()
        if self.screenplay:
            for eid, meta in self.screenplay.identity_block_metadata.items():
                if (meta.get("type") or "").lower() == "environment":
                    raw = meta.get("name", "")
                    cleaned = re.sub(r'^[_\{\[]|[_\}\]]$', '', raw.strip()).strip().lower()
                    if cleaned and cleaned != name_lower:
                        all_env_names.add(cleaned)

        def _is_character_sentence(sent: str) -> bool:
            """Return True if this sentence is primarily about a character, not the setting."""
            s = sent.strip()
            if not s:
                return True
            # Starts with a CAPS character name
            if re.match(r'^[A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)*\b', s):
                return True
            # Contains action markup *verbs*
            if re.search(r'\*[^*]+\*', s):
                return True
            # Dialogue
            if s.startswith('"') or s.startswith('\u201c'):
                return True
            # Character name followed by comma (e.g. "ADRIAN VAUGHN, a man...")
            if re.search(r'\b[A-Z]{2,}(?:\s+[A-Z]{2,})+,\s', s):
                return True
            # Starts with possessive pronoun (His/Her/Their) — about a person, not the setting
            if re.match(r'^(?:His|Her|Their|He|She|They)\s', s):
                return True
            # Contains [object] markup — about an object, not the environment
            if re.search(r'\[[^\]]+\]', s):
                return True
            return False

        def _clean_sentence(sent: str) -> str:
            """Remove residual markup tokens from a setting-oriented sentence."""
            s = re.sub(r'\([a-z_]+\)', '', sent)       # (sfx)
            s = re.sub(r'\*[^*]+\*', '', s)             # *actions*
            s = re.sub(r'_([^_]+)_', r'\1', s)          # _Location_ → Location
            s = re.sub(r'\[[^\]]+\]', '', s)             # [objects]
            s = re.sub(r'\{[^}]+\}', '', s)              # {vehicles}
            s = re.sub(r'"[^"]*"', '', s)                # "dialogue"
            s = re.sub(r'\s{2,}', ' ', s).strip()
            return s

        def _sentence_mentions_env(sent_lower: str) -> bool:
            """Return True if this sentence references the target environment."""
            if name_lower in sent_lower:
                return True
            if name_parts and any(p.lower() in sent_lower for p in name_parts):
                return True
            return False

        def _sentence_mentions_other_env(sent_lower: str) -> bool:
            """Return True if this sentence references a DIFFERENT known environment."""
            for other in all_env_names:
                if other in sent_lower:
                    return True
            return False

        env_sentences = []
        is_primary_paragraph = False
        for para in paragraphs[:8]:
            para_lower = para.lower()
            lines = para.split('\n')
            if len(lines) >= 2 and lines[1].strip().startswith('"'):
                continue
            if para.startswith('"'):
                continue
            mentioned = name_lower in para_lower
            if not mentioned and name_parts:
                mentioned = any(part.lower() in para_lower for part in name_parts)
            if not mentioned:
                continue

            sentences = re.split(r'(?<=[.!?])\s+', para)
            direct_mentions = [s for s in sentences if _sentence_mentions_env(s.lower())]
            is_primary_paragraph = len(direct_mentions) >= 2 or (
                len(sentences) > 0 and _sentence_mentions_env(sentences[0].lower())
            )

            for sent in sentences:
                if _is_character_sentence(sent):
                    continue
                sent_lower = sent.lower()
                mentions_this = _sentence_mentions_env(sent_lower)
                mentions_other = _sentence_mentions_other_env(sent_lower)

                if mentions_other and not mentions_this:
                    continue
                if not is_primary_paragraph and not mentions_this:
                    continue

                cleaned = _clean_sentence(sent)
                if len(cleaned) > 15:
                    env_sentences.append(cleaned)
        
        if not env_sentences:
            first = paragraphs[0]
            first_lower = first.lower()
            if not first.startswith('"') and len(first) > 30:
                if name_lower in first_lower or (name_parts and any(p.lower() in first_lower for p in name_parts)):
                    sentences = re.split(r'(?<=[.!?])\s+', first)
                    for sent in sentences:
                        if _is_character_sentence(sent):
                            continue
                        cleaned = _clean_sentence(sent)
                        if len(cleaned) > 15:
                            env_sentences.append(cleaned)
        
        result = " ".join(env_sentences)
        max_len = 500
        if len(result) > max_len:
            result = result[:max_len].rsplit(".", 1)[0] + "." if "." in result[:max_len] else result[:max_len] + "..."
        
        return result.strip()

    def _extract_character_appearance_from_scene(self, content: str, character_name: str) -> str:
        """Extract a short physical/appearance description of the character using AI.
        
        Returns only an idea of what the character looks like (age, build, clothing, etc.),
        NOT action narrative, setting, or dialogue. Used for character identity block user_notes.
        """
        if not self.ai_generator or not self.ai_generator._adapter or not content or not character_name:
            return ""
        
        # Optional: get character outline from story for context (e.g. "cybersecurity expert" informs style)
        outline_hint = ""
        story_outline = getattr(self.screenplay, "story_outline", None) or {}
        if isinstance(story_outline, dict):
            for char in story_outline.get("characters", []) or []:
                if isinstance(char, dict) and (char.get("name") or "").strip():
                    name_match = (char.get("name") or "").strip().lower()
                    if name_match == character_name.strip().lower():
                        outline_snippet = (char.get("outline") or "")[:300]
                        if outline_snippet:
                            outline_hint = f"\nCharacter context from story: {outline_snippet}..."
                        break
        
        genre_atmosphere = ""
        if self.screenplay:
            g = getattr(self.screenplay, "genre", None) or []
            a = getattr(self.screenplay, "atmosphere", None) or ""
            if g or a:
                genre_atmosphere = f"\nGenre: {', '.join(g) if isinstance(g, list) else g}. Atmosphere: {a}."
        
        try:
            prompt = f"""Create a SHORT physical description of the character "{character_name}" for visual reference.

Scene content:
{content[:6000]}
{outline_hint}
{genre_atmosphere}

INSTRUCTIONS:
1. If the scene explicitly describes PHYSICAL appearance (hair, build, age, face, skin, features), use those details.
2. If the scene does NOT describe appearance, suggest plausible physical traits from character role and genre.
3. Describe ENDURING physical traits only: age range, build, hair, eye color, skin tone, distinctive features (scars, etc.).
4. Output 1-2 sentences (about 40-80 words). No preamble.
5. Do NOT include:
   - Clothing, attire, or accessories—these belong in scene wardrobe
   - Scene-specific posture, pose, or what they are doing (e.g. "hunched over laptop", "amid takeout containers")
   - Setting, props, or environment
   - Actions, dialogue, or internal emotions

Respond with ONLY the physical appearance description (no clothing)."""


            response = self.ai_generator._chat_completion(
                messages=[
                    {"role": "system", "content": "You create concise visual/physical character descriptions. Describe enduring physical traits only (age, build, hair, eyes, skin)—never clothing, accessories, scene-specific posture, props, or setting."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=200
            )
            
            desc = (response.choices[0].message.content or "").strip()
            desc = desc.strip('"""').strip("'''").strip('"').strip("'")
            
            if not desc or "no physical description" in desc.lower() or "cannot be inferred" in desc.lower():
                return ""
            if len(desc) > 200:
                desc = desc[:200].rsplit(".", 1)[0] + "." if "." in desc[:200] else desc[:200] + "..."
            
            return desc
        except Exception as e:
            print(f"Error extracting character appearance: {e}")
            return ""
    
    def _extract_entity_details_from_scene(self, content: str, entity_name: str, entity_type: str) -> str:
        """Extract entity-relevant snippets from scene content for use as user_notes.
        
        For objects and vehicles: extracts only physical description phrases
        (adjectives, materials, colours, condition) — strips character names, actions, sounds.
        For other types: finds relevant paragraphs as a starting point.
        Rule-based, no AI call.
        """
        if not content or not entity_name or not entity_name.strip():
            return ""
        
        import re
        # Normalize entity name for matching (strip markup, get core text)
        core_name = entity_name.strip()
        # Remove markup: _underlined_, [brackets], {braces}
        core_name = re.sub(r'^[_\{\[]|[_\}\]]$', '', core_name)
        core_name = core_name.strip()
        if not core_name:
            return ""
        
        # Name parts for matching (full name + individual words for character names)
        name_lower = core_name.lower()
        name_parts = [p for p in re.split(r"[\s'\"]+", core_name) if len(p) >= 2]
        if not name_parts:
            name_parts = [core_name] if len(core_name) >= 2 else []
        
        # --- For OBJECTS and VEHICLES: extract physical descriptions only ---
        if entity_type in ("object", "vehicle"):
            return self._extract_physical_description_for_entity(
                content, core_name, name_lower, name_parts
            )
        
        # --- For ENVIRONMENTS: use sentence-level filtering (no character prose) ---
        if entity_type == "environment":
            return self._extract_environment_description_from_content(content, entity_name)
        
        # --- For other entity types: paragraph extraction ---
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        matching = []
        seen = set()
        
        for para in paragraphs:
            para_lower = para.lower()
            matched = name_lower in para_lower
            if not matched and name_parts:
                matched = any(part.lower() in para_lower for part in name_parts)
            if matched and para not in seen:
                seen.add(para)
                matching.append(para)
        
        if not matching:
            return ""
        
        result = " ".join(matching)
        max_len = 800
        if len(result) > max_len:
            result = result[:max_len].rsplit(".", 1)[0] + "." if "." in result[:max_len] else result[:max_len] + "..."
        
        return result.strip()
    
    def _extract_physical_description_for_entity(
        self, content: str, core_name: str, name_lower: str, name_parts: list
    ) -> str:
        """Extract physical/visual description for an object or vehicle from scene content.
        
        Strategy:
        1. Find ALL sentences mentioning the entity across the full scene.
        2. Extract appositive descriptions from every mention.
        3. Also capture descriptive clauses in those sentences and adjacent continuations.
        4. Strip character names, action markup, SFX, and dialogue.
        5. Deduplicate and combine for the richest possible description.
        """
        import re
        if not content:
            return ""
        
        name_escaped = re.escape(core_name)
        entity_ref_pattern = re.compile(
            r'(?:\[' + name_escaped + r'\]|\{{1,2}' + name_escaped + r'\}{1,2}|\b' + name_escaped + r'\b)',
            re.IGNORECASE
        )
        
        raw_sentences = re.split(r'(?<=[.!?])\s+|\n\n+', content)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        
        mention_indices = [i for i, s in enumerate(sentences) if entity_ref_pattern.search(s)]
        if not mention_indices:
            return ""
        
        appos_pattern = re.compile(
            r'(?:\[' + name_escaped + r'\]|\{{1,2}' + name_escaped + r'\}{1,2})'
            r'\s*,\s*(.+?)[.!?]',
            re.IGNORECASE | re.DOTALL
        )
        
        desc_words_pat = re.compile(
            r'\b(?:tarnished|rusty|rusted|gleaming|glowing|bright|dim|dark|'
            r'ancient|old|worn|weathered|dusty|dirty|clean|polished|scratched|dented|cracked|'
            r'ornate|intricate|simple|plain|massive|tiny|small|large|heavy|light|bulky|sleek|'
            r'metallic|wooden|leather|brass|bronze|copper|silver|golden|iron|steel|crystal|glass|'
            r'stone|ceramic|plastic|fabric|velvet|matte|chrome|battered|broken|modified|'
            r'red|blue|green|yellow|black|white|grey|gray|brown|orange|purple|crimson|'
            r'round|square|flat|curved|angular|pointed|cylindrical|'
            r'cobbled|jury-rigged|repurposed|homemade|makeshift|improvised|custom|'
            r'strange|mysterious|unusual|eerie|functional|decorative|'
            r'covered|etched|engraved|painted|carved|studded|taped|wired|tangled|'
            r'device|contraption|array|rig|apparatus|machine|gadget|instrument|'
            r'surface|finish|texture|patina|antenna|screen|monitor|display|dial|gauge|'
            r'with|from|made of|built from|consisting of)\b',
            re.IGNORECASE
        )
        
        def _strip_character_refs(text: str) -> str:
            """Remove CAPS character names and their possessive tails (e.g. ADRIAN VAUGHN's)."""
            s = re.sub(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,})*(?:'s?)?\b", '', text)
            s = re.sub(r'\([a-z_]+\)', '', s)        # (sfx)
            s = re.sub(r'\*([^*]+)\*', r'\1', s)      # *actions* → actions
            s = re.sub(r'"[^"]*"', '', s)              # "dialogue"
            s = re.sub(r'[\[\]\{\}]', '', s)           # [] {} markup
            s = re.sub(r'(?<!\w)_(\w)', r'\1', s)      # _Location_ → Location
            s = re.sub(r'(\w)_(?!\w)', r'\1', s)
            # Clean orphaned possessives and leading articles after name removal
            s = re.sub(r"^\s*'s\b", '', s)
            s = re.sub(r"\s+'s\s+", ' ', s)
            s = re.sub(r'^\s*(?:The|A|An)\s+(?:connects|raises|swings|slams)\b.*', '', s, flags=re.IGNORECASE)
            s = re.sub(r'\s{2,}', ' ', s).strip().strip('.,;:!? ')
            return s

        appositive_parts = []
        for idx in mention_indices:
            m = appos_pattern.search(sentences[idx])
            if m:
                cleaned = _strip_character_refs(m.group(1).strip())
                if len(cleaned) >= 10 and cleaned.lower() not in {p.lower() for p in appositive_parts}:
                    appositive_parts.append(cleaned)
        
        gather_indices = set()
        for idx in mention_indices:
            gather_indices.add(idx)
            if idx + 1 < len(sentences):
                nxt_lower = sentences[idx + 1].lower()
                if (name_lower in nxt_lower
                        or "its " in nxt_lower
                        or (name_parts and "the " + name_parts[0].lower() in nxt_lower)):
                    gather_indices.add(idx + 1)
        
        descriptive_parts = []
        seen_lower = set()
        for idx in sorted(gather_indices):
            sent = sentences[idx]
            cleaned = _strip_character_refs(sent)
            cleaned = re.sub(r'^\s*(?:Her|His|Its|Their|The)\s+', '', cleaned)
            cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
            if len(cleaned) < 5:
                continue
            
            clauses = re.split(r'[,;](?:\s)', cleaned)
            for clause in clauses:
                clause = clause.strip().strip('.,;:!? ')
                if len(clause) < 5:
                    continue
                clause_lower = clause.lower()
                if clause_lower in seen_lower:
                    continue
                mentions = name_lower in clause_lower or any(
                    p.lower() in clause_lower for p in name_parts if len(p) >= 3
                )
                has_desc = bool(desc_words_pat.search(clause))
                if mentions or has_desc:
                    descriptive_parts.append(clause)
                    seen_lower.add(clause_lower)
        
        all_parts = appositive_parts + [
            p for p in descriptive_parts if p.lower() not in {a.lower() for a in appositive_parts}
        ]
        if not all_parts:
            return ""
        
        result = ". ".join(all_parts)
        result = re.sub(r'[\[\]\{\}]', '', result)
        result = re.sub(r'(?<!\w)_(\w)', r'\1', result)
        result = re.sub(r'(\w)_(?!\w)', r'\1', result)
        result = re.sub(r'\s{2,}', ' ', result).strip()
        max_len = 800
        if len(result) > max_len:
            result = result[:max_len].rsplit(".", 1)[0] + "." if "." in result[:max_len] else result[:max_len]
        
        return result.strip()
    
    def _enrich_entity_descriptions_from_full_scene(self, content: str):
        """Second pass: scan the FULL scene for additional descriptive details per entity.

        After initial extraction populates user_notes from the first mention or
        limited context, this method scans every paragraph for each entity in the
        current scene and appends any new descriptive sentences that were missed.

        Only non-character entities (objects, vehicles, environments) are enriched
        here; characters use their own AI-based appearance extraction which is
        already fed the wider content window.
        """
        import re
        if not content or not self.screenplay or not self.current_scene:
            return

        scene_id = getattr(self.current_scene, "scene_id", None)
        raw_sentences = re.split(r'(?<=[.!?])\s+|\n\n+', content)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        if not sentences:
            return

        def _is_character_or_action(sent: str) -> bool:
            s = sent.strip()
            if not s:
                return True
            if s.startswith('"') or s.startswith('\u201c'):
                return True
            if re.match(r'^[A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)*\b', s):
                return True
            if re.search(r'\*[^*]+\*', s):
                return True
            return False

        def _clean(sent: str) -> str:
            s = re.sub(r'\([a-z_]+\)', '', sent)
            s = re.sub(r'\*[^*]+\*', '', s)
            s = re.sub(r'_([^_]+)_', r'\1', s)
            s = re.sub(r'\[[^\]]+\]', '', s)
            s = re.sub(r'\{[^}]+\}', '', s)
            s = re.sub(r'"[^"]*"', '', s)
            s = re.sub(r'\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b', '', s)
            s = re.sub(r'\s{2,}', ' ', s).strip()
            return s

        enriched_count = 0
        for entity_id, meta in list(self.screenplay.identity_block_metadata.items()):
            etype = (meta.get("type") or "").lower()
            if etype not in ("object", "vehicle", "environment"):
                continue
            if meta.get("source_scene_id") and meta.get("source_scene_id") != scene_id:
                continue

            entity_name = meta.get("name", "").strip()
            if not entity_name:
                continue
            core_name = re.sub(r'^[_\{\[\]\}]|[_\{\[\]\}]$', '', entity_name).strip()
            if not core_name:
                continue

            name_lower = core_name.lower()
            name_parts = [p for p in re.split(r"[\s'\"]+", core_name) if len(p) >= 3]
            name_escaped = re.escape(core_name)
            pattern = re.compile(
                r'(?:\[' + name_escaped + r'\]|\{{1,2}' + name_escaped + r'\}{1,2}|\b' + name_escaped + r'\b)',
                re.IGNORECASE
            )

            existing_notes = (meta.get("user_notes") or "").strip()
            existing_lower = existing_notes.lower()

            new_fragments = []
            for sent in sentences:
                if not pattern.search(sent):
                    continue
                if etype != "environment" and _is_character_or_action(sent):
                    continue
                cleaned = _clean(sent)
                if len(cleaned) < 20:
                    continue
                if cleaned.lower() in existing_lower:
                    continue
                already_covered = any(frag.lower() in cleaned.lower() or cleaned.lower() in frag.lower()
                                      for frag in new_fragments)
                if already_covered:
                    continue
                new_fragments.append(cleaned)

            if not new_fragments:
                continue

            combined = existing_notes
            for frag in new_fragments:
                candidate = (combined + " " + frag).strip() if combined else frag
                if len(candidate) > 1000:
                    break
                combined = candidate

            if combined != existing_notes:
                self.screenplay.update_identity_block_metadata(entity_id, user_notes=combined)
                enriched_count += 1
                print(f"  + Enriched user_notes for {entity_name} ({etype}): +{len(combined) - len(existing_notes)} chars")

        if enriched_count:
            print(f"Enrichment pass: updated {enriched_count} entities with additional scene details")

        # --- Lighting cross-reference: fold object light sources into environment ---
        self._cross_reference_lighting_objects_to_environment()

    def _cross_reference_lighting_objects_to_environment(self):
        """Scan object entities for lighting keywords and append a summary to the environment.

        Identifies objects whose user_notes suggest they emit (or notably lack)
        light, then appends a 'Light sources:' line to the primary environment's
        user_notes so the environment identity block captures the full lighting
        picture without an extra AI call.
        """
        import re
        if not self.screenplay or not self.current_scene:
            return

        scene_id = getattr(self.current_scene, "scene_id", None)

        _LIGHT_KEYWORDS = re.compile(
            r'\b(?:torch|torchlight|lamp|lantern|candle|candlelight|sconce|brazier|chandelier|'
            r'campfire|bonfire|hearth|fireplace|firelight|fire pit|embers|'
            r'neon|spotlight|bulb|screen glow|headlights|taillights|'
            r'fairy lights|string lights|candelabra|oil lamp|gas lamp|street lamp|'
            r'glow|glowing|flicker|flickering|flame|flames|luminous|luminescent|'
            r'bioluminescent|phosphorescent|lit |lighted|ablaze|smoldering|'
            r'unlit|extinguished|dark|dead|burned out|burnt out)\b',
            re.IGNORECASE
        )

        env_id = getattr(self.current_scene, "environment_id", None)
        if not env_id:
            for eid, meta in self.screenplay.identity_block_metadata.items():
                if (meta.get("type") or "").lower() == "environment" and meta.get("is_primary_environment"):
                    src = meta.get("source_scene_id", "")
                    if src == scene_id or not src:
                        env_id = eid
                        break
        if not env_id:
            return

        env_meta = self.screenplay.identity_block_metadata.get(env_id)
        if not env_meta:
            return
        existing_env_notes = (env_meta.get("user_notes") or "").strip()
        if "Light sources:" in existing_env_notes or "Light source:" in existing_env_notes:
            return

        light_fragments = []
        for eid, meta in self.screenplay.identity_block_metadata.items():
            if eid == env_id:
                continue
            etype = (meta.get("type") or "").lower()
            if etype not in ("object", "vehicle"):
                continue
            src = meta.get("source_scene_id", "")
            if src and src != scene_id:
                continue
            notes = (meta.get("user_notes") or "").strip()
            if not notes:
                continue
            if not _LIGHT_KEYWORDS.search(notes):
                continue
            obj_name = meta.get("name", "").strip()
            obj_name = re.sub(r'^[_\{\[\]\}]|[_\{\[\]\}]$', '', obj_name).strip()
            if not obj_name:
                continue
            snippet = notes[:120]
            if len(notes) > 120:
                snippet = snippet.rsplit(" ", 1)[0] + "..."
            light_fragments.append(f"{obj_name} — {snippet}")

        if not light_fragments:
            return

        summary = "Light sources: " + "; ".join(light_fragments)
        updated = (existing_env_notes + " " + summary).strip() if existing_env_notes else summary
        if len(updated) <= 1200:
            self.screenplay.update_identity_block_metadata(env_id, user_notes=updated)
            print(f"  + Lighting cross-reference: added {len(light_fragments)} light source(s) to environment")

    def extract_entities_from_scene_content(self, content: str, progress=None):
        """Extract entities from scene content and create placeholders.
        
        MANDATORY: Complete character extraction (ZERO SELECTIVITY).
        - ALL Wizard characters mentioned in scene MUST be extracted
        - No filtering by importance, screen time, or action
        - Validation pass ensures no missing characters
        """
        import traceback, datetime as _dt, os as _os
        _log_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "debug_entity_extraction.log")

        def _elog(msg: str):
            try:
                with open(_log_path, "a", encoding="utf-8") as _f:
                    _f.write(f"[{_dt.datetime.now().isoformat()}] {msg}\n")
            except Exception:
                pass

        _elog("=" * 80)
        _elog("extract_entities_from_scene_content CALLED")
        _elog(f"  current_scene: {getattr(self.current_scene, 'title', None)}")
        _elog(f"  screenplay: {bool(self.screenplay)}")
        _elog(f"  ai_generator: {bool(self.ai_generator)}")
        _elog(f"  content length: {len(content) if content else 0}")

        if not self.current_scene or not self.screenplay or not self.ai_generator:
            _elog("EARLY RETURN — missing current_scene, screenplay, or ai_generator")
            return
        
        def _update_progress(msg: str):
            if progress:
                progress.setLabelText(msg)
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
        
        try:
            _elog("STEP 0: Sanitizing character registry...")
            _update_progress("Sanitizing character registry...")
            self._sanitize_character_registry()
            _elog("STEP 0 complete.")
            
            _elog("STEP 1: Extracting characters from scene...")
            _update_progress("Extracting characters from scene...")
            characters_named_in_scene = self.ai_generator._extract_all_characters_named_in_scene(
                content, self.screenplay
            )
            _elog(f"STEP 1 primary result: {characters_named_in_scene}")
            if not characters_named_in_scene and getattr(self.screenplay, "character_registry_frozen", False):
                characters_named_in_scene = self.ai_generator._extract_all_wizard_characters_from_scene(
                    content, self.screenplay
                )
                _elog(f"STEP 1 fallback result: {characters_named_in_scene}")
            
            # Safety-net filtering: remove non-person entities, fold body parts, strip articles.
            # _extract_all_characters_named_in_scene already does this, but the fallback path
            # or a stale registry can still let bad entries through.
            import re as _re
            filtered_chars = []
            filtered_lower = set()
            for _cname in characters_named_in_scene:
                # Filter non-person entities (UI, software, abstract visuals)
                if self.ai_generator._is_company_or_concept_entity(_cname):
                    print(f"  [filtered non-person] {_cname}")
                    continue
                # Fold body-part possessives ("filmmaker's hands" → "filmmaker")
                bp = self.ai_generator._split_possessive_body_part(_cname)
                if bp:
                    _cname = self.ai_generator._normalize_character_name_for_identity(bp[0]) or bp[0]
                    print(f"  [folded body-part] → {_cname}")
                else:
                    # Strip leading articles ("A FILMMAKER" → "FILMMAKER")
                    stripped = self.ai_generator._normalize_character_name_for_identity(_cname)
                    if stripped and stripped.lower() != _cname.lower():
                        print(f"  [stripped article] {_cname} → {stripped}")
                        _cname = stripped
                if _cname.lower() not in filtered_lower:
                    filtered_chars.append(_cname)
                    filtered_lower.add(_cname.lower())
            characters_named_in_scene = filtered_chars
            
            # Filter name collisions: no two characters may share a significant name part.
            # When two names collide, prefer the canonical (registry) version.
            _registry_set = {n.strip().upper() for n in (getattr(self.screenplay, 'character_registry', []) or []) if n}
            collision_filtered = []
            for _cname in characters_named_in_scene:
                _cwords = {w.lower() for w in _re.sub(r"['\"]", " ", _cname).split() if len(w) >= 3}
                has_collision = False
                for idx, kept_name in enumerate(collision_filtered):
                    _kwords = {w.lower() for w in _re.sub(r"['\"]", " ", kept_name).split() if len(w) >= 3}
                    shared = _cwords & _kwords
                    if shared:
                        # Prefer the registry (canonical) name over the scene-extracted variant
                        _cname_is_canonical = _cname.strip().upper() in _registry_set
                        _kept_is_canonical = kept_name.strip().upper() in _registry_set
                        if _cname_is_canonical and not _kept_is_canonical:
                            print(f"  [name collision] '{kept_name}' shares word(s) {shared} with canonical '{_cname}' — replacing with canonical")
                            collision_filtered[idx] = _cname
                        else:
                            print(f"  [name collision] '{_cname}' shares word(s) {shared} with '{kept_name}' — skipping '{_cname}'")
                        has_collision = True
                        break
                if not has_collision:
                    collision_filtered.append(_cname)
            characters_named_in_scene = collision_filtered
            
            _elog(f"STEP 1 final (after filters): {len(characters_named_in_scene)} characters: {characters_named_in_scene}")
            print(f"CHARACTER EXTRACTION: Found {len(characters_named_in_scene)} characters named in scene")
            for char_name in characters_named_in_scene:
                print(f"  - {char_name}")
            
            _elog("STEP 2: Extracting environments, objects, and vehicles...")
            _update_progress("Extracting environments, objects, and vehicles...")
            markup_locations = self.ai_generator._extract_locations_from_text(content, max_locations=50)
            markup_objects = self.ai_generator._extract_objects_from_scene_markup(content, require_interaction=True)
            markup_vehicles = self.ai_generator._extract_vehicles_from_scene_markup(content, require_interaction=True)
            entities = [
                {"name": name, "type": "environment", "description": ""} for name in markup_locations
            ] + [
                {"name": name, "type": "object", "description": ""} for name in markup_objects
            ] + [
                {"name": name, "type": "vehicle", "description": ""} for name in markup_vehicles
            ]
            if not entities:
                print("No markup entities extracted from scene content (only explicitly marked entities)")
            _elog(f"STEP 2 complete: {len(markup_locations)} locations, {len(markup_objects)} objects, {len(markup_vehicles)} vehicles")
            
            _elog("STEP 3: Creating character identity block placeholders...")
            _update_progress("Creating character identity blocks...")
            characters_created = 0
            # Build set of known main character names from story outline
            story_outline = getattr(self.screenplay, 'story_outline', {}) or {}
            wizard_chars = story_outline.get("characters", []) if isinstance(story_outline, dict) else []
            known_main_lower = {
                wc.get("name", "").strip().lower()
                for wc in wizard_chars
                if isinstance(wc, dict) and wc.get("name")
            }
            for char_name in characters_named_in_scene:
                # Use canonical name when registry is frozen (e.g. JASON -> JASON LYNCH) for consistent lookup
                lookup_name = char_name
                if getattr(self.screenplay, "character_registry_frozen", False):
                    canonical = self.screenplay.resolve_character_to_canonical(char_name)
                    if canonical:
                        lookup_name = canonical
                
                # Check if identity block already exists (use lookup_name for consistency)
                existing_block = self.screenplay.get_identity_block_by_name(lookup_name, "character")
                if existing_block:
                    print(f"  ✓ Identity block already exists for {char_name}")
                    continue
                
                # Create identity block for this character (use lookup_name so block matches registry)
                char_id = self.screenplay.create_placeholder_identity_block(
                    lookup_name,
                    "character",
                    self.current_scene.scene_id
                )
                if char_id:
                    characters_created += 1
                    details = ""
                    char_species = "Human"
                    for wc in wizard_chars:
                        if isinstance(wc, dict) and wc.get("name", "").strip().lower() == lookup_name.strip().lower():
                            details = str(wc.get("physical_appearance", "") or "").strip()
                            char_species = str(wc.get("species", "Human") or "Human").strip()
                            break
                    
                    is_minor = lookup_name.strip().lower() not in known_main_lower
                    
                    if not details and is_minor:
                        _update_progress(f"Generating appearance for minor character {lookup_name}...")
                        try:
                            premise = story_outline.get("premise", "") or ""
                            genres = story_outline.get("genres", []) or []
                            atmosphere = story_outline.get("atmosphere", "") or ""
                            title = getattr(self.screenplay, "title", "") or ""
                            main_storyline = story_outline.get("main_storyline", "") or ""
                            result = self.ai_generator.regenerate_character_details(
                                premise=premise,
                                genres=genres if isinstance(genres, list) else [genres],
                                atmosphere=atmosphere,
                                title=title,
                                main_storyline=main_storyline,
                                character_name=lookup_name,
                                regenerate_type="physical_appearance",
                                existing_characters=wizard_chars,
                            )
                            details = (result.get("physical_appearance", "") or "").strip()
                            print(f"  ⚙ Generated physical appearance for minor character: {lookup_name}")
                        except Exception as gen_err:
                            print(f"  ⚠ Failed to generate appearance for {lookup_name}: {gen_err}")
                    elif not details:
                        details = self._extract_character_appearance_from_scene(content, char_name)
                    
                    # Species inference fallback: if wizard data says Human, check text
                    if not char_species or char_species == "Human":
                        from core.ai_generator import infer_species_from_text
                        main_sl = str((story_outline.get("main_storyline", "") or ""))
                        char_ctx = ""
                        for seg in main_sl.split(". "):
                            if lookup_name.upper() in seg.upper():
                                char_ctx += seg + ". "
                        inferred_sp = infer_species_from_text("", details or "", char_ctx, lookup_name)
                        if inferred_sp != "Human":
                            char_species = inferred_sp
                    
                    # Always persist species to identity block metadata
                    meta = self.screenplay.identity_block_metadata.get(char_id)
                    if meta:
                        meta["species"] = char_species
                    
                    if details:
                        self.screenplay.update_identity_block_metadata(char_id, user_notes=details)
                    
                    # Also update the wizard character data so it persists to project
                    for wc in wizard_chars:
                        if isinstance(wc, dict) and wc.get("name", "").strip().lower() == lookup_name.strip().lower():
                            if wc.get("species", "Human") == "Human" and char_species != "Human":
                                wc["species"] = char_species
                            break
                    
                    # Add minor characters to story_outline and registry
                    if is_minor:
                        wizard_chars.append({
                            "name": lookup_name,
                            "role": "minor",
                            "outline": "",
                            "growth_arc": "",
                            "physical_appearance": details or "",
                            "species": char_species
                        })
                        known_main_lower.add(lookup_name.strip().lower())
                        # Add to character registry so future scenes recognise this name
                        registry = getattr(self.screenplay, "character_registry", []) or []
                        if lookup_name not in registry:
                            overlap = self.screenplay.has_overlapping_registry_name(lookup_name)
                            if overlap:
                                print(f"  [registry guard] Skipping '{lookup_name}' — overlaps with existing '{overlap}'")
                            else:
                                registry.append(lookup_name)
                                self.screenplay.character_registry = registry
                        print(f"  + Created identity block for MINOR character {lookup_name}")
                    else:
                        print(f"  + Created identity block placeholder for {char_name}")
            _elog(f"STEP 3 complete: {characters_created} character blocks created")

            # STEP 3b: Ensure ALL wizard characters have identity block placeholders
            # Main characters may not appear in scene content yet (e.g. scenes 2-5) but
            # still need identity blocks so wardrobe variants and other features work.
            for wc in wizard_chars:
                if not isinstance(wc, dict):
                    continue
                wc_name = (wc.get("name") or "").strip()
                if not wc_name:
                    continue
                existing = self.screenplay.get_identity_block_by_name(wc_name, "character")
                if existing:
                    continue
                char_id = self.screenplay.create_placeholder_identity_block(
                    wc_name, "character", self.current_scene.scene_id
                )
                if char_id:
                    characters_created += 1
                    details = str(wc.get("physical_appearance", "") or "").strip()
                    char_species = str(wc.get("species", "Human") or "Human").strip()
                    if details:
                        self.screenplay.update_identity_block_metadata(char_id, user_notes=details)
                    meta = self.screenplay.identity_block_metadata.get(char_id)
                    if meta:
                        meta["species"] = char_species
                    print(f"  + Created identity block for wizard character {wc_name}")
            _elog(f"STEP 3b complete: ensured all wizard characters have identity blocks")

            _elog("STEP 4: Validation pass...")
            # STEP 4: Validation pass (REQUIRED) - ensure no characters named in scene are missing
            # Do NOT proceed with partial data - retry if validation fails
            # Use lookup_name (canonical when registry frozen) for consistency with creation
            missing_characters = []
            for char_name in characters_named_in_scene:
                lookup_name = char_name
                if getattr(self.screenplay, "character_registry_frozen", False):
                    canonical = self.screenplay.resolve_character_to_canonical(char_name)
                    if canonical:
                        lookup_name = canonical
                existing_block = self.screenplay.get_identity_block_by_name(lookup_name, "character")
                if not existing_block:
                    missing_characters.append(char_name)
            
            if missing_characters:
                print(f"⚠️ VALIDATION FAILED: {len(missing_characters)} character(s) missing identity blocks:")
                for char_name in missing_characters:
                    print(f"    - {char_name}")
                # Retry: force create identity blocks for missing characters
                for char_name in missing_characters:
                    lookup_name = char_name
                    if getattr(self.screenplay, "character_registry_frozen", False):
                        canonical = self.screenplay.resolve_character_to_canonical(char_name)
                        if canonical:
                            lookup_name = canonical
                    print(f"  Retrying creation for: {char_name}")
                    char_id = self.screenplay.create_placeholder_identity_block(
                        lookup_name,
                        "character",
                        self.current_scene.scene_id
                    )
                    if char_id:
                        characters_created += 1
                        details = ""
                        for wc in wizard_chars:
                            if isinstance(wc, dict) and wc.get("name", "").strip().lower() == lookup_name.strip().lower():
                                details = str(wc.get("physical_appearance", "") or "").strip()
                                break
                        is_minor_retry = lookup_name.strip().lower() not in known_main_lower
                        if not details and is_minor_retry:
                            _update_progress(f"Generating appearance for minor character {lookup_name}...")
                            try:
                                premise = story_outline.get("premise", "") or ""
                                genres = story_outline.get("genres", []) or []
                                atmosphere = story_outline.get("atmosphere", "") or ""
                                title = getattr(self.screenplay, "title", "") or ""
                                main_storyline = story_outline.get("main_storyline", "") or ""
                                result = self.ai_generator.regenerate_character_details(
                                    premise=premise,
                                    genres=genres if isinstance(genres, list) else [genres],
                                    atmosphere=atmosphere,
                                    title=title,
                                    main_storyline=main_storyline,
                                    character_name=lookup_name,
                                    regenerate_type="physical_appearance",
                                    existing_characters=wizard_chars,
                                )
                                details = (result.get("physical_appearance", "") or "").strip()
                            except Exception:
                                pass
                        elif not details:
                            details = self._extract_character_appearance_from_scene(content, char_name)
                        if details:
                            self.screenplay.update_identity_block_metadata(char_id, user_notes=details)
                        if is_minor_retry:
                            wizard_chars.append({
                                "name": lookup_name, "role": "minor",
                                "outline": "", "growth_arc": "",
                                "physical_appearance": details or ""
                            })
                            known_main_lower.add(lookup_name.strip().lower())
                            registry = getattr(self.screenplay, "character_registry", []) or []
                            if lookup_name not in registry:
                                overlap = self.screenplay.has_overlapping_registry_name(lookup_name)
                                if overlap:
                                    print(f"  [registry guard] Skipping '{lookup_name}' — overlaps with existing '{overlap}'")
                                else:
                                    registry.append(lookup_name)
                                    self.screenplay.character_registry = registry
                            print(f"  + Created identity block for MINOR character {lookup_name} (retry)")
                        else:
                            print(f"  + Created identity block placeholder for {char_name} (retry)")
                # Re-validate (use lookup_name for consistency)
                still_missing = []
                for c in missing_characters:
                    lookup_c = c
                    if getattr(self.screenplay, "character_registry_frozen", False):
                        can = self.screenplay.resolve_character_to_canonical(c)
                        if can:
                            lookup_c = can
                    if not self.screenplay.get_identity_block_by_name(lookup_c, "character"):
                        still_missing.append(c)
                if still_missing:
                    print(f"⚠️ VALIDATION STILL FAILED after retry: {still_missing}")
                else:
                    print(f"✓ VALIDATION PASSED after retry: All {len(characters_named_in_scene)} characters have identity blocks")
            else:
                print(f"✓ VALIDATION PASSED: All {len(characters_named_in_scene)} characters have identity blocks")
            _elog("STEP 4 complete.")
            
            _elog("STEP 4b: Extracting wardrobes (respecting selector state)...")
            _update_progress("Extracting character wardrobes...")
            scene_context = (self.current_scene.title or "") + " " + (self.current_scene.description or "")
            selector_state = getattr(self.current_scene, 'character_wardrobe_selector', {}) or {}
            last_variants = getattr(self.screenplay, 'character_last_wardrobe_variant', {}) or {}

            for char_name in characters_named_in_scene:
                lookup_key = f"character:{char_name}".lower()
                entity_id = self.screenplay.identity_block_ids.get(lookup_key)
                if not entity_id and getattr(self.screenplay, "character_registry_frozen", False):
                    canonical = self.screenplay.resolve_character_to_canonical(char_name)
                    if canonical:
                        entity_id = self.screenplay.identity_block_ids.get(f"character:{canonical}".lower())
                if not entity_id:
                    continue

                choice = selector_state.get(entity_id, "change")

                if choice == "same":
                    prev_vid = last_variants.get(entity_id)
                    if prev_vid:
                        if not hasattr(self.current_scene, 'character_wardrobe_variant_ids'):
                            self.current_scene.character_wardrobe_variant_ids = {}
                        self.current_scene.character_wardrobe_variant_ids[entity_id] = prev_vid
                        print(f"  = Carried forward wardrobe variant for {char_name} (same)")
                    continue

                # choice == "change" or "change_in_scene": extract wardrobe text
                wardrobe = self.ai_generator.extract_character_wardrobe_from_scene(
                    content, char_name, scene_context
                )
                if wardrobe:
                    self.screenplay.set_character_wardrobe_for_scene(
                        self.current_scene.scene_id, entity_id, wardrobe
                    )
                    print(f"  + Extracted wardrobe for {char_name}: {wardrobe[:60]}...")

                    # Reuse existing variant for this scene if one is already assigned
                    existing_vids = getattr(self.current_scene, 'character_wardrobe_variant_ids', {}) or {}
                    existing_vid = existing_vids.get(entity_id, "")
                    existing_variant = (
                        self.screenplay.get_wardrobe_variant_by_id(entity_id, existing_vid)
                        if existing_vid else None
                    )

                    if existing_variant:
                        self.screenplay.update_wardrobe_variant(
                            entity_id, existing_vid, description=wardrobe
                        )
                        print(f"  ~ Updated existing wardrobe variant for {char_name} in scene {self.current_scene.scene_number}")
                    else:
                        import uuid as _uuid
                        new_vid = str(_uuid.uuid4())[:8]
                        scene_label = f"Scene {self.current_scene.scene_number}"
                        variant_data = {
                            "variant_id": new_vid,
                            "label": scene_label,
                            "description": wardrobe,
                            "identity_block": "",
                            "reference_image_prompt": "",
                            "image_path": "",
                            "created_at": "",
                        }
                        self.screenplay.add_wardrobe_variant(entity_id, variant_data)
                        if not hasattr(self.current_scene, 'character_wardrobe_variant_ids'):
                            self.current_scene.character_wardrobe_variant_ids = {}
                        self.current_scene.character_wardrobe_variant_ids[entity_id] = new_vid
                        print(f"  + Created pending wardrobe variant '{scene_label}' for {char_name} (image required)")
            
            # Refresh wardrobe UI after extraction
            if hasattr(self, '_refresh_wardrobe_ui') and self.current_scene:
                self._refresh_wardrobe_ui(self.current_scene)
            
            _elog("STEP 4b complete.")
            _elog("STEP 5: Creating environment, object, and vehicle identity blocks...")
            _update_progress("Creating environment, object, and vehicle identity blocks...")
            entities_created = characters_created
            environments_extracted = 0
            scene_desc = self.current_scene.description or ""
            
            if entities:
                for entity in entities:
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "")
                    description = entity.get("description", "")
                    
                    if not entity_name or not entity_type:
                        continue
                    
                    # Skip characters - already handled in STEP 3 (complete extraction)
                    if entity_type == "character":
                        continue
                    
                    # Wizard character list is absolute authority: reclassify if needed
                    if entity_type in ("environment", "object", "vehicle") and getattr(self.screenplay, "character_registry_frozen", False):
                        canonical = self.screenplay.resolve_character_to_canonical(entity_name)
                        if canonical is not None:
                            # This is a character, not an object/vehicle/environment - skip (already handled)
                            continue
                    
                    # Do not create character blocks for extras
                    if self.ai_generator._is_extras_entity(entity_name, description, entity_type):
                        continue
                    
                    # Special handling for extracted environments
                    if entity_type == "environment":
                        # Vehicle interior: ENVIRONMENT with parent_vehicle. Vehicle exterior = VEHICLE only.
                        # If this environment name implies a vehicle interior (e.g. "Starfall Cruiser – Bridge"),
                        # ensure the VEHICLE identity exists first, then set parent_vehicle on the environment.
                        parent_vehicle_name = self.ai_generator._parse_vehicle_interior_from_environment_name(entity_name)
                        if parent_vehicle_name:
                            # Create VEHICLE identity first if it does not exist (exterior). Camera outside = VEHICLE.
                            existing_vehicle = self.screenplay.get_identity_block_by_name(parent_vehicle_name, "vehicle")
                            if not existing_vehicle:
                                veh_id = self.screenplay.create_placeholder_identity_block(parent_vehicle_name, "vehicle", self.current_scene.scene_id)
                                if veh_id:
                                    notes = self._extract_entity_details_from_scene(content, parent_vehicle_name, "vehicle")
                                    if notes:
                                        self.screenplay.update_identity_block_metadata(veh_id, user_notes=notes)
                            env_id = self.screenplay.create_placeholder_identity_block(entity_name, "environment", self.current_scene.scene_id)
                            self.screenplay.update_identity_block_metadata(env_id, parent_vehicle=parent_vehicle_name)
                        else:
                            env_id = self.screenplay.create_placeholder_identity_block(entity_name, "environment", self.current_scene.scene_id)
                        # Apply MODE A/B to extracted environments
                        requires_extras = self.ai_generator._scene_requires_extras(scene_desc, content)
                        self.screenplay.update_identity_block_metadata(env_id, extras_present=requires_extras, foreground_zone="clear")
                        if requires_extras:
                            self.screenplay.update_identity_block_metadata(env_id, extras_density="sparse", extras_activities="", extras_depth="background_only")
                        # Auto-populate user_notes for environment from scene content
                        env_notes = description
                        if not env_notes:
                            env_notes = self._extract_environment_description_from_content(content, entity_name)
                        if env_notes:
                            self.screenplay.update_identity_block_metadata(env_id, user_notes=env_notes)
                            print(f"  + Environment user_notes set for {entity_name}: {env_notes[:80]}...")
                        if environments_extracted == 0:
                            self.current_scene.environment_id = env_id
                            self.screenplay.update_identity_block_metadata(env_id, is_primary_environment=True)
                        else:
                            self.screenplay.update_identity_block_metadata(env_id, is_primary_environment=False)
                        environments_extracted += 1
                        entities_created += 1
                        continue
                    
                    # Create placeholder for non-character entities (vehicles, objects)
                    entity_id = self.screenplay.create_placeholder_identity_block(entity_name, entity_type, self.current_scene.scene_id)
                    if not entity_id:
                        continue
                    
                    # Pre-fill user notes: use description if provided, else extract from scene content
                    notes = description
                    if not notes:
                        notes = self._extract_entity_details_from_scene(content, entity_name, entity_type)
                    if notes:
                        self.screenplay.update_identity_block_metadata(entity_id, user_notes=notes)
                    
                    entities_created += 1
            
            # Fallback: Create generic environment placeholder ONLY if no environments were extracted
            if environments_extracted == 0:
                env_name = f"{self.current_scene.title} Environment"
                env_id = self.screenplay.create_placeholder_identity_block(env_name, "environment", self.current_scene.scene_id)
                self.current_scene.environment_id = env_id
                
                # Scene-driven mode: MODE A (empty) vs MODE B (with extras)
                requires_extras = self.ai_generator._scene_requires_extras(scene_desc, content)
                self.screenplay.update_identity_block_metadata(env_id, extras_present=requires_extras, foreground_zone="clear")
                if requires_extras:
                    self.screenplay.update_identity_block_metadata(env_id, extras_density="sparse", extras_activities="", extras_depth="background_only")
                
                # Extract environment description from the generated scene content using AI
                env_description = self._extract_environment_from_content(content, self.current_scene.title)
                self.screenplay.update_identity_block_metadata(env_id, user_notes=env_description)
                
                print(f"Created fallback environment placeholder (no environments extracted)")
            
            _elog(f"STEP 5 complete: {entities_created} total entities, {environments_extracted} environments")
            print(f"Extracted {entities_created} entities from scene content ({environments_extracted} environment(s))")
            
            # ENRICHMENT PASS: scan the full scene for additional descriptive
            # details that may have been introduced after the first mention.
            _elog("STEP 6: Enrichment pass — scanning full scene for additional entity details...")
            _update_progress("Enriching entity descriptions from full scene...")
            self._enrich_entity_descriptions_from_full_scene(content)
            _elog("STEP 6 complete.")
            
            # VALIDATION PASS (parent_vehicle): environments with parent_vehicle reference existing VEHICLE; no VEHICLE has parent_vehicle
            passed, pv_issues = self.screenplay.validate_parent_vehicle_relationships()
            if not passed and pv_issues:
                print("parent_vehicle validation:", "; ".join(pv_issues))
                # Auto-correct: ensure any environment with parent_vehicle has the vehicle created
                for entity_id, meta in list(self.screenplay.identity_block_metadata.items()):
                    if meta.get("type") != "environment":
                        continue
                    parent = (meta.get("parent_vehicle") or "").strip()
                    if not parent:
                        continue
                    if not self.screenplay.get_identity_block_by_name(parent, "vehicle"):
                        veh_id = self.screenplay.create_placeholder_identity_block(parent, "vehicle", self.current_scene.scene_id)
                        if veh_id and content:
                            notes = self._extract_entity_details_from_scene(content, parent, "vehicle")
                            if notes:
                                self.screenplay.update_identity_block_metadata(veh_id, user_notes=notes)
                        print(f"  Auto-created VEHICLE '{parent}' for environment '{meta.get('name', '')}'")
            
            # Refresh the Identity Blocks tab if it exists
            if hasattr(self, 'identity_blocks_tab') and self.identity_blocks_tab:
                self.identity_blocks_tab.refresh_entity_list()
            
            _elog(f"EXTRACTION COMPLETE — identity_block_metadata has {len(self.screenplay.identity_block_metadata)} entries")
        except Exception as e:
            _tb = traceback.format_exc()
            _elog(f"EXCEPTION in extract_entities_from_scene_content:\n{_tb}")
            print(f"Error extracting entities: {e}")
    
    def on_scene_content_error(self, error: str, progress: QProgressDialog):
        """Handle scene content generation error."""
        progress.close()
        self.generate_scene_content_btn.setEnabled(True)
        self.generate_scene_content_btn.setText("Generate with AI")
        QMessageBox.critical(self, "Error", f"Failed to generate scene content: {error}")
    
    def _merge_dialogue_blocks(self, content: str) -> str:
        """Merge orphaned character-name paragraphs with their following dialogue.

        The AI sometimes puts a blank line between a character name and their
        dialogue, splitting them into separate paragraphs. This collapses
        NAME\\n\\n"dialogue" back into NAME\\n"dialogue".
        """
        import re
        if not content or not content.strip():
            return content

        paragraphs = content.split('\n\n')
        merged = []
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i].strip()
            if (re.match(r"^[A-Z][A-Z'\-\.]+(?:[ \t]+[A-Z'\-\.]+)*$", para)
                    and i + 1 < len(paragraphs)
                    and paragraphs[i + 1].strip()[:1] in ('"', '\u201c')):
                merged.append(para + '\n' + paragraphs[i + 1].strip())
                i += 2
            else:
                merged.append(para)
                i += 1
        return '\n\n'.join(merged)

    def _add_paragraph_numbers(self, content: str) -> str:
        """Add paragraph numbers to content for display."""
        if not content or not content.strip():
            return content
        
        content = self._merge_dialogue_blocks(content)

        # Split by double newlines (paragraph breaks)
        paragraphs = content.split('\n\n')
        numbered_paragraphs = []
        
        for i, para in enumerate(paragraphs, 1):
            para = para.strip()
            if para:
                # Add paragraph number at the start
                numbered_paragraphs.append(f"[{i}] {para}")
            else:
                numbered_paragraphs.append(para)
        
        return '\n\n'.join(numbered_paragraphs)
    
    def _remove_paragraph_numbers(self, content: str) -> str:
        """Remove paragraph numbers from content before saving."""
        if not content or not content.strip():
            return content
        
        # Remove pattern like "[1] ", "[2] ", etc. at the start of paragraphs
        import re
        # Pattern matches [number] followed by space at the start of a line or after double newline
        pattern = r'(\n\n|^)\[\d+\]\s+'
        cleaned = re.sub(pattern, r'\1', content)
        return cleaned
    
    def on_tree_items_reordered(self):
        """Handle tree items being reordered via drag and drop."""
        if not self.screenplay:
            return
        
        # Store current selection before any updates
        current_item = self.tree.currentItem()
        selected_scene_id = None
        if current_item:
            data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "scene":
                selected_scene_id = data[1].scene_id
        
        # Count scenes before update to detect loss
        scenes_before = {}
        for act in self.screenplay.acts:
            for scene in act.scenes:
                scenes_before[scene.scene_id] = scene
        
        # Update the screenplay structure based on tree order
        # This reads the current tree state (after the drop) and updates the screenplay
        self.update_screenplay_from_tree()
        
        # Verify no scenes were lost
        scenes_after = {}
        for act in self.screenplay.acts:
            for scene in act.scenes:
                scenes_after[scene.scene_id] = scene
        
        lost_scenes = set(scenes_before.keys()) - set(scenes_after.keys())
        if lost_scenes:
            print(f"ERROR: Lost {len(lost_scenes)} scenes during update: {lost_scenes}")
            # Try to restore from tree
            root = self.tree.topLevelItem(0)
            if root:
                for i in range(root.childCount()):
                    act_item = root.child(i)
                    for j in range(act_item.childCount()):
                        scene_item = act_item.child(j)
                        scene_data = scene_item.data(0, Qt.ItemDataRole.UserRole)
                        if scene_data and scene_data[0] == "scene":
                            scene = scene_data[1]
                            if scene.scene_id in lost_scenes:
                                # Find the act and add the scene back
                                for act in self.screenplay.acts:
                                    if act_item.data(0, Qt.ItemDataRole.UserRole)[1] == act:
                                        if scene not in act.scenes:
                                            act.scenes.append(scene)
                                            print(f"Restored scene {scene.title} to act {act.act_number}")
        
        # Renumber acts and scenes to maintain continuity
        self.renumber_acts()
        for act in self.screenplay.acts:
            self.renumber_scenes_in_act(act)
        
        # Update tree labels to reflect new numbers (but don't rebuild structure)
        # The tree widget already has the correct structure from the drop
        self._update_tree_labels()
        
        # Restore selection
        if selected_scene_id:
            self._select_scene_by_id(selected_scene_id)
        
        # Timeline visualization removed - method no longer exists
        # self.update_timeline_visualization()
    
    def _update_tree_labels(self):
        """Update tree item labels to reflect current act/scene numbers without rebuilding structure."""
        root = self.tree.topLevelItem(0)
        if not root:
            return
        
        for i in range(root.childCount()):
            act_item = root.child(i)
            act_data = act_item.data(0, Qt.ItemDataRole.UserRole)
            if act_data and act_data[0] == "act":
                act = act_data[1]
                # Update act label
                act_item.setText(0, f"Act {act.act_number}: {act.title}")
                
                # Update scene labels
                for j in range(act_item.childCount()):
                    scene_item = act_item.child(j)
                    scene_data = scene_item.data(0, Qt.ItemDataRole.UserRole)
                    if scene_data and scene_data[0] == "scene":
                        scene = scene_data[1]
                        # Update scene label
                        completion_icon = "✓" if scene.is_complete else "○"
                        plot_point_indicator = f" [{scene.plot_point}]" if scene.plot_point else ""
                        pacing_indicator = f" ({scene.pacing})" if scene.pacing else ""
                        scene_item.setText(0, f"{completion_icon} Scene {scene.scene_number}: {scene.title}{plot_point_indicator}{pacing_indicator}")
    
    def _select_scene_by_id(self, scene_id: str):
        """Select a scene in the tree by its ID."""
        root = self.tree.topLevelItem(0)
        if not root:
            return
        
        for i in range(root.childCount()):
            act_item = root.child(i)
            for j in range(act_item.childCount()):
                scene_item = act_item.child(j)
                scene_data = scene_item.data(0, Qt.ItemDataRole.UserRole)
                if scene_data and scene_data[0] == "scene" and scene_data[1].scene_id == scene_id:
                    self.tree.setCurrentItem(scene_item)
                    self.tree.expandItem(act_item)
                    return
    
    def update_screenplay_from_tree(self):
        """Update screenplay structure based on tree order."""
        if not self.screenplay:
            return
        
        # Get root item
        root = self.tree.topLevelItem(0)
        if not root:
            return
        
        # Collect all scenes first to ensure we don't lose any
        # Use a dictionary to track scenes by ID - this is our source of truth
        all_scenes = {}
        for act in self.screenplay.acts:
            for scene in act.scenes:
                all_scenes[scene.scene_id] = scene
        
        original_scene_ids = set(all_scenes.keys())
        original_scene_count = len(all_scenes)
        
        # Rebuild acts list based on tree order
        new_acts = []
        scenes_found_in_tree = set()
        
        for i in range(root.childCount()):
            act_item = root.child(i)
            data = act_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "act":
                act = data[1]
                # Update scenes order based on tree
                new_scenes = []
                for j in range(act_item.childCount()):
                    scene_item = act_item.child(j)
                    scene_data = scene_item.data(0, Qt.ItemDataRole.UserRole)
                    if scene_data and scene_data[0] == "scene":
                        scene = scene_data[1]
                        scene_id = scene.scene_id
                        scenes_found_in_tree.add(scene_id)
                        
                        # CRITICAL: Always use the scene from our collection to preserve all data
                        # The scene object from tree might be a reference, but we want the original
                        if scene_id in all_scenes:
                            new_scenes.append(all_scenes[scene_id])
                        else:
                            # Scene not in collection - this shouldn't happen, but preserve it
                            print(f"Warning: Scene {scene_id} ({scene.title}) not in collection, adding it")
                            all_scenes[scene_id] = scene
                            new_scenes.append(scene)
                
                # Update the act's scenes list
                act.scenes = new_scenes
                new_acts.append(act)
        
        # CRITICAL: Check for lost scenes and preserve them
        lost_scenes = original_scene_ids - scenes_found_in_tree
        if lost_scenes:
            print(f"ERROR: {len(lost_scenes)} scenes lost during tree update!")
            for lost_id in lost_scenes:
                lost_scene = all_scenes[lost_id]
                print(f"  - Lost: {lost_scene.title} (ID: {lost_id})")
                # Try to restore by finding the act it was originally in
                # Add it back to the first act as a fallback (better than losing it)
                if new_acts:
                    # Check if scene was in this act before
                    for act in new_acts:
                        # If we can't determine, add to first act
                        if lost_scene not in act.scenes:
                            act.scenes.append(lost_scene)
                            print(f"  - Restored '{lost_scene.title}' to act {act.act_number}")
                            break
        
        # Update the screenplay's acts list
        self.screenplay.acts = new_acts
        
        # Final verification
        final_scene_count = sum(len(act.scenes) for act in self.screenplay.acts)
        if final_scene_count < original_scene_count:
            print(f"ERROR: Scene count mismatch! Had {original_scene_count}, now have {final_scene_count}")
    
    def on_tree_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        
        if not data:
            # Root item - can only add act
            add_act_action = QAction("Add Act", self)
            add_act_action.triggered.connect(self.on_add_act_clicked)
            menu.addAction(add_act_action)
        else:
            item_type, item_obj = data
            if item_type == "act":
                # Act context menu
                add_scene_action = QAction("Add Scene", self)
                add_scene_action.triggered.connect(lambda: self.on_add_scene_clicked(item_obj))
                menu.addAction(add_scene_action)
                menu.addSeparator()
                delete_act_action = QAction("Delete Act", self)
                delete_act_action.triggered.connect(lambda: self.on_delete_act_clicked(item_obj))
                menu.addAction(delete_act_action)
            elif item_type == "scene":
                # Scene context menu
                delete_scene_action = QAction("Delete Scene", self)
                delete_scene_action.triggered.connect(lambda: self.on_delete_scene_clicked(item_obj))
                menu.addAction(delete_scene_action)
        
        menu.exec(self.tree.mapToGlobal(position))
    
    def on_add_act_clicked(self):
        """Add a new act."""
        if not self.screenplay:
            QMessageBox.warning(self, "No Screenplay", "No screenplay loaded.")
            return
        
        # Get act title
        title, ok = QInputDialog.getText(self, "Add Act", "Enter act title:", text="New Act")
        if not ok or not title.strip():
            return
        
        # Create new act
        from datetime import datetime
        from core.screenplay_engine import StoryAct
        
        # Determine act number (next available)
        existing_acts = sorted(self.screenplay.acts, key=lambda x: x.act_number)
        act_number = existing_acts[-1].act_number + 1 if existing_acts else 1
        
        new_act = StoryAct(
            act_number=act_number,
            title=title.strip(),
            description="",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        self.screenplay.acts.append(new_act)
        self.renumber_acts()
        self.update_tree()
        # Timeline visualization removed - method no longer exists
        # self.update_timeline_visualization()
    
    def on_add_scene_clicked(self, act=None):
        """Add a new scene to an act."""
        if not self.screenplay:
            QMessageBox.warning(self, "No Screenplay", "No screenplay loaded.")
            return
        
        # Determine which act to add to
        if not act:
            current_item = self.tree.currentItem()
            if not current_item:
                QMessageBox.warning(self, "No Selection", "Please select an act first.")
                return
            
            data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                QMessageBox.warning(self, "Invalid Selection", "Please select an act to add a scene to.")
                return
            
            item_type, item_obj = data
            if item_type == "scene":
                # If scene selected, get its parent act
                parent_item = current_item.parent()
                if parent_item:
                    parent_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
                    if parent_data:
                        act = parent_data[1]
            elif item_type == "act":
                act = item_obj
        
        if not act:
            QMessageBox.warning(self, "No Act", "Please select an act first.")
            return
        
        # Get scene title
        title, ok = QInputDialog.getText(self, "Add Scene", "Enter scene title:", text="New Scene")
        if not ok or not title.strip():
            return
        
        # Create new scene
        from datetime import datetime
        import uuid
        from core.screenplay_engine import StoryScene
        
        # Determine scene number (next available in act)
        existing_scenes = sorted(act.scenes, key=lambda x: x.scene_number)
        scene_number = existing_scenes[-1].scene_number + 1 if existing_scenes else 1
        
        new_scene = StoryScene(
            scene_id=str(uuid.uuid4()),
            scene_number=scene_number,
            title=title.strip(),
            description="",
            pacing="Medium",
            estimated_duration=60,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        act.add_scene(new_scene)
        self.renumber_scenes_in_act(act)
        self.update_tree()
        # Timeline visualization removed - method no longer exists
        # self.update_timeline_visualization()
    
    def on_delete_act_clicked(self, act: StoryAct):
        """Delete an act."""
        if not self.screenplay:
            return
        
        reply = QMessageBox.question(
            self, "Delete Act",
            f"Are you sure you want to delete '{act.title}'?\n\nThis will also delete all scenes in this act.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.screenplay.acts.remove(act)
            self.renumber_acts()
            self.update_tree()
            # Timeline visualization removed
            self.current_scene = None
            self.clear_scene_data()
    
    def on_delete_scene_clicked(self, scene: StoryScene):
        """Delete a scene."""
        if not self.screenplay:
            return
        
        # Find the act containing this scene
        act = None
        for a in self.screenplay.acts:
            if scene in a.scenes:
                act = a
                break
        
        if not act:
            return
        
        reply = QMessageBox.question(
            self, "Delete Scene",
            f"Are you sure you want to delete '{scene.title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            act.scenes.remove(scene)
            self.renumber_scenes_in_act(act)
            self.update_tree()
            # Timeline visualization removed
            if self.current_scene == scene:
                self.current_scene = None
                self.clear_scene_data()
    
    def renumber_acts(self):
        """Renumber all acts to maintain continuity."""
        if not self.screenplay:
            return
        
        sorted_acts = sorted(self.screenplay.acts, key=lambda x: x.act_number)
        for i, act in enumerate(sorted_acts, start=1):
            act.act_number = i
            from datetime import datetime
            act.updated_at = datetime.now().isoformat()
    
    def renumber_scenes_in_act(self, act: StoryAct):
        """Renumber scenes in an act to maintain continuity."""
        sorted_scenes = sorted(act.scenes, key=lambda x: x.scene_number)
        for i, scene in enumerate(sorted_scenes, start=1):
            scene.scene_number = i
            from datetime import datetime
            scene.updated_at = datetime.now().isoformat()
    
    def refresh(self):
        """Refresh the display."""
        try:
            from debug_log import debug_log, debug_exception
            debug_log("refresh() started")
        except:
            pass
        
        try:
            debug_log("Updating tree...")
            self.update_tree()
            debug_log("Tree updated")
            # Timeline visualization removed - method no longer exists
            # self.update_timeline_visualization()
            if self.current_scene:
                debug_log("Loading scene data...")
                self.load_scene_data(self.current_scene)
                debug_log("Scene data loaded")
            debug_log("refresh() completed successfully")
        except Exception as e:
            try:
                debug_exception("Error in refresh()", e)
            except:
                pass
            try:
                log_exception("Error refreshing framework view", e)
            except:
                pass
            # Don't show message box here as it might cause recursion
            # Just log the error
    
    def on_identity_blocks_changed(self):
        """Handle identity blocks being updated."""
        # Refresh the identity blocks manager to show updated status
        if hasattr(self, 'identity_block_manager') and self.screenplay:
            self.identity_block_manager.refresh_entity_list()
    
