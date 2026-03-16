# Building the SceneWrite Executable

This guide explains how to create standalone executables for **Windows**, **macOS**, and **Linux** that can be distributed without requiring Python.

## Prerequisites (All Platforms)

- Python 3.10 or higher installed
- All project dependencies installed (`pip install -r requirements.txt`)
- PyInstaller (will be installed automatically by the build scripts)

---

## Windows

### Quick Build

1. **Run the build script:**
   ```bash
   build_exe.bat
   ```

2. **Wait for completion** (takes 2-5 minutes)

3. **Find your executable:**
   - Location: `dist\SceneWrite\`
   - Main file: `SceneWrite.exe`

### Distribution

#### Option 1: Simple Distribution
1. Zip the entire `dist\SceneWrite\` folder
2. Share the zip file
3. Users extract and run `SceneWrite.exe`

#### Option 2: Inno Setup Installer (Recommended)

An Inno Setup script (`installer.iss`) is included in the project. It creates a professional Windows installer with:
- Start Menu and Desktop shortcuts
- Uninstaller
- In-place upgrade support (users run the new installer to update — no uninstall required)
- Automatic closure of the running app during upgrade

**To build the installer:**
1. Download Inno Setup from https://jrsoftware.org/isinfo.php
2. Build the executable first (`build_exe.bat`)
3. Open `installer.iss` in Inno Setup Compiler
4. Click Build → Compile
5. The installer will be created in `installer_output/SceneWrite_Setup_{version}.exe`

**Versioning:** Update `#define MyAppVersion` in `installer.iss` before each release to ensure the installer filename and displayed version are correct.

**In-place upgrades:** The installer uses `UsePreviousAppDir=yes` to reuse the existing install location and `CloseApplications=yes` to safely shut down the running app before overwriting files. User configuration is preserved because it lives in `%APPDATA%\SceneWrite\` (not the install directory).

---

## macOS

### Prerequisites

- Python 3.10+ (install via [Homebrew](https://brew.sh): `brew install python@3.12`)
- Xcode Command Line Tools: `xcode-select --install`

### Quick Build

1. **Make the build script executable (first time only):**
   ```bash
   chmod +x build_mac.sh
   ```

2. **Run the build script:**
   ```bash
   ./build_mac.sh
   ```

3. **Wait for completion** (takes 2-5 minutes)

4. **Find your application:**
   - Location: `dist/SceneWrite.app`

### Manual Build

```bash
pip3 install PyInstaller
pip3 install -r requirements.txt
python3 -m PyInstaller --clean --noconfirm screenplay_tool.spec
```

### Distribution

#### Option 1: Zip File
```bash
cd dist && zip -r SceneWrite-macOS.zip SceneWrite.app
```
Users extract and drag `SceneWrite.app` to `/Applications`.

#### Option 2: DMG Image (Recommended)
```bash
brew install create-dmg
create-dmg \
  --volname "SceneWrite" \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "SceneWrite.app" 150 200 \
  --app-drop-link 450 200 \
  "dist/SceneWrite.dmg" "dist/SceneWrite.app"
```

### macOS Notes
- **Gatekeeper:** Since the app is not signed with an Apple Developer certificate, users will need to right-click the app and select "Open" on first launch, then click "Open" in the dialog.
- **App icon:** Place a `SceneWrite_Logo.icns` file in the project root before building to include a custom app icon. You can convert from PNG using: `sips -s format icns SceneWrite_Logo.png --out SceneWrite_Logo.icns`
- **Universal binary:** The build targets the current architecture by default. To build a universal binary (Intel + Apple Silicon), you would need to build on each architecture and use `lipo` to combine them.

---

## Linux

### Prerequisites

- Python 3.10+ (usually pre-installed on modern distros)
- System libraries required by PyQt6:

  **Ubuntu/Debian:**
  ```bash
  sudo apt install python3 python3-pip python3-venv \
    libgl1 libegl1 libxkbcommon0 libdbus-1-3 libxcb-cursor0
  ```

  **Fedora:**
  ```bash
  sudo dnf install python3 python3-pip \
    mesa-libGL mesa-libEGL libxkbcommon
  ```

  **Arch Linux:**
  ```bash
  sudo pacman -S python python-pip mesa libxkbcommon
  ```

### Quick Build

1. **Make the build script executable (first time only):**
   ```bash
   chmod +x build_linux.sh
   ```

2. **Run the build script:**
   ```bash
   ./build_linux.sh
   ```

3. **Wait for completion** (takes 2-5 minutes)

4. **Find your executable:**
   - Location: `dist/SceneWrite/`
   - Main file: `dist/SceneWrite/SceneWrite`

### Manual Build

```bash
pip3 install PyInstaller
pip3 install -r requirements.txt
python3 -m PyInstaller --clean --noconfirm screenplay_tool.spec
```

### Distribution

#### Option 1: Tarball (Simplest)
```bash
cd dist && tar -czf SceneWrite-Linux-x86_64.tar.gz SceneWrite/
```
Users extract and run:
```bash
tar -xzf SceneWrite-Linux-x86_64.tar.gz
./SceneWrite/SceneWrite
```

#### Option 2: AppImage (Recommended for Wide Compatibility)
See [appimage.org](https://appimage.org) for packaging tools. An AppImage runs on most Linux distributions without installation.

#### Option 3: .deb Package (Debian/Ubuntu)
Using [fpm](https://fpm.readthedocs.io):
```bash
gem install fpm
fpm -s dir -t deb -n scenewrite -v 1.0.0 \
  --description "AI-powered screenplay writing tool" \
  dist/SceneWrite/=/opt/scenewrite/
```

#### Option 4: Desktop Entry
To create a system menu entry, save this as `~/.local/share/applications/scenewrite.desktop`:
```ini
[Desktop Entry]
Name=SceneWrite
Exec=/opt/scenewrite/SceneWrite
Type=Application
Categories=Office;TextEditor;
Comment=AI-powered screenplay writing tool
```

---

## Cleaning Build Artifacts

**Windows:**
```bash
clean_build.bat
```

**macOS / Linux:**
```bash
chmod +x clean_build.sh
./clean_build.sh
```

---

## Troubleshooting

### Build Fails
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check that PyInstaller is installed: `pip install PyInstaller`
- Review error messages in the console output
- **macOS:** Ensure Xcode CLI tools are installed: `xcode-select --install`
- **Linux:** Ensure system packages are installed (see Prerequisites above)

### Executable Doesn't Run
- **Windows:** Check Windows Defender isn't blocking it
- **macOS:** Right-click → Open to bypass Gatekeeper
- **Linux:** Make sure the file is executable: `chmod +x dist/SceneWrite/SceneWrite`
- Try running from command line/terminal to see error messages

### Missing Modules
- Add missing modules to `hiddenimports` in `screenplay_tool.spec`
- Rebuild: `pyinstaller --clean screenplay_tool.spec`

### Large File Size
- The executable includes Python and all dependencies (~50-100 MB)
- This is normal for PyQt6 applications
- Users don't need Python installed

### Linux: "qt.qpa.plugin: Could not load the Qt platform plugin"
Install the missing Qt platform dependencies:
```bash
# Ubuntu/Debian
sudo apt install libgl1 libegl1 libxkbcommon0 libxcb-cursor0

# Or try setting the platform explicitly
QT_QPA_PLATFORM=xcb ./dist/SceneWrite/SceneWrite
```

---

## File Structure After Build

**Windows:**
```
dist/
└── SceneWrite/
    ├── SceneWrite.exe
    └── _internal/
        ├── python310.dll
        ├── PyQt6/
        └── ...
```

**macOS:**
```
dist/
└── SceneWrite.app/
    └── Contents/
        ├── Info.plist
        ├── MacOS/
        │   └── SceneWrite
        └── Resources/
            └── ...
```

**Linux:**
```
dist/
└── SceneWrite/
    ├── SceneWrite
    └── _internal/
        ├── libpython3.10.so
        ├── PyQt6/
        └── ...
```

---

## Notes

- The executable is standalone — no Python installation needed on target machines
- First run may be slightly slower as the OS scans the executable
- **Windows:** Config is stored in `%APPDATA%\SceneWrite\`
- **macOS:** Config is stored in `~/Library/Application Support/SceneWrite/`
- **Linux:** Config is stored in `~/.config/SceneWrite/`
- Stories default to `~/Documents/SceneWrite Stories`
- API keys are stored in the config file (and optionally via the system keyring)
- Configuration files are created automatically on first run

## Build Scripts Summary

| Platform | Build | Clean | Installer |
|----------|-------|-------|-----------|
| Windows  | `build_exe.bat` | `clean_build.bat` | `installer.iss` (Inno Setup) |
| macOS    | `build_mac.sh` | `clean_build.sh` | DMG via `create-dmg` |
| Linux    | `build_linux.sh` | `clean_build.sh` | Tarball / AppImage / .deb |
