#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "SceneWrite - macOS Build Script"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python is available
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.10+ first."
    echo "  brew install python@3.12"
    exit 1
fi

PYTHON=python3

echo "Using Python: $($PYTHON --version)"
echo ""

# Check / install PyInstaller
if ! $PYTHON -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller not found. Installing..."
    $PYTHON -m pip install PyInstaller
fi

# Check / install project dependencies
echo "Checking project dependencies..."
$PYTHON -m pip install -r requirements.txt --quiet

# Check / install PyArmor
if ! $PYTHON -c "import pyarmor" 2>/dev/null; then
    echo "PyArmor not found. Installing..."
    $PYTHON -m pip install pyarmor || echo "Warning: PyArmor install failed. Build will continue without obfuscation."
fi

echo ""
echo "========================================"
echo "Step 1: Cleaning previous builds..."
echo "========================================"
echo ""

rm -rf build dist _obf __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.spec.bak" -delete 2>/dev/null || true

echo "Clean complete."
echo ""
echo "========================================"
echo "Step 2: Obfuscating source code..."
echo "========================================"
echo ""

USE_OBF=false
if $PYTHON -c "import pyarmor" 2>/dev/null; then
    echo "Obfuscating with PyArmor..."
    mkdir -p _obf

    if pyarmor gen -O _obf -r core ui && pyarmor gen -O _obf main.py config.py debug_log.py fix_storyboard_extraction.py; then
        echo "Obfuscation complete."
        USE_OBF=true

        cp -f screenplay_tool.spec _obf/
        cp -f SceneWrite_Logo.* _obf/ 2>/dev/null || true
        mkdir -p _obf/config
        cp -f config/*.json _obf/config/ 2>/dev/null || true
        for f in "Action Rules.txt" "SFX Rules.txt" "Character Rules.txt" "Video Prompt.txt" "Wardrobe.txt"; do
            [ -f "$f" ] && cp -f "$f" _obf/
        done
        echo "Staging complete."
    else
        echo "WARNING: PyArmor obfuscation failed — building from plain source."
        rm -rf _obf
    fi
else
    echo "WARNING: PyArmor not available — skipping obfuscation."
    echo "Install with: pip install pyarmor"
fi

echo ""
echo "========================================"
echo "Step 3: Building macOS application..."
echo "========================================"
echo ""
echo "This may take a few minutes..."
echo ""

if [ "$USE_OBF" = true ] && [ -f "_obf/main.py" ]; then
    (cd _obf && $PYTHON -m PyInstaller --clean --noconfirm screenplay_tool.spec)
    cp -r _obf/dist/* dist/ 2>/dev/null || true
else
    $PYTHON -m PyInstaller --clean --noconfirm screenplay_tool.spec
fi

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================"
    echo "BUILD FAILED!"
    echo "========================================"
    echo ""
    echo "Check the output above for errors."
    echo "Common issues:"
    echo "  - Missing dependencies: pip install -r requirements.txt"
    echo "  - PyInstaller not installed: pip install PyInstaller"
    echo "  - Xcode CLI tools needed: xcode-select --install"
    echo ""
    exit 1
fi

echo ""
echo "========================================"
echo "BUILD COMPLETED SUCCESSFULLY!"
echo "========================================"
echo ""

if [ -d "dist/SceneWrite.app" ]; then
    echo "Application bundle created: dist/SceneWrite.app"
    echo ""
    APP_SIZE=$(du -sh "dist/SceneWrite.app" | cut -f1)
    echo "App size: $APP_SIZE"
    echo ""
    echo "========================================"
    echo "Distribution Instructions:"
    echo "========================================"
    echo ""
    echo "Option 1 - Direct Distribution:"
    echo "  1. Zip the SceneWrite.app bundle:"
    echo "     cd dist && zip -r SceneWrite-macOS.zip SceneWrite.app"
    echo "  2. Share the zip file"
    echo "  3. Users extract and drag SceneWrite.app to /Applications"
    echo ""
    echo "Option 2 - Create a DMG (recommended):"
    echo "  1. Install create-dmg: brew install create-dmg"
    echo "  2. Run: create-dmg \\"
    echo "       --volname 'SceneWrite' \\"
    echo "       --window-size 600 400 \\"
    echo "       --icon-size 100 \\"
    echo "       --icon 'SceneWrite.app' 150 200 \\"
    echo "       --app-drop-link 450 200 \\"
    echo "       'dist/SceneWrite.dmg' 'dist/SceneWrite.app'"
    echo ""
    echo "Note: Users may need to right-click > Open on first launch"
    echo "      to bypass Gatekeeper (unsigned app)."
    echo ""
elif [ -d "dist/SceneWrite" ]; then
    echo "Application directory created: dist/SceneWrite/"
    echo ""
    DIR_SIZE=$(du -sh "dist/SceneWrite" | cut -f1)
    echo "Directory size: $DIR_SIZE"
    echo ""
    echo "To run: ./dist/SceneWrite/SceneWrite"
    echo ""
else
    echo "Warning: Output not found in expected location."
    echo "Check dist/ folder for output."
fi

echo "========================================"
