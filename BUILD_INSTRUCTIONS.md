# Building the MoviePrompterAI Executable

This guide explains how to create a standalone Windows executable that can be installed on any Windows PC without requiring Python.

## Prerequisites

- Python 3.10 or higher installed
- All project dependencies installed (`pip install -r requirements.txt`)
- PyInstaller (will be installed automatically by the build script)

## Quick Build

1. **Run the build script:**
   ```bash
   build_exe.bat
   ```

2. **Wait for completion** (takes 2-5 minutes)

3. **Find your executable:**
   - Location: `dist\MoviePrompterAI\`
   - Main file: `MoviePrompterAI.exe`

## Manual Build

If you prefer to build manually:

```bash
pip install PyInstaller
pyinstaller --clean screenplay_tool.spec
```

## Distribution

### Option 1: Simple Distribution (Recommended)
1. Zip the entire `dist\MoviePrompterAI\` folder
2. Share the zip file
3. Users extract and run `MoviePrompterAI.exe`

### Option 2: Create an Installer
For a professional installer, use one of these tools:

**Inno Setup (Free, Recommended)**
- Download from: https://jrsoftware.org/isinfo.php
- Create an installer script that:
  - Copies files to `Program Files`
  - Creates Start Menu shortcuts
  - Adds uninstaller

**NSIS (Free)**
- Download from: https://nsis.sourceforge.io/
- Create installer scripts for Windows

**Advanced Installer (Free version available)**
- Download from: https://www.advancedinstaller.com/

## Troubleshooting

### Build Fails
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check that PyInstaller is installed: `pip install PyInstaller`
- Review error messages in the console output

### Executable Doesn't Run
- Check Windows Defender isn't blocking it
- Try running from command line to see error messages
- Ensure all DLLs are included (check the dist folder)

### Missing Modules
- Add missing modules to `hiddenimports` in `screenplay_tool.spec`
- Rebuild: `pyinstaller --clean screenplay_tool.spec`

### Large File Size
- The executable includes Python and all dependencies (~50-100 MB)
- This is normal for PyQt6 applications
- Users don't need Python installed

## File Structure After Build

```
dist/
└── MoviePrompterAI/
    ├── MoviePrompterAI.exe  (Main executable)
    ├── _internal/                 (Python runtime and libraries)
    │   ├── python310.dll
    │   ├── PyQt6/
    │   ├── spellchecker/
    │   └── ... (other dependencies)
    └── ... (other required files)
```

## Notes

- The executable is standalone - no Python installation needed on target PCs
- First run may be slightly slower as Windows scans the executable
- All user data is stored in the user's AppData folder (handled by keyring)
- Configuration files are created automatically on first run

