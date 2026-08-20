@echo off
rem ============================================================
rem  FexoBooth - Kamera-Messung starten  (2.4.37)
rem ============================================================
rem  Doppelklick genuegt. Das Programm misst 2 bis 4 Minuten, wie
rem  schnell die Kamera bei verschiedenen Aufloesungen ist, und
rem  legt das Ergebnis als Textdatei ab.
rem
rem  WICHTIG: Die Fotobox-Software darf dabei NICHT laufen, sonst
rem  ist die Kamera belegt und die Messung ist wertlos. Das prueft
rem  diese Datei und beendet sie bei Bedarf.
rem
rem  WARUM IN DIESEM FENSTER NIE ETWAS PASSIERT (Feld 19.08.2026):
rem  fexobooth.exe ist ein Fenster-Programm OHNE Konsole. Es kann
rem  hier baulich nichts ausgeben. Der einzige Fortschrittsanzeiger
rem  ist die mitwachsende Berichtsdatei - darauf weist der Text
rem  unten deshalb ausdruecklich hin.
rem
rem  ASCII ohne Umlaute - der Inhalt wird von cmd.exe gelesen.
rem ============================================================
title FexoBooth - Kamera-Messung
color 0B
setlocal

set "EXE=C:\FexoBooth\fexobooth.exe"
set "BERICHT=C:\FexoBooth\logs\kamera-messung.txt"
set "BERICHT2=C:\ProgramData\FexoBox\kamera-messung.txt"
set "VORHER=C:\FexoBooth\logs\kamera-messung-vorher.txt"

echo.
echo   ===============================================
echo    FexoBooth - Kamera-Messung
echo   ===============================================
echo.

if not exist "%EXE%" (
    echo   FEHLER: %EXE% nicht gefunden.
    echo   Ist FexoBooth auf dieser Box installiert?
    echo.
    pause
    exit /b 1
)

rem --- Laeuft die Fotobox gerade? Dann ist die Kamera belegt. ---
tasklist /FI "IMAGENAME eq fexobooth.exe" 2>nul | find /I "fexobooth.exe" >nul
if not errorlevel 1 (
    echo   Die Fotobox-Software laeuft gerade.
    echo   Fuer die Messung muss sie beendet werden - die Kamera
    echo   kann nur von einem Programm gleichzeitig benutzt werden.
    echo.
    choice /C JN /N /M "   Jetzt beenden und messen? [J/N] "
    if errorlevel 2 (
        echo.
        echo   Abgebrochen - es wurde nichts geaendert.
        echo.
        pause
        exit /b 0
    )
    echo.
    echo   Beende Fotobox-Software...
    taskkill /IM fexobooth.exe /F >nul 2>&1

    rem Nicht blind warten, sondern nachsehen: Erst wenn der Prozess
    rem wirklich weg ist, gibt Windows die Kamera frei. Nach taskkill /F ist
    rem das praktisch immer schon in der ersten Runde der Fall. Harte
    rem Obergrenze 10 Runden (auf einer langsamen Box rund 30 Sekunden, weil
    rem tasklist dort mehrere Sekunden braucht) - ohne Obergrenze haengt am
    rem Ende diese Datei statt der Messung.
    set "WEG="
    for /L %%i in (1,1,10) do (
        if not defined WEG (
            tasklist /FI "IMAGENAME eq fexobooth.exe" 2>nul | find /I "fexobooth.exe" >nul
            if errorlevel 1 (
                set "WEG=ja"
            ) else (
                ping -n 2 127.0.0.1 >nul
            )
        )
    )
    if not defined WEG (
        echo.
        echo   [!!] Die Fotobox-Software laeuft immer noch.
        echo   Bitte die Box neu starten und diese Datei danach
        echo   erneut per Doppelklick oeffnen.
        echo.
        pause
        exit /b 1
    )
    echo   Fotobox-Software beendet.
)

rem --- Alten Bericht aufheben statt loeschen ---
rem Ein frueheres Ergebnis kann noch gebraucht werden (Vergleich!),
rem darf aber nicht mit dem neuen verwechselt werden.
if exist "%BERICHT%" (
    if exist "%VORHER%" del /Q "%VORHER%" >nul 2>&1
    move /Y "%BERICHT%" "%VORHER%" >nul 2>&1
)

echo.
echo   ===============================================
echo    Die Messung dauert normalerweise 2 bis 4 Minuten.
echo    Auf langsamen Boxen kann es laenger dauern -
echo    das ist kein Fehler. Nach spaetestens rund 10
echo    Minuten beendet sich die Messung selbst.
echo   ===============================================
echo.
echo   SO SEHEN SIE DEN FORTSCHRITT:
echo   Oeffnen Sie waehrenddessen die Datei
echo      C:\FexoBooth\logs\kamera-messung.txt   (Doppelklick)
echo   Ganz oben steht, welcher Schritt gerade laeuft und seit wann.
echo   Zum Aktualisieren die Datei schliessen und neu oeffnen.
echo.
echo   Aendert sich die Datei 3 Minuten lang nicht mehr, haengt die
echo   Messung fest. Dann:
echo      Strg+Umschalt+Esc -^> Reiter "Details" -^> fexobooth.exe
echo      anklicken -^> "Task beenden"
echo.
echo   ACHTUNG: Dieses schwarze Fenster einfach zuzuklicken reicht
echo   NICHT! Die Messung laeuft dann unsichtbar weiter und haelt
echo   die Kamera belegt.
echo.

rem ------------------------------------------------------------
rem  NOTBREMSE (2.4.37)
rem  Bis 2.4.36 stand hier schlicht  "%EXE%" --kamera-test  und
rem  diese Datei wartete OHNE JEDE OBERGRENZE auf das Programmende.
rem  Genau so entstand der Feld-Befund vom 20.08.2026: "ich warte
rem  nun schon 5 min aber der test wird immernoch angezeigt".
rem  Jetzt wird die Messung losgeschickt und beobachtet - meldet
rem  sie sich nach rund 10 Minuten nicht zurueck, wird sie hart
rem  beendet. Der Bericht waechst mit, es geht also nichts verloren.
rem  (Der Rueckgabewert des Programms geht dabei verloren; ob ein
rem  Bericht existiert, ist das aussagekraeftigere Signal.)
rem ------------------------------------------------------------
start "" /B "%EXE%" --kamera-test

set /a RUNDEN=0
:MESSUNG_BEOBACHTEN
ping -n 6 127.0.0.1 >nul
tasklist /FI "IMAGENAME eq fexobooth.exe" 2>nul | find /I "fexobooth.exe" >nul
if errorlevel 1 goto MESSUNG_ENDE
set /a RUNDEN+=1
if %RUNDEN% LSS 120 goto MESSUNG_BEOBACHTEN

echo.
echo   [!!] Die Messung kam nicht mehr weiter und wird jetzt beendet.
echo   Der bis dahin geschriebene Bericht bleibt erhalten.
taskkill /IM fexobooth.exe /F >nul 2>&1

:MESSUNG_ENDE
echo.
if exist "%BERICHT%" (
    echo   [OK] Fertig! Der Bericht oeffnet sich jetzt.
    echo   Datei: %BERICHT%
    start "" notepad.exe "%BERICHT%"
) else (
    if exist "%BERICHT2%" (
        rem Ausweichpfad: den benutzt das Programm, wenn der Log-Ordner
        rem nicht beschreibbar ist.
        echo   [OK] Fertig! Der Bericht liegt am Ausweichort.
        echo   Datei: %BERICHT2%
        start "" notepad.exe "%BERICHT2%"
    ) else (
        echo   [!!] Es wurde KEIN Bericht geschrieben.
        echo   Bitte trotzdem den Ordner C:\FexoBooth\logs mitschicken -
        echo   in absturz.log steht dann, woran es lag.
    )
)

echo.
echo   NAECHSTER SCHRITT: Ordner C:\FexoBooth\logs komplett
echo   auf den USB-Stick kopieren und an Claude schicken.
echo.
echo   Die Fotobox startet beim naechsten Neustart wieder normal.
echo.
pause
