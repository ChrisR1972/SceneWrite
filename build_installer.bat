@echo off
echo Building MoviePrompterAI installer...
echo.

REM First build the executable
call build_exe.bat

if errorlevel 1 (
    echo Build failed. Cannot create installer.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Executable built successfully!
echo ========================================
echo.
echo The application is ready in: dist\MoviePrompterAI\
echo.
echo To distribute the application:
echo 1. Copy the entire "MoviePrompterAI" folder from the dist folder
echo 2. Zip it and share it with users
echo 3. Users can extract and run MoviePrompterAI.exe
echo.
echo For a proper installer, you can use:
echo - Inno Setup (free, Windows installer creator)
echo - NSIS (free, Windows installer creator)
echo - Advanced Installer (has free version)
echo.
pause

