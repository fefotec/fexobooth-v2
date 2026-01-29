@echo off
echo ===================================
echo  FEXOBOOTH UPDATE & START
echo ===================================

echo.
echo Schritt 1: Wechsle zum Projektverzeichnis...
cd C:\fexobooth\fexobooth
if %errorlevel% neq 0 (
    echo FEHLER: Projektverzeichnis nicht gefunden!
    echo Bitte pruefen: C:\fexobooth\fexobooth
    pause
    exit /b
)

echo.
echo Schritt 2: Hole neueste Version von GitHub...
git pull

echo.
echo Schritt 3: Installiere Python-Pakete...
pip install -r requirements.txt --quiet

echo.
echo ========================================================
echo  UPDATE ABGESCHLOSSEN - STARTE FEXOBOOTH
echo ========================================================
echo.

python src/main.py

pause
