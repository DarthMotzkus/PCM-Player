@echo off
REM Removes "Play with PCM-Player" from file, folder and folder-background menus.
reg delete "HKCU\Software\Classes\*\shell\PlayWithPCMPlayer"                   /f >nul 2>&1
reg delete "HKCU\Software\Classes\Directory\shell\PlayWithPCMPlayer"           /f >nul 2>&1
reg delete "HKCU\Software\Classes\Directory\Background\shell\PlayWithPCMPlayer" /f >nul 2>&1
echo.
echo  Removed (if it was there): "Play with PCM-Player" entries.
echo.
pause
