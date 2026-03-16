@echo off
echo ========================================
echo SceneWrite - Clean Script
echo ========================================
echo.

echo Cleaning all build artifacts...
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

REM Clean obfuscation staging
if exist _obf (
    echo Removing obfuscation staging folder...
    rmdir /s /q _obf
    echo Obfuscation folder removed.
) else (
    echo No obfuscation folder found.
)

REM Clean PyInstaller cache
if exist __pycache__ (
    echo Removing __pycache__ folders...
    for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
    echo __pycache__ folders removed.
) else (
    echo No __pycache__ folders found.
)

REM Clean .spec file artifacts (if any)
if exist *.spec.bak (
    echo Removing .spec backup files...
    del /q *.spec.bak
    echo Backup files removed.
)

REM Clean .pyc files
echo Removing .pyc files...
for /r . %%f in (*.pyc) do @if exist "%%f" del /q "%%f"

echo.
echo ========================================
echo Clean completed!
echo ========================================
echo.
pause

