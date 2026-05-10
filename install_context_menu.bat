@echo off
REM ============================================================
REM  install_context_menu.bat
REM  Adds "Play with PCM-Player" to the right-click menu of:
REM    - any FILE
REM    - any FOLDER
REM    - the empty BACKGROUND inside a folder (right-click empty space)
REM
REM  Multi-select aware (MultiSelectModel="Player"): selecting many
REM  files and choosing the verb sends them all as a single playlist
REM  to a single PCMPlayer.exe instance.
REM
REM  Per-user install (HKCU). No admin required.
REM  Place this file next to PCMPlayer.exe and double-click.
REM ============================================================
setlocal

set "EXE=%~dp0PCMPlayer.exe"
set "FILE_KEY=HKCU\Software\Classes\*\shell\PlayWithPCMPlayer"
set "DIR_KEY=HKCU\Software\Classes\Directory\shell\PlayWithPCMPlayer"
set "BG_KEY=HKCU\Software\Classes\Directory\Background\shell\PlayWithPCMPlayer"

if not exist "%EXE%" (
    echo.
    echo  ERROR: PCMPlayer.exe was not found in this folder:
    echo    %~dp0
    echo  Place install_context_menu.bat in the same folder as PCMPlayer.exe.
    echo.
    pause
    exit /b 1
)

REM Files
reg add "%FILE_KEY%"         /ve /d "Play with PCM-Player" /f >nul
reg add "%FILE_KEY%"         /v "Icon"             /d "\"%EXE%\",0" /f >nul
reg add "%FILE_KEY%"         /v "MultiSelectModel" /d "Player"      /f >nul
reg add "%FILE_KEY%\command" /ve /d "\"%EXE%\" %%1" /f >nul

REM Folders (right-click on a folder)
reg add "%DIR_KEY%"          /ve /d "Play with PCM-Player" /f >nul
reg add "%DIR_KEY%"          /v "Icon"             /d "\"%EXE%\",0" /f >nul
reg add "%DIR_KEY%"          /v "MultiSelectModel" /d "Player"      /f >nul
reg add "%DIR_KEY%\command"  /ve /d "\"%EXE%\" %%1" /f >nul

REM Folder background (right-click empty space inside a folder; %V is the cwd)
reg add "%BG_KEY%"           /ve /d "Play with PCM-Player" /f >nul
reg add "%BG_KEY%"           /v "Icon"             /d "\"%EXE%\",0" /f >nul
reg add "%BG_KEY%\command"   /ve /d "\"%EXE%\" \"%%V\"" /f >nul

echo.
echo  Installed.
echo  Right-click a file, a folder, or inside a folder, and pick
echo  "Play with PCM-Player".
echo.
echo  To remove: run uninstall_context_menu.bat from this folder.
echo.
pause
