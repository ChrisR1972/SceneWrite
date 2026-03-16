"""
Series Bible Editor for the Episodic Series System.

Provides a tabbed dialog for viewing and editing all persistent narrative
elements in a Series Bible: characters, locations, world context, objects,
factions, timeline, and episode history.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QTextEdit, QPushButton, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QMessageBox,
    QSplitter, QScrollArea, QSizePolicy, QComboBox, QSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Optional, Dict, Any, List

from core.series_bible import SeriesBible


class SeriesBibleEditor(QDialog):
    """Dialog for viewing and editing a Series Bible."""

    bible_saved = pyqtSignal()

    def __init__(self, bible: SeriesBible, series_folder: str, parent=None):
        super().__init__(parent)
        self.bible = bible
        self.series_folder = series_folder
        self._dirty = False
        self.init_ui()
        self._load_bible()

    def init_ui(self):
        self.setWindowTitle(f"Series Bible — {self.bible.series_title}")
        self.setMinimumSize(750, 550)
        self.resize(850, 620)

        layout = QVBoxLayout(self)

        # Series title
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Series Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.textChanged.connect(self._mark_dirty)
        title_row.addWidget(self.title_edit, 1)
        layout.addLayout(title_row)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_characters_tab(), "Characters")
        self.tabs.addTab(self._build_locations_tab(), "Locations")
        self.tabs.addTab(self._build_world_tab(), "World Context")
        self.tabs.addTab(self._build_objects_tab(), "Objects && Props")
        self.tabs.addTab(self._build_factions_tab(), "Factions")
        self.tabs.addTab(self._build_timeline_tab(), "Timeline")
        self.tabs.addTab(self._build_episodes_tab(), "Episodes")
        layout.addWidget(self.tabs, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ── Tab builders ─────────────────────────────────────────────────

    def _build_characters_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        self.char_list = QListWidget()
        self.char_list.currentRowChanged.connect(self._on_char_selected)
        layout.addWidget(self.char_list, 1)

        detail = QWidget()
        form = QFormLayout(detail)
        self.char_name = QLineEdit(); form.addRow("Name:", self.char_name)
        self.char_role = QComboBox(); self.char_role.addItems(["main", "supporting"]); form.addRow("Role:", self.char_role)
        self.char_species = QLineEdit(); form.addRow("Species:", self.char_species)
        self.char_appearance = QTextEdit(); self.char_appearance.setMaximumHeight(80); form.addRow("Appearance:", self.char_appearance)
        self.char_traits = QLineEdit(); self.char_traits.setPlaceholderText("Comma-separated traits"); form.addRow("Traits:", self.char_traits)
        self.char_arc = QTextEdit(); self.char_arc.setMaximumHeight(60); form.addRow("Growth Arc:", self.char_arc)
        self.char_relationships = QTextEdit(); self.char_relationships.setMaximumHeight(60)
        self.char_relationships.setPlaceholderText("One per line: TargetName | type | description")
        form.addRow("Relationships:", self.char_relationships)

        char_btn_row = QHBoxLayout()
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add_character)
        update_btn = QPushButton("Update"); update_btn.clicked.connect(self._update_character)
        remove_btn = QPushButton("Remove"); remove_btn.clicked.connect(self._remove_character)
        char_btn_row.addWidget(add_btn); char_btn_row.addWidget(update_btn); char_btn_row.addWidget(remove_btn)
        form.addRow(char_btn_row)

        layout.addWidget(detail, 2)
        return w

    def _build_locations_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        self.loc_list = QListWidget()
        self.loc_list.currentRowChanged.connect(self._on_loc_selected)
        layout.addWidget(self.loc_list, 1)

        detail = QWidget()
        form = QFormLayout(detail)
        self.loc_name = QLineEdit(); form.addRow("Name:", self.loc_name)
        self.loc_desc = QTextEdit(); self.loc_desc.setMaximumHeight(80); form.addRow("Description:", self.loc_desc)
        self.loc_struct = QTextEdit(); self.loc_struct.setMaximumHeight(80); form.addRow("Characteristics:", self.loc_struct)

        loc_btn_row = QHBoxLayout()
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add_location)
        update_btn = QPushButton("Update"); update_btn.clicked.connect(self._update_location)
        remove_btn = QPushButton("Remove"); remove_btn.clicked.connect(self._remove_location)
        loc_btn_row.addWidget(add_btn); loc_btn_row.addWidget(update_btn); loc_btn_row.addWidget(remove_btn)
        form.addRow(loc_btn_row)

        layout.addWidget(detail, 2)
        return w

    def _build_world_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.world_setting = QTextEdit(); self.world_setting.setMaximumHeight(100)
        form.addRow("Setting Description:", self.world_setting)
        self.world_period = QLineEdit(); form.addRow("Time Period:", self.world_period)
        self.world_rules = QTextEdit(); self.world_rules.setMaximumHeight(120)
        form.addRow("Rules / Lore:", self.world_rules)
        self.world_tone = QLineEdit(); form.addRow("Tone:", self.world_tone)

        # Episode duration setting
        dur_row = QWidget()
        dur_layout = QHBoxLayout(dur_row)
        dur_layout.setContentsMargins(0, 0, 0, 0)
        self.ep_dur_minutes = QSpinBox(); self.ep_dur_minutes.setRange(0, 30); self.ep_dur_minutes.setSuffix(" min")
        self.ep_dur_seconds = QSpinBox(); self.ep_dur_seconds.setRange(0, 59); self.ep_dur_seconds.setSuffix(" sec")
        dur_layout.addWidget(self.ep_dur_minutes)
        dur_layout.addWidget(self.ep_dur_seconds)
        dur_layout.addWidget(QLabel("(0 = use preset lengths)"))
        dur_layout.addStretch()
        form.addRow("Episode Duration:", dur_row)

        for widget in (self.world_setting, self.world_period, self.world_rules, self.world_tone):
            if isinstance(widget, QTextEdit):
                widget.textChanged.connect(self._mark_dirty)
            else:
                widget.textChanged.connect(self._mark_dirty)
        self.ep_dur_minutes.valueChanged.connect(self._mark_dirty)
        self.ep_dur_seconds.valueChanged.connect(self._mark_dirty)
        return w

    def _build_objects_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        self.obj_list = QListWidget()
        self.obj_list.currentRowChanged.connect(self._on_obj_selected)
        layout.addWidget(self.obj_list, 1)

        detail = QWidget()
        form = QFormLayout(detail)
        self.obj_name = QLineEdit(); form.addRow("Name:", self.obj_name)
        self.obj_desc = QTextEdit(); self.obj_desc.setMaximumHeight(60); form.addRow("Description:", self.obj_desc)
        self.obj_visual = QTextEdit(); self.obj_visual.setMaximumHeight(60); form.addRow("Visual:", self.obj_visual)
        self.obj_function = QTextEdit(); self.obj_function.setMaximumHeight(60); form.addRow("Function:", self.obj_function)

        obj_btn_row = QHBoxLayout()
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add_object)
        update_btn = QPushButton("Update"); update_btn.clicked.connect(self._update_object)
        remove_btn = QPushButton("Remove"); remove_btn.clicked.connect(self._remove_object)
        obj_btn_row.addWidget(add_btn); obj_btn_row.addWidget(update_btn); obj_btn_row.addWidget(remove_btn)
        form.addRow(obj_btn_row)

        layout.addWidget(detail, 2)
        return w

    def _build_factions_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        self.fac_list = QListWidget()
        self.fac_list.currentRowChanged.connect(self._on_fac_selected)
        layout.addWidget(self.fac_list, 1)

        detail = QWidget()
        form = QFormLayout(detail)
        self.fac_name = QLineEdit(); form.addRow("Name:", self.fac_name)
        self.fac_desc = QTextEdit(); self.fac_desc.setMaximumHeight(60); form.addRow("Description:", self.fac_desc)
        self.fac_members = QLineEdit(); self.fac_members.setPlaceholderText("Comma-separated"); form.addRow("Members:", self.fac_members)
        self.fac_goals = QTextEdit(); self.fac_goals.setMaximumHeight(60); form.addRow("Goals:", self.fac_goals)

        fac_btn_row = QHBoxLayout()
        add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add_faction)
        update_btn = QPushButton("Update"); update_btn.clicked.connect(self._update_faction)
        remove_btn = QPushButton("Remove"); remove_btn.clicked.connect(self._remove_faction)
        fac_btn_row.addWidget(add_btn); fac_btn_row.addWidget(update_btn); fac_btn_row.addWidget(remove_btn)
        form.addRow(fac_btn_row)

        layout.addWidget(detail, 2)
        return w

    def _build_timeline_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Timeline of key events across all episodes (read-only):"))
        self.timeline_text = QTextEdit()
        self.timeline_text.setReadOnly(True)
        layout.addWidget(self.timeline_text)
        return w

    def _build_episodes_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Episode history:"))
        self.episodes_text = QTextEdit()
        self.episodes_text.setReadOnly(True)
        layout.addWidget(self.episodes_text)
        return w

    # ── Load / save ──────────────────────────────────────────────────

    def _load_bible(self):
        self.title_edit.setText(self.bible.series_title)

        # Characters
        self.char_list.clear()
        for ch in self.bible.main_characters:
            self.char_list.addItem(ch.get("name", "Unknown"))

        # Locations
        self.loc_list.clear()
        for loc in self.bible.recurring_locations:
            self.loc_list.addItem(loc.get("name", "Unknown"))

        # World
        wc = self.bible.world_context
        self.world_setting.setPlainText(wc.get("setting_description", ""))
        self.world_period.setText(wc.get("time_period", ""))
        self.world_rules.setPlainText(wc.get("rules_and_lore", ""))
        self.world_tone.setText(wc.get("tone", ""))

        # Episode duration
        dur = getattr(self.bible, "episode_duration_seconds", 0)
        self.ep_dur_minutes.setValue(dur // 60)
        self.ep_dur_seconds.setValue(dur % 60)

        # Objects
        self.obj_list.clear()
        for obj in self.bible.recurring_objects:
            self.obj_list.addItem(obj.get("name", "Unknown"))

        # Factions
        self.fac_list.clear()
        for fac in self.bible.factions_or_groups:
            self.fac_list.addItem(fac.get("name", "Unknown"))

        # Timeline
        lines = []
        for evt in self.bible.timeline_events:
            lines.append(f"[Episode {evt.get('episode_number', '?')}] {evt.get('event', '')} — {evt.get('description', '')}")
        self.timeline_text.setPlainText("\n".join(lines) if lines else "(no events yet)")

        # Episodes
        ep_lines = []
        for ep in sorted(self.bible.episode_history, key=lambda e: e.get("episode_number", 0)):
            status = ep.get("status", "")
            summary = ep.get("summary", ep.get("premise", ""))
            ep_lines.append(
                f"Episode {ep.get('episode_number', '?')}: {ep.get('title', 'Untitled')} [{status}]\n"
                f"  Premise: {ep.get('premise', '')}\n"
                f"  Summary: {summary}\n"
            )
        self.episodes_text.setPlainText("\n".join(ep_lines) if ep_lines else "(no episodes yet)")

        self._dirty = False

    def _collect_world_context(self):
        self.bible.world_context = {
            "setting_description": self.world_setting.toPlainText().strip(),
            "time_period": self.world_period.text().strip(),
            "rules_and_lore": self.world_rules.toPlainText().strip(),
            "tone": self.world_tone.text().strip(),
        }
        self.bible.episode_duration_seconds = self.ep_dur_minutes.value() * 60 + self.ep_dur_seconds.value()

    def _save(self):
        self.bible.series_title = self.title_edit.text().strip()
        self._collect_world_context()
        try:
            from core.series_manager import SeriesManager
            SeriesManager.save_series_bible(self.series_folder, self.bible)
            self._dirty = False
            self.bible_saved.emit()
            QMessageBox.information(self, "Saved", "Series Bible saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save Series Bible:\n{e}")

    def _close(self):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        self.accept()

    def _mark_dirty(self):
        self._dirty = True

    # ── Character CRUD ───────────────────────────────────────────────

    def _on_char_selected(self, row: int):
        if row < 0 or row >= len(self.bible.main_characters):
            return
        ch = self.bible.main_characters[row]
        self.char_name.setText(ch.get("name", ""))
        self.char_role.setCurrentText(ch.get("role", "main"))
        self.char_species.setText(ch.get("species", ""))
        self.char_appearance.setPlainText(ch.get("physical_appearance", ""))
        self.char_traits.setText(", ".join(ch.get("personality_traits", [])))
        self.char_arc.setPlainText(ch.get("growth_arc", ""))
        rels = ch.get("relationships", [])
        rel_lines = [f"{r.get('target','')} | {r.get('type','')} | {r.get('description','')}" for r in rels]
        self.char_relationships.setPlainText("\n".join(rel_lines))

    def _char_from_form(self) -> Dict[str, Any]:
        traits = [t.strip() for t in self.char_traits.text().split(",") if t.strip()]
        rels = []
        for line in self.char_relationships.toPlainText().strip().split("\n"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                rels.append({"target": parts[0], "type": parts[1], "description": parts[2] if len(parts) > 2 else ""})
        return {
            "name": self.char_name.text().strip(),
            "role": self.char_role.currentText(),
            "species": self.char_species.text().strip() or "Human",
            "physical_appearance": self.char_appearance.toPlainText().strip(),
            "personality_traits": traits,
            "relationships": rels,
            "growth_arc": self.char_arc.toPlainText().strip(),
        }

    def _add_character(self):
        data = self._char_from_form()
        if not data["name"]:
            return
        self.bible.add_character(data)
        self.char_list.addItem(data["name"])
        self._mark_dirty()

    def _update_character(self):
        row = self.char_list.currentRow()
        if row < 0 or row >= len(self.bible.main_characters):
            return
        data = self._char_from_form()
        existing = self.bible.main_characters[row]
        existing.update(data)
        self.char_list.item(row).setText(data.get("name", existing.get("name", "")))
        self._mark_dirty()

    def _remove_character(self):
        row = self.char_list.currentRow()
        if row < 0 or row >= len(self.bible.main_characters):
            return
        self.bible.main_characters.pop(row)
        self.char_list.takeItem(row)
        self._mark_dirty()

    # ── Location CRUD ────────────────────────────────────────────────

    def _on_loc_selected(self, row: int):
        if row < 0 or row >= len(self.bible.recurring_locations):
            return
        loc = self.bible.recurring_locations[row]
        self.loc_name.setText(loc.get("name", ""))
        self.loc_desc.setPlainText(loc.get("description", ""))
        self.loc_struct.setPlainText(loc.get("structural_characteristics", ""))

    def _add_location(self):
        name = self.loc_name.text().strip()
        if not name:
            return
        data = {"name": name, "description": self.loc_desc.toPlainText().strip(), "structural_characteristics": self.loc_struct.toPlainText().strip()}
        self.bible.add_location(data)
        self.loc_list.addItem(name)
        self._mark_dirty()

    def _update_location(self):
        row = self.loc_list.currentRow()
        if row < 0 or row >= len(self.bible.recurring_locations):
            return
        loc = self.bible.recurring_locations[row]
        loc["name"] = self.loc_name.text().strip()
        loc["description"] = self.loc_desc.toPlainText().strip()
        loc["structural_characteristics"] = self.loc_struct.toPlainText().strip()
        self.loc_list.item(row).setText(loc["name"])
        self._mark_dirty()

    def _remove_location(self):
        row = self.loc_list.currentRow()
        if row < 0 or row >= len(self.bible.recurring_locations):
            return
        self.bible.recurring_locations.pop(row)
        self.loc_list.takeItem(row)
        self._mark_dirty()

    # ── Object CRUD ──────────────────────────────────────────────────

    def _on_obj_selected(self, row: int):
        if row < 0 or row >= len(self.bible.recurring_objects):
            return
        obj = self.bible.recurring_objects[row]
        self.obj_name.setText(obj.get("name", ""))
        self.obj_desc.setPlainText(obj.get("description", ""))
        self.obj_visual.setPlainText(obj.get("visual_appearance", ""))
        self.obj_function.setPlainText(obj.get("narrative_function", ""))

    def _add_object(self):
        name = self.obj_name.text().strip()
        if not name:
            return
        self.bible.add_object({
            "name": name,
            "description": self.obj_desc.toPlainText().strip(),
            "visual_appearance": self.obj_visual.toPlainText().strip(),
            "narrative_function": self.obj_function.toPlainText().strip(),
        })
        self.obj_list.addItem(name)
        self._mark_dirty()

    def _update_object(self):
        row = self.obj_list.currentRow()
        if row < 0 or row >= len(self.bible.recurring_objects):
            return
        obj = self.bible.recurring_objects[row]
        obj["name"] = self.obj_name.text().strip()
        obj["description"] = self.obj_desc.toPlainText().strip()
        obj["visual_appearance"] = self.obj_visual.toPlainText().strip()
        obj["narrative_function"] = self.obj_function.toPlainText().strip()
        self.obj_list.item(row).setText(obj["name"])
        self._mark_dirty()

    def _remove_object(self):
        row = self.obj_list.currentRow()
        if row < 0 or row >= len(self.bible.recurring_objects):
            return
        self.bible.recurring_objects.pop(row)
        self.obj_list.takeItem(row)
        self._mark_dirty()

    # ── Faction CRUD ─────────────────────────────────────────────────

    def _on_fac_selected(self, row: int):
        if row < 0 or row >= len(self.bible.factions_or_groups):
            return
        fac = self.bible.factions_or_groups[row]
        self.fac_name.setText(fac.get("name", ""))
        self.fac_desc.setPlainText(fac.get("description", ""))
        self.fac_members.setText(", ".join(fac.get("members", [])))
        self.fac_goals.setPlainText(fac.get("goals", ""))

    def _add_faction(self):
        name = self.fac_name.text().strip()
        if not name:
            return
        members = [m.strip() for m in self.fac_members.text().split(",") if m.strip()]
        self.bible.add_faction({
            "name": name,
            "description": self.fac_desc.toPlainText().strip(),
            "members": members,
            "goals": self.fac_goals.toPlainText().strip(),
        })
        self.fac_list.addItem(name)
        self._mark_dirty()

    def _update_faction(self):
        row = self.fac_list.currentRow()
        if row < 0 or row >= len(self.bible.factions_or_groups):
            return
        fac = self.bible.factions_or_groups[row]
        fac["name"] = self.fac_name.text().strip()
        fac["description"] = self.fac_desc.toPlainText().strip()
        fac["members"] = [m.strip() for m in self.fac_members.text().split(",") if m.strip()]
        fac["goals"] = self.fac_goals.toPlainText().strip()
        self.fac_list.item(row).setText(fac["name"])
        self._mark_dirty()

    def _remove_faction(self):
        row = self.fac_list.currentRow()
        if row < 0 or row >= len(self.bible.factions_or_groups):
            return
        self.bible.factions_or_groups.pop(row)
        self.fac_list.takeItem(row)
        self._mark_dirty()
