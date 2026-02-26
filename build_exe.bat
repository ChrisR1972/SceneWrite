@echo off
echo ========================================
echo MoviePrompterAI - Build Script
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

REM Clean PyInstaller cache
if exist __pycache__ (
    echo Removing __pycache__ folders...
    for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
)

REM Clean .spec file artifacts (if any)
if exist *.spec.bak del /q *.spec.bak

echo.
echo ========================================
echo Step 2: Building executable...
echo ========================================
echo.
echo This may take a few minutes...
echo Please wait...
echo.

REM Run PyInstaller with the spec file
pyinstaller --clean --noconfirm screenplay_tool.spec

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
if exist "dist\MoviePrompterAI.exe" (
    echo Executable created: dist\MoviePrompterAI.exe
    echo.
    
    REM Get file size
    for %%A in ("dist\MoviePrompterAI.exe") do (
        set size=%%~zA
    )
    echo Checking file size...
    
    REM Check folder size
    echo.
    echo Distribution folder location: dist\MoviePrompterAI\
    echo.
    echo ========================================
    echo Distribution Instructions:
    echo ========================================
    echo.
    echo 1. Copy the entire "MoviePrompterAI" folder from dist\
    echo 2. Zip it and share with users
    echo 3. Users can extract and run MoviePrompterAI.exe
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

