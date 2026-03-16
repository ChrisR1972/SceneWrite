#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "SceneWrite - Clean Script (macOS/Linux)"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Cleaning all build artifacts..."
echo ""

if [ -d "build" ]; then
    echo "Removing build folder..."
    rm -rf build
    echo "Build folder removed."
else
    echo "No build folder found."
fi

if [ -d "dist" ]; then
    echo "Removing dist folder..."
    rm -rf dist
    echo "Dist folder removed."
else
    echo "No dist folder found."
fi

if [ -d "_obf" ]; then
    echo "Removing obfuscation staging folder..."
    rm -rf _obf
    echo "Obfuscation folder removed."
else
    echo "No obfuscation folder found."
fi

echo "Removing __pycache__ folders..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "Done."

echo "Removing .pyc files..."
find . -name "*.pyc" -delete 2>/dev/null || true
echo "Done."

echo "Removing .spec backup files..."
find . -name "*.spec.bak" -delete 2>/dev/null || true
echo "Done."

echo ""
echo "========================================"
echo "Clean completed!"
echo "========================================"
