@echo off
REM =====================================================
REM Fexobooth - DEVELOPER MODE
REM =====================================================
REM Startet Fexobooth mit:
REM   - DEBUG Logging (Console + Datei)
REM   - CPU/RAM Overlay in der Top-Bar
REM =====================================================

cd /d "%~dp0"
echo.
echo  ========================================
echo   FEXOBOOTH - DEVELOPER MODE
echo  ========================================
echo.
echo   DEBUG Logging aktiviert
echo   CPU/RAM Overlay wird angezeigt
echo.
echo  ========================================
echo.

python src/main.py --dev

pause
