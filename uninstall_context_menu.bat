@echo off
REM Removes the "Play with PCM-Player" entry from the right-click menu.
reg delete "HKCU\Software\Classes\*\shell\PlayWithPCMPlayer" /f >nul 2>&1
if %errorlevel%==0 (
    echo.
    echo  Removed: "Play with PCM-Player" is gone from the right-click menu.
) else (
    echo.
    echo  Nothing to remove ^(the entry was not registered^).
)
echo.
pause
