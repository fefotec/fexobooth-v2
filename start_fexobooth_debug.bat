@echo off
REM =====================================================
REM Fexobooth - Developer Mode
REM =====================================================
REM Startet Fexobooth mit sichtbarer Konsole + Dev-Tools
REM =====================================================

cd /d "%~dp0"
python src/main.py --dev

pause
