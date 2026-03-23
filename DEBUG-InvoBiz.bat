@echo off
chcp 65001 >nul
title InvoBiz - Debug Mode
color 0E
echo.
echo ============================================
echo   InvoBiz v1.0 Beta - Debug Mode
echo ============================================
echo.
echo This window will show all errors and warnings.
echo Keep it open while using the app.
echo If something breaks, screenshot this window.
echo.
echo ============================================
echo   Starting InvoBiz...
echo ============================================
echo.

:: Try running the EXE first (built version)
if exist InvoBiz.exe (
    echo Running: InvoBiz.exe
    echo.
    InvoBiz.exe
    echo.
    echo ============================================
    if %errorlevel% == 0 (
        echo   App closed normally.
    ) else (
        echo   App exited with error code: %errorlevel%
        echo   Screenshot above and send to Anna!
    )
    echo ============================================
    goto END
)

:: Fall back to Python source if no EXE
if exist main.py (
    echo No EXE found - running from Python source...
    echo.
    python main.py 2>&1
    echo.
    echo ============================================
    if %errorlevel% == 0 (
        echo   App closed normally.
    ) else (
        echo   ERROR CODE: %errorlevel%
        echo   Screenshot the error above and send to Anna!
    )
    echo ============================================
    goto END
)

echo ERROR: Neither InvoBiz.exe nor main.py found!
echo Make sure this file is in your InvoBiz folder.

:END
echo.
pause
