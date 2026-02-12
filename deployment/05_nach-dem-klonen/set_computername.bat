@echo off
chcp 65001 >nul

echo.
echo ===================================================
echo    FexoBooth - Computernamen aendern
echo ===================================================
echo.
echo Aktueller Computername: %COMPUTERNAME%
echo.

:: Admin-Check
net session >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Dieses Script muss als Administrator ausgefuehrt werden!
    echo Rechtsklick ^> "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

set /p NEWNAME="Neuer Name (z.B. FEXOBOX-001): "

if "%NEWNAME%"=="" (
    echo Kein Name eingegeben. Abbruch.
    pause
    exit /b 0
)

:: Name darf max 15 Zeichen, keine Leerzeichen, keine Sonderzeichen
echo %NEWNAME% | findstr /R "^[A-Za-z0-9-]*$" >nul
if errorlevel 1 (
    echo FEHLER: Name darf nur Buchstaben, Zahlen und Bindestriche enthalten!
    pause
    exit /b 1
)

echo.
echo Computername wird geaendert: %COMPUTERNAME% -^> %NEWNAME%
echo.

powershell -Command "Rename-Computer -NewName '%NEWNAME%' -Force" 2>nul

if errorlevel 1 (
    echo FEHLER: Konnte Computernamen nicht aendern.
    pause
    exit /b 1
)

echo [OK] Computername wird nach Neustart geaendert zu: %NEWNAME%
echo.

choice /C JN /M "Jetzt neustarten? (J)a/(N)ein"
if errorlevel 2 goto :end
shutdown /r /t 5 /c "Neustart fuer Namensaenderung zu %NEWNAME%"
echo Neustart in 5 Sekunden...
goto :done

:end
echo.
echo Bitte das Tablet manuell neustarten damit der Name uebernommen wird.

:done
echo.
pause
