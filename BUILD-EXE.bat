@echo off
title InvoBiz Build Tool
color 0A
echo.
echo ============================================
echo   InvoBiz v1.0 - Build EXE
echo ============================================
echo.

echo Detecting Python environment...
for /f "delims=" %%i in ('python -c "import customtkinter, os; print(os.path.dirname(customtkinter.__file__))"') do set CTK_PATH=%%i

if "%CTK_PATH%"=="" (
    echo Installing dependencies...
    python -m pip install customtkinter reportlab pillow pyinstaller --user
    for /f "delims=" %%i in ('python -c "import customtkinter, os; print(os.path.dirname(customtkinter.__file__))"') do set CTK_PATH=%%i
)

if "%CTK_PATH%"=="" (
    echo ERROR: Could not find customtkinter.
    pause
    exit /b 1
)
echo Found: %CTK_PATH%

echo.
echo [1/4] Installing dependencies...
python -m pip install pyinstaller pillow customtkinter reportlab --user --quiet
echo Done.

echo.
echo [2/4] Generating icon...
python generate_icon.py
if exist invobiz.ico (
    echo Icon ready.
    set ICON_FLAG=--icon=invobiz.ico
) else (
    set ICON_FLAG=
)

echo.
echo [3/4] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist InvoBiz.spec del /q InvoBiz.spec
if exist InvoBiz.exe del /q InvoBiz.exe
echo Done.

echo.
echo [4/4] Building InvoBiz.exe - please wait...
echo.

python -m PyInstaller --onefile --windowed --name InvoBiz %ICON_FLAG% ^
  --add-data "%CTK_PATH%;customtkinter" ^
  --add-data "invobiz.ico;." ^
  --collect-all customtkinter ^
  --hidden-import customtkinter ^
  --hidden-import reportlab ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import PIL.ImageFont ^
  --hidden-import sqlite3 ^
  --hidden-import json ^
  --hidden-import calendar ^
  --hidden-import platform ^
  --hidden-import tempfile ^
  --hidden-import subprocess ^
  --exclude-module PIL._avif ^
  --exclude-module PIL._webp ^
  --exclude-module PIL.FtImagePlugin ^
  --exclude-module PIL.SgiImagePlugin ^
  --exclude-module PIL.SpiderImagePlugin ^
  --exclude-module matplotlib ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  main.py

echo.
if exist dist\InvoBiz.exe (
    copy /y dist\InvoBiz.exe InvoBiz.exe >nul
    echo ============================================
    echo   SUCCESS! InvoBiz.exe is ready.
    echo ============================================
    echo.
    echo Share with testers: InvoBiz.exe + README.txt
    ie4uinit.exe -show >nul 2>nul
) else (
    echo ============================================
    echo   BUILD FAILED - check errors above
    echo ============================================
)
echo.
pause
