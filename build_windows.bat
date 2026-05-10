@echo off
REM ============================================================
REM  PCM Player - Build portable Windows .exe (single-file)
REM ============================================================
REM  Requirements: Python 3.10+ on PATH, internet access for pip.
REM  Run from this folder:  build_windows.bat
REM
REM  Output: dist\PCMPlayer.exe  (portable, no install needed)
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo [1/4] Creating virtual environment .venv ...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv || goto :fail
) else (
    python -m venv .venv || goto :fail
)

call .venv\Scripts\activate.bat

echo.
echo [2/4] Upgrading pip and installing build dependencies ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo.
echo [3/4] Building portable single-file executable ...
REM Using --onefile produces ONE PCMPlayer.exe that unpacks to a temp dir on launch.
REM --windowed hides the console window (it's a GUI app).
REM --noconfirm overwrites previous builds without prompting.
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "PCMPlayer" ^
  --collect-binaries sounddevice ^
  --collect-binaries soundfile ^
  --collect-data soundfile ^
  pcm_player.py || goto :fail

echo.
echo [4/4] Cleaning intermediate folders ...
if exist build rmdir /s /q build
if exist PCMPlayer.spec del /q PCMPlayer.spec

echo.
echo ============================================================
echo  BUILD COMPLETE
echo ============================================================
echo  Portable executable: %CD%\dist\PCMPlayer.exe
echo  Just copy that file anywhere; no installation needed.
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo  BUILD FAILED. Check messages above.
echo ============================================================
pause
exit /b 1
