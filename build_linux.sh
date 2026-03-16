#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "SceneWrite - Linux Build Script"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python is available
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Please install Python 3.10+ first."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo "  Arch:          sudo pacman -S python python-pip"
    exit 1
fi

echo "Using Python: $($PYTHON --version)"
echo ""

# PyQt6 needs certain system libraries on Linux
echo "Note: PyQt6 on Linux requires system packages."
echo "If the build succeeds but the app fails to launch, install:"
echo "  Ubuntu/Debian: sudo apt install libgl1 libegl1 libxkbcommon0 libdbus-1-3 libxcb-cursor0"
echo "  Fedora:        sudo dnf install mesa-libGL mesa-libEGL libxkbcommon"
echo "  Arch:          sudo pacman -S mesa libxkbcommon"
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

        # Copy non-Python files needed by PyInstaller
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
echo "Step 3: Building Linux application..."
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
    echo "  - Missing system packages (see note above)"
    echo ""
    exit 1
fi

echo ""
echo "========================================"
echo "BUILD COMPLETED SUCCESSFULLY!"
echo "========================================"
echo ""

if [ -d "dist/SceneWrite" ]; then
    echo "Application directory created: dist/SceneWrite/"
    echo ""
    DIR_SIZE=$(du -sh "dist/SceneWrite" | cut -f1)
    echo "Directory size: $DIR_SIZE"
    echo ""
    echo "To run: ./dist/SceneWrite/SceneWrite"
    echo ""
    echo "========================================"
    echo "Distribution Instructions:"
    echo "========================================"
    echo ""
    echo "Option 1 - Tarball (simplest):"
    echo "  1. Create archive:"
    echo "     cd dist && tar -czf SceneWrite-Linux-x86_64.tar.gz SceneWrite/"
    echo "  2. Share the .tar.gz file"
    echo "  3. Users extract and run:"
    echo "     tar -xzf SceneWrite-Linux-x86_64.tar.gz"
    echo "     ./SceneWrite/SceneWrite"
    echo ""
    echo "Option 2 - AppImage (recommended for wide compatibility):"
    echo "  See https://appimage.org for packaging tools."
    echo ""
    echo "Option 3 - .deb package:"
    echo "  Use fpm: fpm -s dir -t deb -n scenewrite -v 1.0.0 \\"
    echo "    --description 'AI-powered screenplay writing tool' \\"
    echo "    dist/SceneWrite/=/opt/scenewrite/"
    echo "  (Install fpm: gem install fpm)"
    echo ""
else
    echo "Warning: Output not found in expected location."
    echo "Check dist/ folder for output."
fi

echo "========================================"
