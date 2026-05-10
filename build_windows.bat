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
echo [3/4] Building executable ...
REM Defaults: --onedir (folder bundle, faster startup, fewer AV false positives).
REM   set ONEFILE=1   -> single self-extracting PCMPlayer.exe
REM   set DEBUG=1     -> keep console visible + bootloader logs (diagnostic mode)
REM --collect-all bundles ALL submodules + binaries + data of these libs (including
REM   the native libsndfile / portaudio DLLs they need at runtime).
REM We invoke PyInstaller via "python -m PyInstaller" instead of the pyinstaller.exe
REM shim because the shim has the original venv's python path baked in and breaks
REM if the venv was relocated.
set "ONEDIR_FLAG=--onedir"
if /i "%ONEFILE%"=="1" set "ONEDIR_FLAG=--onefile"

set "WINDOW_FLAG=--windowed"
set "DEBUG_FLAG="
if /i "%DEBUG%"=="1" (
    set "WINDOW_FLAG=--console"
    set "DEBUG_FLAG=--debug bootloader"
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  %ONEDIR_FLAG% ^
  %WINDOW_FLAG% ^
  %DEBUG_FLAG% ^
  --name "PCMPlayer" ^
  --icon "icon.ico" ^
  --add-data "icon.ico;." ^
  --collect-all sounddevice ^
  --collect-all soundfile ^
  pcm_player.py || goto :fail

echo.
echo [4/4] Cleaning intermediate folders ...
if exist build rmdir /s /q build
if exist PCMPlayer.spec del /q PCMPlayer.spec

echo.
echo ============================================================
echo  BUILD COMPLETE
echo ============================================================
if /i "%ONEFILE%"=="1" (
    echo  Portable executable: %CD%\dist\PCMPlayer.exe
    echo  Just copy that file anywhere; no installation needed.
) else (
    echo  Portable folder:    %CD%\dist\PCMPlayer\
    echo  Run:                %CD%\dist\PCMPlayer\PCMPlayer.exe
    echo  Distribute the entire dist\PCMPlayer folder ^(zip it if you want one file^).
)
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
