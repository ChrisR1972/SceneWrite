"""
Spell checking utilities for text input widgets.
"""

from PyQt6.QtGui import QTextCharFormat, QSyntaxHighlighter, QColor, QTextCursor, QAction
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QMessageBox
import sys
import subprocess
import os
from typing import Optional
import re

# Try to import spellchecker, but make it optional
try:
    from spellchecker import SpellChecker
    SPELL_CHECKER_AVAILABLE = True
except ImportError:
    SpellChecker = None
    SPELL_CHECKER_AVAILABLE = False

_SPELLCHECKER_INSTALL_ATTEMPTED = False
_SPELLCHECKER_MISSING_WARNED = False
_SPELLCHECKER_ERROR_WARNED = False


def _log_spellcheck(message: str):
    """Log spellcheck diagnostics to a file."""
    try:
        log_path = os.path.join(os.getcwd(), "spellcheck_debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def _warn_spellcheck(parent, message: str):
    """Show a single warning message about spellcheck issues."""
    global _SPELLCHECKER_ERROR_WARNED
    if _SPELLCHECKER_ERROR_WARNED:
        return
    _SPELLCHECKER_ERROR_WARNED = True
    try:
        QMessageBox.warning(parent, "Spell Check Issue", message)
    except Exception:
        pass


def _ensure_spellchecker_available() -> bool:
    """Ensure pyspellchecker is available; attempt install once if missing."""
    global SPELL_CHECKER_AVAILABLE, SpellChecker, _SPELLCHECKER_INSTALL_ATTEMPTED
    
    if SPELL_CHECKER_AVAILABLE:
        return True
    
    if _SPELLCHECKER_INSTALL_ATTEMPTED:
        return False
    
    _SPELLCHECKER_INSTALL_ATTEMPTED = True
    try:
        # Attempt to install pyspellchecker into the current environment
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyspellchecker"],
            check=False,
            capture_output=True,
            timeout=20
        )
        from spellchecker import SpellChecker as _SpellChecker
        SpellChecker = _SpellChecker
        SPELL_CHECKER_AVAILABLE = True
        return True
    except Exception:
        return False


class SpellCheckHighlighter(QSyntaxHighlighter):
    """Syntax highlighter that marks misspelled words."""
    
    def __init__(self, parent=None, spell_checker=None):
        super().__init__(parent)
        if spell_checker is None:
            if not SPELL_CHECKER_AVAILABLE:
                raise ImportError("spellchecker library not available")
            spell_checker = SpellChecker()
        self.spell_checker = spell_checker
        self.misspelled_format = QTextCharFormat()
        # Set the standard spell check underline (no background highlight)
        self.misspelled_format.setUnderlineColor(QColor(255, 0, 0))  # Red underline
        self.misspelled_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        
        # Word pattern: letters, apostrophes, hyphens (for contractions and hyphenated words)
        self.word_pattern = re.compile(r'\b[a-zA-Z\'-]+\b')

    def highlightBlock(self, text_block):
        """Highlight misspelled words in the text block."""
        # QSyntaxHighlighter.highlightBlock receives a QTextBlock, not a string
        # We need to get the text from the block
        try:
            text_str = text_block.text()
        except AttributeError:
            # Fallback if it's already a string (shouldn't happen, but be safe)
            text_str = str(text_block) if text_block else ""
        
        if not text_str:
            return
        
        # Collect all words first for batch checking (more efficient)
        ignore_set = set()
        try:
            ignore_set = set(self.document().property("spell_ignore_words") or [])
        except Exception:
            ignore_set = set()
        words_to_check = []
        word_positions = []
        
        for match in self.word_pattern.finditer(text_str):
            word = match.group()
            # Clean word (remove leading/trailing punctuation that might be part of the word)
            clean_word = word.strip("'-")
            
            # Skip ignored words
            if clean_word.lower() in ignore_set:
                continue
            
            # Skip if too short, all caps (likely acronyms), or contains numbers
            if len(clean_word) < 2:
                continue
            if clean_word.isupper() and len(clean_word) > 1:
                continue
            if any(char.isdigit() for char in clean_word):
                continue
            
            words_to_check.append(clean_word.lower())
            word_positions.append((match.start(), match.end() - match.start()))
        
        # Batch check all words at once (more efficient)
        if words_to_check:
            misspelled_set = self.spell_checker.unknown(words_to_check)
            
            # Highlight misspelled words
            for i, (start, length) in enumerate(word_positions):
                if words_to_check[i] in misspelled_set:
                    self.setFormat(start, length, self.misspelled_format)


class CinematicMarkupHighlighter(QSyntaxHighlighter):
    """Combined syntax highlighter for spell checking AND cinematic markup token detection.
    
    Underline styles:
    - Misspelled words: red wavy underline (spell check)
    - Unknown actions: blue wavy underline (unmarked verb from whitelist)
    - Unknown SFX: green wavy underline (unmarked sound effect)
    - Unknown identity: orange wavy underline (untagged proper noun)
    
    Only ONE QSyntaxHighlighter can be attached to a document at a time,
    so this class combines both spell-check and cinematic markup detection.
    """
    
    def __init__(self, parent=None, spell_checker=None):
        super().__init__(parent)
        
        # Spell checker setup
        self.spell_checker = spell_checker
        self.cinematic_enabled = True
        
        # Spell check format: red wavy underline
        self.misspelled_format = QTextCharFormat()
        self.misspelled_format.setUnderlineColor(QColor(255, 0, 0))
        self.misspelled_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        
        # Unknown action format: blue wavy underline
        self.unknown_action_format = QTextCharFormat()
        self.unknown_action_format.setUnderlineColor(QColor(60, 130, 255))
        self.unknown_action_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        
        # Unknown SFX format: green wavy underline
        self.unknown_sfx_format = QTextCharFormat()
        self.unknown_sfx_format.setUnderlineColor(QColor(50, 200, 80))
        self.unknown_sfx_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        
        # Unknown identity format: orange wavy underline
        self.unknown_identity_format = QTextCharFormat()
        self.unknown_identity_format.setUnderlineColor(QColor(240, 160, 40))
        self.unknown_identity_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        
        # Word pattern for spell checking
        self.word_pattern = re.compile(r'\b[a-zA-Z\'-]+\b')
        
        # Instance-level ignore set for cinematic tokens
        self._cinematic_ignore_words: set = set()
    
    def set_cinematic_ignore_words(self, words: set):
        """Set the instance-level ignore set for cinematic token detection."""
        self._cinematic_ignore_words = set(words)
    
    def add_cinematic_ignore_word(self, word: str):
        """Add a single word to the cinematic ignore set."""
        self._cinematic_ignore_words.add(word)
        self._cinematic_ignore_words.add(word.lower())
    
    def set_cinematic_enabled(self, enabled: bool):
        """Enable or disable cinematic markup highlighting."""
        self.cinematic_enabled = enabled
    
    def highlightBlock(self, text_block):
        """Highlight misspelled words AND unmarked cinematic tokens."""
        try:
            text_str = text_block.text()
        except AttributeError:
            text_str = str(text_block) if text_block else ""
        
        if not text_str:
            return
        
        # ── SPELL CHECK PASS ──
        if self.spell_checker:
            self._highlight_spelling(text_str)
        
        # ── CINEMATIC MARKUP PASS ──
        if self.cinematic_enabled:
            self._highlight_cinematic(text_str)
    
    def _highlight_spelling(self, text_str: str):
        """Apply spell-check highlighting."""
        ignore_set = set()
        try:
            ignore_set = set(self.document().property("spell_ignore_words") or [])
        except Exception:
            ignore_set = set()
        
        words_to_check = []
        word_positions = []
        
        for match in self.word_pattern.finditer(text_str):
            word = match.group()
            clean_word = word.strip("'-")
            
            if clean_word.lower() in ignore_set:
                continue
            if len(clean_word) < 2:
                continue
            if clean_word.isupper() and len(clean_word) > 1:
                continue
            if any(char.isdigit() for char in clean_word):
                continue
            
            words_to_check.append(clean_word.lower())
            word_positions.append((match.start(), match.end() - match.start()))
        
        if words_to_check:
            try:
                misspelled_set = self.spell_checker.unknown(words_to_check)
                for i, (start, length) in enumerate(word_positions):
                    if words_to_check[i] in misspelled_set:
                        self.setFormat(start, length, self.misspelled_format)
            except Exception:
                pass
    
    def _highlight_cinematic(self, text_str: str):
        """Apply cinematic token highlighting (unmarked actions, SFX, identities)."""
        try:
            from core.cinematic_token_detector import detect_line_tokens
            tokens = detect_line_tokens(text_str, self._cinematic_ignore_words)
            
            for token in tokens:
                if token.token_type == "unknown_action":
                    self.setFormat(token.start, token.length, self.unknown_action_format)
                elif token.token_type == "unknown_sfx":
                    self.setFormat(token.start, token.length, self.unknown_sfx_format)
                elif token.token_type == "unknown_identity":
                    self.setFormat(token.start, token.length, self.unknown_identity_format)
        except Exception:
            pass


def _match_case(original: str, suggestion: str) -> str:
    """Match suggestion case to the original word."""
    if not original:
        return suggestion
    if original.isupper():
        return suggestion.upper()
    if original[0].isupper():
        return suggestion.capitalize()
    return suggestion


def _rank_suggestions(spell_checker: SpellChecker, word: str, candidates: set) -> list:
    """Rank suggestions by frequency and similarity."""
    if not candidates:
        return []
    # Remove exact match if present
    candidates = {c for c in candidates if c.lower() != word.lower()}
    try:
        return sorted(
            candidates,
            key=lambda c: spell_checker.word_frequency.frequency(c),
            reverse=True,
        )
    except Exception:
        return sorted(candidates)


def enable_cinematic_checking(text_widget):
    """Enable combined spell-check + cinematic markup highlighting for a text widget.
    
    Uses CinematicMarkupHighlighter (combined highlighter) and does NOT set up
    the spell-check context menu — the calling widget is expected to handle
    its own context menu (e.g. SceneContentTextEdit).
    
    Returns the CinematicMarkupHighlighter instance, or None on failure.
    """
    spell_checker_obj = None
    if _ensure_spellchecker_available():
        try:
            spell_checker_obj = SpellChecker()
        except Exception:
            pass
    
    try:
        if not hasattr(text_widget, 'document'):
            return None
        
        document = text_widget.document()
        if document is None:
            return None
        
        highlighter = CinematicMarkupHighlighter(document, spell_checker_obj)
        text_widget.setProperty("spell_highlighter", highlighter)
        text_widget.setProperty("cinematic_highlighter", highlighter)
        if spell_checker_obj:
            text_widget.setProperty("spell_checker", spell_checker_obj)
        if document.property("spell_ignore_words") is None:
            document.setProperty("spell_ignore_words", set())
        
        from PyQt6.QtCore import QTimer
        
        timer = QTimer()
        timer.setSingleShot(True)
        def do_rehighlight():
            try:
                highlighter.rehighlight()
            except Exception:
                pass
        timer.timeout.connect(do_rehighlight)
        
        def on_text_changed():
            timer.stop()
            timer.start(400)
        
        if hasattr(text_widget, 'textChanged'):
            text_widget.textChanged.connect(on_text_changed)
        
        text_widget.setProperty("spell_check_timer", timer)
        
        QTimer.singleShot(300, do_rehighlight)
        
        return highlighter
    except Exception:
        return None


def enable_spell_checking(text_widget):
    """Enable spell checking for a QTextEdit or QPlainTextEdit widget."""
    global _SPELLCHECKER_MISSING_WARNED
    if not _ensure_spellchecker_available():
        # Spell checker not available - warn once and fail gracefully
        if not _SPELLCHECKER_MISSING_WARNED:
            _SPELLCHECKER_MISSING_WARNED = True
            _warn_spellcheck(
                text_widget.window() if hasattr(text_widget, "window") else text_widget,
                "Spell checker dependency is missing. Please install 'pyspellchecker' and restart the app."
            )
        return None
    
    try:
        # Check if widget has a document (QTextEdit/QPlainTextEdit)
        if not hasattr(text_widget, 'document'):
            return None
        
        # Get or create the document
        document = text_widget.document()
        if document is None:
            return None
        
        try:
            spell_checker = SpellChecker()
        except Exception as e:
            _log_spellcheck(f"SpellChecker init error: {e}")
            _warn_spellcheck(
                text_widget.window() if hasattr(text_widget, "window") else text_widget,
                "Spell checker failed to initialize. Please reinstall 'pyspellchecker' and restart the app."
            )
            return None
        highlighter = SpellCheckHighlighter(document, spell_checker)
        text_widget.setProperty("spell_highlighter", highlighter)  # Keep reference
        text_widget.setProperty("spell_checker", spell_checker)  # For context menu suggestions
        if document.property("spell_ignore_words") is None:
            document.setProperty("spell_ignore_words", set())
        
        # QSyntaxHighlighter should automatically re-highlight when document changes
        # But we need to ensure it's triggered. Let's connect to both document and widget signals
        from PyQt6.QtCore import QTimer
        
        # Create a debounced rehighlight function
        timer = QTimer()
        timer.setSingleShot(True)
        def do_rehighlight():
            try:
                highlighter.rehighlight()
            except Exception:
                pass
        timer.timeout.connect(do_rehighlight)
        
        def on_text_changed():
            # Stop any pending rehighlight and start a new one
            timer.stop()
            timer.start(300)  # Wait 300ms after user stops typing
        
        # Connect to textChanged signal
        if hasattr(text_widget, 'textChanged'):
            text_widget.textChanged.connect(on_text_changed)
        
        # Also try connecting to document's contentsChange signal directly
        try:
            def on_contents_change(pos, removed, added):
                highlighter.rehighlight()
            document.contentsChange.connect(on_contents_change)
        except Exception:
            pass
        
        # Store timer to keep it alive
        text_widget.setProperty("spell_check_timer", timer)
        
        # Force initial re-highlighting of the entire document after a short delay
        # This ensures the widget is fully initialized
        def do_initial_highlight():
            try:
                highlighter.rehighlight()
            except Exception:
                pass
        
        QTimer.singleShot(200, do_initial_highlight)

        # Add right-click suggestions for misspelled words (once)
        if not text_widget.property("spell_context_menu_enabled"):
            def show_spellcheck_menu(pos):
                try:
                    cursor = text_widget.cursorForPosition(pos)
                    cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                    original_word = cursor.selectedText()
                    
                    # Build standard menu first
                    menu = text_widget.createStandardContextMenu()
                    
                    if not original_word:
                        menu.exec(text_widget.mapToGlobal(pos))
                        return
                    
                    clean_word = original_word.strip("'-")
                    if not clean_word:
                        menu.exec(text_widget.mapToGlobal(pos))
                        return
                    
                    misspelled = clean_word.lower() in spell_checker.unknown([clean_word.lower()])
                    if not misspelled:
                        menu.exec(text_widget.mapToGlobal(pos))
                        return
                    
                    candidates = spell_checker.candidates(clean_word) or set()
                    suggestions = _rank_suggestions(spell_checker, clean_word, candidates)[:5]
                    
                    first_action = menu.actions()[0] if menu.actions() else None
                    
                    if suggestions:
                        for suggestion in suggestions:
                            replacement = _match_case(original_word, suggestion)
                            action = QAction(replacement, menu)
                            start = cursor.selectionStart()
                            end = cursor.selectionEnd()
                            
                            def apply_replacement(checked=False, replacement=replacement, start=start, end=end):
                                replace_cursor = text_widget.textCursor()
                                replace_cursor.setPosition(start)
                                replace_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                                replace_cursor.insertText(replacement)
                            
                            action.triggered.connect(apply_replacement)
                            if first_action:
                                menu.insertAction(first_action, action)
                            else:
                                menu.addAction(action)
                        
                        if first_action:
                            menu.insertSeparator(first_action)
                        else:
                            menu.addSeparator()
                    else:
                        no_action = QAction("No suggestions", menu)
                        no_action.setEnabled(False)
                        if first_action:
                            menu.insertAction(first_action, no_action)
                            menu.insertSeparator(first_action)
                        else:
                            menu.addAction(no_action)
                            menu.addSeparator()
                    
                    # Add dictionary actions
                    add_action = QAction("Add to dictionary", menu)
                    ignore_action = QAction("Ignore word", menu)
                    
                    def add_to_dictionary(checked=False, word=clean_word.lower()):
                        try:
                            spell_checker.word_frequency.add(word)
                            highlighter.rehighlight()
                        except Exception:
                            pass
                    
                    def ignore_word(checked=False, word=clean_word.lower()):
                        try:
                            ignore_words = set(document.property("spell_ignore_words") or [])
                            ignore_words.add(word)
                            document.setProperty("spell_ignore_words", ignore_words)
                            highlighter.rehighlight()
                        except Exception:
                            pass
                    
                    add_action.triggered.connect(add_to_dictionary)
                    ignore_action.triggered.connect(ignore_word)
                    
                    if first_action:
                        menu.insertAction(first_action, add_action)
                        menu.insertAction(first_action, ignore_action)
                        menu.insertSeparator(first_action)
                    else:
                        menu.addAction(add_action)
                        menu.addAction(ignore_action)
                        menu.addSeparator()
                    
                    menu.exec(text_widget.mapToGlobal(pos))
                except Exception:
                    # Fall back to standard menu if anything goes wrong
                    standard_menu = text_widget.createStandardContextMenu()
                    standard_menu.exec(text_widget.mapToGlobal(pos))
            
            text_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            text_widget.customContextMenuRequested.connect(show_spellcheck_menu)
            text_widget.setProperty("spell_context_menu_enabled", True)
        
        return highlighter
    except Exception:
        return None

