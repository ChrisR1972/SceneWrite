@echo off
echo ========================================
echo SceneWrite - Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install PyInstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller. Please install manually: pip install PyInstaller
        pause
        exit /b 1
    )
)

REM Check if PyArmor is installed
python -c "import pyarmor" 2>nul
if errorlevel 1 (
    echo PyArmor not found. Installing...
    pip install pyarmor
    if errorlevel 1 (
        echo Warning: PyArmor install failed. Build will continue WITHOUT obfuscation.
    )
)

echo.
echo ========================================
echo Step 1: Cleaning previous builds...
echo ========================================
echo.

REM Clean previous builds
if exist build (
    echo Removing build folder...
    rmdir /s /q build
    if errorlevel 1 (
        echo Warning: Could not fully remove build folder. Some files may be in use.
    ) else (
        echo Build folder removed successfully.
    )
) else (
    echo No build folder found.
)

if exist dist (
    echo Removing dist folder...
    rmdir /s /q dist
    if errorlevel 1 (
        echo Warning: Could not fully remove dist folder. Some files may be in use.
    ) else (
        echo Dist folder removed successfully.
    )
) else (
    echo No dist folder found.
)

REM Clean obfuscation artifacts
if exist _obf (
    echo Removing obfuscation folder...
    rmdir /s /q _obf
)

REM Clean PyInstaller cache
if exist __pycache__ (
    echo Removing __pycache__ folders...
    for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
)

REM Clean .spec file artifacts (if any)
if exist *.spec.bak del /q *.spec.bak

echo.
echo ========================================
echo Step 2: Obfuscating source code...
echo ========================================
echo.

REM Obfuscate Python source with PyArmor before building
python -c "import pyarmor" 2>nul
if errorlevel 1 (
    echo WARNING: PyArmor not available — skipping obfuscation.
    echo The build will work, but source code will NOT be protected.
    echo Install with: pip install pyarmor
    echo.
) else (
    echo Obfuscating with PyArmor...
    mkdir _obf 2>nul

    REM Obfuscate core and ui packages plus top-level modules
    pyarmor gen -O _obf -r core ui
    pyarmor gen -O _obf main.py config.py debug_log.py fix_storyboard_extraction.py

    if errorlevel 1 (
        echo WARNING: PyArmor obfuscation failed — building from plain source.
        if exist _obf rmdir /s /q _obf
    ) else (
        echo Obfuscation complete.
        echo.

        REM Copy obfuscated files over the originals for PyInstaller to pick up.
        REM We work on a staging copy so the originals are never touched.
        echo Staging obfuscated files...
        mkdir _obf\config 2>nul
        if exist config\ActionWhitelist.json copy /y config\ActionWhitelist.json _obf\config\ >nul
        if exist config\SFXWhitelist.json copy /y config\SFXWhitelist.json _obf\config\ >nul

        REM Copy non-Python files that PyInstaller needs
        copy /y screenplay_tool.spec _obf\ >nul
        copy /y SceneWrite_Logo.ico _obf\ >nul 2>nul
        copy /y SceneWrite_Logo.icns _obf\ >nul 2>nul
        copy /y SceneWrite_Logo.png _obf\ >nul 2>nul
        for %%f in ("Action Rules.txt" "SFX Rules.txt" "Character Rules.txt" "Video Prompt.txt" "Wardrobe.txt") do (
            if exist %%f copy /y %%f _obf\ >nul 2>nul
        )
        echo Staging complete.
    )
)

echo.
echo ========================================
echo Step 3: Building executable...
echo ========================================
echo.
echo This may take a few minutes...
echo Please wait...
echo.

REM Build from obfuscated source if available, otherwise from plain source
if exist _obf\main.py (
    pushd _obf
    pyinstaller --clean --noconfirm screenplay_tool.spec
    popd
    REM Move the dist output back
    if exist _obf\dist (
        xcopy /e /i /y _obf\dist dist >nul
    )
) else (
    pyinstaller --clean --noconfirm screenplay_tool.spec
)

if errorlevel 1 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo.
    echo Check the output above for errors.
    echo Common issues:
    echo - Missing dependencies: pip install -r requirements.txt
    echo - PyInstaller not installed: pip install PyInstaller
    echo - File permissions: Close any open files and try again
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD COMPLETED SUCCESSFULLY!
echo ========================================
echo.

REM Check if executable exists and show size
if exist "dist\SceneWrite.exe" (
    echo Executable created: dist\SceneWrite.exe
    echo.
    
    REM Get file size
    for %%A in ("dist\SceneWrite.exe") do (
        set size=%%~zA
    )
    echo Checking file size...
    
    REM Check folder size
    echo.
    echo Distribution folder location: dist\SceneWrite\
    echo.
    echo ========================================
    echo Distribution Instructions:
    echo ========================================
    echo.
    echo 1. Copy the entire "SceneWrite" folder from dist\
    echo 2. Zip it and share with users
    echo 3. Users can extract and run SceneWrite.exe
    echo.
    echo Expected size: 50-100 MB (optimized build)
    echo.
) else (
    echo Warning: Executable not found in expected location.
    echo Check dist folder for output.
    echo.
)

echo ========================================
pause

