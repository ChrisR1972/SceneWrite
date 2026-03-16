# -*- mode: python ; coding: utf-8 -*-
"""
Cross-platform PyInstaller spec file for SceneWrite.

Works on Windows, macOS, and Linux. Run with:
    pyinstaller --clean --noconfirm screenplay_tool.spec
"""

import sys
import os
import re

block_cipher = None

# Read APP_VERSION from config.py so it stays in sync
_version = "1.0.0"
with open("config.py", encoding="utf-8") as _f:
    _m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', _f.read(), re.MULTILINE)
    if _m:
        _version = _m.group(1)

platform = sys.platform

# Determine icon file based on platform
if platform == "darwin":
    icon_file = "SceneWrite_Logo.icns" if os.path.exists("SceneWrite_Logo.icns") else None
elif platform == "win32":
    icon_file = "SceneWrite_Logo.ico" if os.path.exists("SceneWrite_Logo.ico") else None
else:
    icon_file = None

# Data files to bundle (icon for runtime use, rule/text files)
datas = []
for ico in ["SceneWrite_Logo.ico", "SceneWrite_Logo.icns", "SceneWrite_Logo.png"]:
    if os.path.exists(ico):
        datas.append((ico, "."))

# Bundle .txt rule files so the app can read them at runtime
txt_files = [
    "Action Rules.txt",
    "SFX Rules.txt",
    "Character Rules.txt",
    "The Core Principle for characters identity.txt",
    "Product AdvertisementBranding.txt",
    "Video Prompt.txt",
    "Instructions for video prompt.txt",
    "Instructions for image prompt.txt",
    "Wardrobe.txt",
]
for txt in txt_files:
    if os.path.exists(txt):
        datas.append((txt, "."))

# Bundle pyspellchecker dictionary files
try:
    import spellchecker as _sc
    _sc_dir = os.path.dirname(_sc.__file__)
    _sc_res = os.path.join(_sc_dir, "resources")
    if os.path.isdir(_sc_res):
        datas.append((_sc_res, os.path.join("spellchecker", "resources")))
except ImportError:
    pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "openai",
        "anthropic",
        "keyring",
        "keyring.backends",
        "requests",
        "spellchecker",
        "docx",
        "json",
        "csv",
        "core",
        "core.action_rules",
        "core.ad_framework",
        "core.ai_generator",
        "core.cinematic_grammar",
        "core.cinematic_token_detector",
        "core.higgsfield_exporter",
        "core.higgsfield_api_client",
        "core.markup_whitelist",
        "core.multishot_engine",
        "core.novel_importer",
        "core.platform_clients",
        "core.prompt_adapters",
        "core.screenplay_engine",
        "core.sentence_integrity",
        "core.series_bible",
        "core.series_manager",
        "core.sfx_rules",
        "core.snapshot_manager",
        "core.spell_checker",
        "core.license_manager",
        "core.storyboard_validator",
        "core.update_checker",
        "core.video_prompt_builder",
        "core.workflow_profile",
        "ui",
        "ui.main_window",
        "ui.ai_chat_panel",
        "ui.help_dialogs",
        "ui.higgsfield_panel",
        "ui.identity_block_manager",
        "ui.image_thumbnail",
        "ui.novel_import_dialog",
        "ui.premise_dialog",
        "ui.scene_framework_editor",
        "ui.series_bible_editor",
        "ui.series_dashboard",
        "ui.settings_dialog",
        "ui.story_creation_wizard",
        "ui.story_framework_view",
        "ui.story_settings_tab",
        "ui.storyboard_item_editor",
        "ui.storyboard_timeline",
        "ui.activation_dialog",
        "ui.update_dialog",
        "ui.wizard_steps",
        "ui.wizard_steps.framework_generation_step",
        "ui.wizard_steps.length_intent_step",
        "ui.wizard_steps.premise_step",
        "ui.wizard_steps.series_mode_step",
        "ui.wizard_steps.story_outline_step",
        "utils",
        "utils.logger",
        "debug_log",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL",
        "pytest",
        "unittest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if platform == "darwin":
    # macOS: build an .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="SceneWrite",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="SceneWrite",
    )
    app = BUNDLE(
        coll,
        name="SceneWrite.app",
        icon=icon_file,
        bundle_identifier="com.scenewrite.app",
        info_plist={
            "CFBundleDisplayName": "SceneWrite",
            "CFBundleShortVersionString": _version,
            "CFBundleVersion": _version,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.15",
        },
    )
else:
    # Windows and Linux: build a directory distribution
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="SceneWrite",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="SceneWrite",
    )
