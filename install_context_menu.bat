@echo off
REM ============================================================
REM  install_context_menu.bat
REM  Adds "Play with PCM-Player" to the right-click menu of any
REM  file in Windows Explorer. Multi-select aware: selecting many
REM  files and choosing the verb sends them all as a playlist.
REM
REM  Per-user install (HKCU). No admin required.
REM  Place this file next to PCMPlayer.exe and double-click.
REM ============================================================
setlocal

set "EXE=%~dp0PCMPlayer.exe"
set "KEY=HKCU\Software\Classes\*\shell\PlayWithPCMPlayer"

if not exist "%EXE%" (
    echo.
    echo  ERROR: PCMPlayer.exe was not found in this folder:
    echo    %~dp0
    echo  Place install_context_menu.bat in the same folder as PCMPlayer.exe.
    echo.
    pause
    exit /b 1
)

reg add "%KEY%"         /ve /d "Play with PCM-Player" /f >nul
reg add "%KEY%"         /v "Icon"             /d "\"%EXE%\",0" /f >nul
reg add "%KEY%"         /v "MultiSelectModel" /d "Player"      /f >nul
reg add "%KEY%\command" /ve /d "\"%EXE%\" %%1" /f >nul

echo.
echo  Installed.
echo  Right-click one or more audio files in Explorer and choose
echo  "Play with PCM-Player" to send them as a playlist.
echo.
echo  To remove: run uninstall_context_menu.bat from this folder.
echo.
pause
