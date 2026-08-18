@echo off
title Building LiveSpeech Translator Executable...
echo =======================================================
echo   LiveSpeech Translator | Building Standalone Executable (.exe)
echo =======================================================
echo.

python -m PyInstaller --clean livespeech-translator.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =======================================================
    echo   BUILD SUCCESSFUL!
    echo   Executable located at: dist\LiveSpeech-Translator.exe
    echo =======================================================
    echo.
) else (
    echo.
    echo =======================================================
    echo   BUILD FAILED! Please check the error messages above.
    echo =======================================================
    echo.
)
pause
