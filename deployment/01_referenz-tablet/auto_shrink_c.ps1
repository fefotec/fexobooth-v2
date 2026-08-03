param(
    [UInt64]$ReserveBytes = 2147483648
)

$ErrorActionPreference = "Stop"
$LogPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "auto_shrink_c_log.txt"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Format-Size {
    param([UInt64]$Bytes)
    return ("{0:N2} GB" -f ($Bytes / 1GB))
}

function Get-LastPartition {
    param([UInt32]$DiskNumber)
    $partitions = @(Get-Partition -DiskNumber $DiskNumber | Where-Object { $_.Size -gt 0 } | Sort-Object Offset)
    if ($partitions.Count -eq 0) {
        throw "Keine Partitionen auf Disk $DiskNumber gefunden."
    }
    return $partitions[$partitions.Count - 1]
}

function Request-ChkdskRepair {
    Write-Log "[INFO] C: hat Dateisystemfehler. Windows muss C: beim naechsten Neustart reparieren."
    Write-Log "[INFO] Plane chkdsk C: /F fuer den naechsten Neustart..."

    $chkdskOutput = & cmd.exe /c "echo J|chkdsk C: /F" 2>&1
    foreach ($line in $chkdskOutput) {
        Write-Log ("chkdsk: " + $line)
    }

    Write-Log "[REBOOT_ERFORDERLICH] Tablet neu starten, Windows-Reparatur abwarten, danach defrag_and_check.bat erneut ausfuehren."
}

try {
    Write-Log "===================================================="
    Write-Log " FexoBooth Auto-Shrink C:"
    Write-Log " Ziel-Reserve am Disk-Ende: $(Format-Size $ReserveBytes)"
    Write-Log "===================================================="

    $partition = Get-Partition -DriveLetter C
    $disk = Get-Disk -Number $partition.DiskNumber
    $lastPartition = Get-LastPartition -DiskNumber $disk.Number

    $lastPartitionEnd = [UInt64]($lastPartition.Offset + $lastPartition.Size)
    $trailingBytes = [UInt64]($disk.Size - $lastPartitionEnd)

    Write-Log ("Disk: {0} ({1})" -f $disk.Number, (Format-Size ([UInt64]$disk.Size)))
    Write-Log ("C: aktuell: {0}" -f (Format-Size ([UInt64]$partition.Size)))
    Write-Log ("Letzte Partition: {0} (DriveLetter: {1})" -f $lastPartition.PartitionNumber, $lastPartition.DriveLetter)
    Write-Log ("Freie Reserve am Disk-Ende: {0}" -f (Format-Size $trailingBytes))

    if ($trailingBytes -ge $ReserveBytes) {
        Write-Log "[OK] Reserve ist bereits gross genug. Keine Verkleinerung noetig."
        exit 0
    }

    if ($lastPartition.DriveLetter -ne "C") {
        Write-Log "[FEHLER] C: ist nicht die letzte Partition auf der Disk."
        Write-Log "Automatischer Shrink wuerde dann keine freie Reserve am Disk-Ende erzeugen."
        Write-Log "Bitte Recovery-/OEM-Layout pruefen oder ein Referenz-Tablet ohne nachgelagerte Partition nutzen."
        exit 4
    }

    $missingBytes = [UInt64]($ReserveBytes - $trailingBytes)
    $targetSize = [UInt64]($partition.Size - $missingBytes)
    $supported = Get-PartitionSupportedSize -DriveLetter C

    Write-Log ("C: soll um {0} verkleinert werden." -f (Format-Size $missingBytes))
    Write-Log ("Zielgroesse C: {0}" -f (Format-Size $targetSize))
    Write-Log ("Windows erlaubt minimal: {0}" -f (Format-Size ([UInt64]$supported.SizeMin)))

    if ($targetSize -lt [UInt64]$supported.SizeMin) {
        Write-Log "[FEHLER] Windows erlaubt diese Verkleinerung aktuell nicht."
        Write-Log "Bitte prepare_master_for_capture.bat erneut ausfuehren, neu starten und defrag_and_check.bat nochmal ausfuehren."
        exit 2
    }

    try {
        Resize-Partition -DriveLetter C -Size $targetSize
    }
    catch {
        $resizeMessage = $_.Exception.Message
        Write-Log ("[FEHLER] Resize-Partition: " + $resizeMessage)

        if ($resizeMessage -match "volume with errors|Volume.*Fehler|Fehler.*Volume|Dateisystemfehler|errors") {
            Request-ChkdskRepair
            exit 5
        }

        throw
    }
    Start-Sleep -Seconds 2

    $partition = Get-Partition -DriveLetter C
    $disk = Get-Disk -Number $partition.DiskNumber
    $lastPartition = Get-LastPartition -DiskNumber $disk.Number
    $lastPartitionEnd = [UInt64]($lastPartition.Offset + $lastPartition.Size)
    $newTrailingBytes = [UInt64]($disk.Size - $lastPartitionEnd)

    Write-Log ("C: nach Shrink: {0}" -f (Format-Size ([UInt64]$partition.Size)))
    Write-Log ("Reserve am Disk-Ende: {0}" -f (Format-Size $newTrailingBytes))

    if ($newTrailingBytes -lt $ReserveBytes) {
        Write-Log "[FEHLER] Nach dem Shrink sind noch keine 2 GB Reserve vorhanden."
        exit 3
    }

    Write-Log "[OK] C: wurde erfolgreich vorbereitet. Das Image hat jetzt 2 GB Sicherheitsreserve."
    exit 0
}
catch {
    Write-Log ("[FEHLER] " + $_.Exception.Message)
    exit 1
}
