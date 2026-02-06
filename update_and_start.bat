@echo off
REM =====================================================
REM Fexobooth - Update & Start
REM =====================================================
REM Holt neueste Version von GitHub und startet Fexobooth
REM Funktioniert von jedem Speicherort aus
REM =====================================================

cd /d "%~dp0"

echo.
echo ===================================
echo  FEXOBOOTH UPDATE ^& START
echo ===================================
echo.
echo Projektverzeichnis: %cd%

echo.
echo [1/3] Hole neueste Version von GitHub...
git pull

echo.
echo [2/3] Installiere/aktualisiere Python-Pakete...
pip install -r requirements.txt --quiet

echo.
echo ========================================================
echo  UPDATE ABGESCHLOSSEN - STARTE FEXOBOOTH
echo ========================================================
echo.

echo [3/3] Starte Fexobooth...
python src/main.py

pause
