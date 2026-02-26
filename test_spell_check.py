"""Test script to verify spell checking works."""
import sys
from PyQt6.QtWidgets import QApplication, QTextEdit, QVBoxLayout, QWidget
from core.spell_checker import enable_spell_checking, SPELL_CHECKER_AVAILABLE

print(f"Spell checker available: {SPELL_CHECKER_AVAILABLE}")

if not SPELL_CHECKER_AVAILABLE:
    print("ERROR: Spell checker library not installed!")
    print("Please run: pip install pyspellchecker")
    sys.exit(1)

app = QApplication(sys.argv)

window = QWidget()
layout = QVBoxLayout(window)

text_edit = QTextEdit()
text_edit.setPlainText("This is a test with some misspelled wrds like teest and wrrong.")
layout.addWidget(text_edit)

# Enable spell checking
result = enable_spell_checking(text_edit)
if result:
    print("Spell checking enabled successfully!")
    print(f"Highlighter: {result}")
else:
    print("ERROR: Failed to enable spell checking!")

window.setWindowTitle("Spell Check Test")
window.resize(600, 400)
window.show()

print("\nType some misspelled words in the text box above.")
print("They should appear with red wavy underlines.")
print("Press Ctrl+C to exit.")

sys.exit(app.exec())

