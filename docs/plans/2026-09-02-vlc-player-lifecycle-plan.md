# VLC-Player-Lebenszyklus 2.4.64 – Umsetzungsplan

## Ziel

Den in den Box-155-Logs nachgewiesenen VLC-Ressourcenstau beseitigen, ohne den
Webcam-, Canon- oder Nikon-Aufnahmeweg zu verändern.

## Schritte

1. In `src/ui/vlc_player.py` einen unabhängig testbaren Besitzer für genau eine
   VLC-Instanz und einen Player einführen. Medienreferenzen werden nach
   `set_media()` ausnahmesicher freigegeben; Fehlerfreigabe und Wiederaufbau sind
   auf einen Thread und zwei Generationen begrenzt.
2. In `src/ui/screens/video.py` Warmup und Wiedergabe auf diesen Besitzer
   umstellen. Der Warmup erzeugt das später verwendete Paar, alle Tk-Rückrufe
   erhalten eine Wiedergabe-Generation, Developer-Logs melden Lebenszyklus und
   Ressourcenzahlen.
3. In `src/app.py` den Video-Screen wiederverwenden und beim App-Shutdown den
   nicht blockierenden Video-Close-Hook aufrufen.
4. Fake-VLC-Regressionstests für mehrere hundert Clips, genaues Media-Release,
   Fehlerstau, Wiederaufbau und Shutdown ergänzen. Die Screen-/Callback-Regeln
   mit kleinen Quell- beziehungsweise Objekt-Tests absichern.
5. Gemeinsame Build-Version auf 2.4.64 setzen, Changelog und interne
   Projektstände aktualisieren.
6. Neue Tests, bestehende Kamera-/Hänger-Schutztests, Compile-Check und
   versionsbezogenen Smoke-Test ausführen. Danach bleibt nur der reale
   mehrstündige Tablet-Test offen.
