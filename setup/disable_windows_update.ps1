param(
    [string]$InstallDir = "C:\FexoBooth",
    [switch]$SkipTaskRegistration
)

$ErrorActionPreference = "Continue"
$script:HadWarnings = $false

$LogDir = Join-Path $InstallDir "logs"
$LogFile = Join-Path $LogDir "windows_update_lockdown.log"

function Write-LockdownLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $line = "{0} | {1} | {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -Path $LogDir -ItemType Directory -Force | Out-Null
        }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch {
        Write-Host "Logging failed: $($_.Exception.Message)"
    }
}

function Test-Admin {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Set-DwordPolicy {
    param(
        [string]$Path,
        [string]$Name,
        [int]$Value
    )

    try {
        if (-not (Test-Path $Path)) {
            New-Item -Path $Path -Force | Out-Null
        }
        New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null
        Write-LockdownLog "Registry gesetzt: $Path\$Name=$Value"
    } catch {
        $script:HadWarnings = $true
        Write-LockdownLog "Registry konnte nicht gesetzt werden: $Path\$Name ($($_.Exception.Message))" "WARN"
    }
}

function Set-StringPolicy {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )

    try {
        if (-not (Test-Path $Path)) {
            New-Item -Path $Path -Force | Out-Null
        }
        New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType String -Force | Out-Null
        Write-LockdownLog "Registry gesetzt: $Path\$Name=$Value"
    } catch {
        $script:HadWarnings = $true
        Write-LockdownLog "Registry konnte nicht gesetzt werden: $Path\$Name ($($_.Exception.Message))" "WARN"
    }
}

function Disable-ServiceHard {
    param([string]$Name)

    try {
        $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-LockdownLog "Dienst nicht vorhanden: $Name"
            return
        }

        try {
            if ($svc.Status -ne "Stopped") {
                Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 500
            }
        } catch {
            Write-LockdownLog "Dienst konnte nicht gestoppt werden: $Name ($($_.Exception.Message))" "WARN"
        }

        & sc.exe config $Name start= disabled | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $script:HadWarnings = $true
            Write-LockdownLog "sc.exe konnte Starttyp nicht setzen: $Name (Exit $LASTEXITCODE)" "WARN"
        }

        $serviceRegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
        if (Test-Path $serviceRegPath) {
            New-ItemProperty -Path $serviceRegPath -Name "Start" -Value 4 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null
        }

        Write-LockdownLog "Dienst deaktiviert: $Name"
    } catch {
        $script:HadWarnings = $true
        Write-LockdownLog "Dienst-Deaktivierung fehlgeschlagen: $Name ($($_.Exception.Message))" "WARN"
    }
}

function Disable-ScheduledTaskSafe {
    param([string]$TaskName)

    try {
        & schtasks.exe /Change /TN $TaskName /Disable | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-LockdownLog "Task deaktiviert: $TaskName"
        } else {
            Write-LockdownLog "Task nicht deaktiviert/nicht vorhanden: $TaskName (Exit $LASTEXITCODE)" "INFO"
        }
    } catch {
        Write-LockdownLog "Task konnte nicht deaktiviert werden: $TaskName ($($_.Exception.Message))" "INFO"
    }
}

function Register-ReassertTask {
    if ($SkipTaskRegistration) {
        Write-LockdownLog "Task-Registrierung uebersprungen (Scheduled-Task-Lauf)"
        return
    }

    $scriptPath = $PSCommandPath
    if (-not $scriptPath) {
        $scriptPath = Join-Path $InstallDir "setup\disable_windows_update.ps1"
    }

    if (-not (Test-Path $scriptPath)) {
        $script:HadWarnings = $true
        Write-LockdownLog "Lockdown-Script fuer Scheduled Task nicht gefunden: $scriptPath" "WARN"
        return
    }

    $action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -InstallDir `"$InstallDir`" -SkipTaskRegistration"
    $taskSpecs = @(
        @{ Name = "FexoBooth Windows Update Lockdown Startup"; Schedule = "ONSTART" },
        @{ Name = "FexoBooth Windows Update Lockdown Logon"; Schedule = "ONLOGON" }
    )

    foreach ($spec in $taskSpecs) {
        $taskName = $spec["Name"]
        $schedule = $spec["Schedule"]
        try {
            & schtasks.exe /Create /TN $taskName /SC $schedule /RU SYSTEM /RL HIGHEST /TR $action /F | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-LockdownLog "Re-Assert Task registriert: $taskName"
            } else {
                $script:HadWarnings = $true
                Write-LockdownLog "Re-Assert Task konnte nicht registriert werden: $taskName (Exit $LASTEXITCODE)" "WARN"
            }
        } catch {
            $script:HadWarnings = $true
            Write-LockdownLog "Re-Assert Task Fehler: $taskName ($($_.Exception.Message))" "WARN"
        }
    }
}

Write-LockdownLog "Windows Update Lockdown startet (InstallDir=$InstallDir)"

if (-not (Test-Admin)) {
    Write-LockdownLog "Dieses Script muss als Administrator laufen." "ERROR"
    exit 1
}

$wuPolicyPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
$auPolicyPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"

# Offizielle Windows-Update-Policy-Pfade. NoAutoUpdate blockiert automatische
# Scans/Installationen; AUOptions=2 ist ein zusaetzlicher Fallback auf "notify".
Set-DwordPolicy -Path $auPolicyPath -Name "NoAutoUpdate" -Value 1
Set-DwordPolicy -Path $auPolicyPath -Name "AUOptions" -Value 2
Set-DwordPolicy -Path $auPolicyPath -Name "NoAutoRebootWithLoggedOnUsers" -Value 1
Set-DwordPolicy -Path $auPolicyPath -Name "UseWUServer" -Value 1

Set-DwordPolicy -Path $wuPolicyPath -Name "DoNotConnectToWindowsUpdateInternetLocations" -Value 1
Set-DwordPolicy -Path $wuPolicyPath -Name "SetDisableUXWUAccess" -Value 1
Set-DwordPolicy -Path $wuPolicyPath -Name "DisableWindowsUpdateAccess" -Value 1
Set-DwordPolicy -Path $wuPolicyPath -Name "ExcludeWUDriversInQualityUpdate" -Value 1
Set-DwordPolicy -Path $wuPolicyPath -Name "DisableOSUpgrade" -Value 1

# Dummy-WSUS auf localhost. So bleibt Windows Update policy-gesteuert, hat aber
# keine echte Microsoft-Quelle, selbst wenn ein Update-Dienst wieder startet.
Set-StringPolicy -Path $wuPolicyPath -Name "WUServer" -Value "http://127.0.0.1:9"
Set-StringPolicy -Path $wuPolicyPath -Name "WUStatusServer" -Value "http://127.0.0.1:9"

$services = @(
    "wuauserv",
    "UsoSvc",
    "WaaSMedicSvc",
    "DoSvc",
    "BITS",
    "uhssvc"
)

foreach ($serviceName in $services) {
    Disable-ServiceHard -Name $serviceName
}

$scheduledTasks = @(
    "\Microsoft\Windows\WindowsUpdate\Scheduled Start",
    "\Microsoft\Windows\WindowsUpdate\sih",
    "\Microsoft\Windows\WindowsUpdate\sihboot",
    "\Microsoft\Windows\UpdateOrchestrator\Schedule Scan",
    "\Microsoft\Windows\UpdateOrchestrator\Schedule Scan Static Task",
    "\Microsoft\Windows\UpdateOrchestrator\USO_UxBroker",
    "\Microsoft\Windows\UpdateOrchestrator\Reboot",
    "\Microsoft\Windows\UpdateOrchestrator\Reboot_AC",
    "\Microsoft\Windows\UpdateOrchestrator\Reboot_Battery",
    "\Microsoft\Windows\UpdateOrchestrator\Maintenance Install",
    "\Microsoft\Windows\UpdateOrchestrator\Policy Install",
    "\Microsoft\Windows\UpdateOrchestrator\Report policies",
    "\Microsoft\Windows\UpdateOrchestrator\Refresh Settings",
    "\Microsoft\Windows\UpdateOrchestrator\Resume On Boot",
    "\Microsoft\Windows\UpdateOrchestrator\Schedule Retry Scan",
    "\Microsoft\Windows\UpdateOrchestrator\Schedule Work",
    "\Microsoft\Windows\UpdateOrchestrator\Start Oobe Expedite Work",
    "\Microsoft\Windows\UpdateOrchestrator\UpdateAssistant",
    "\Microsoft\Windows\UpdateOrchestrator\UpdateAssistantCalendarRun",
    "\Microsoft\Windows\UpdateOrchestrator\UpdateAssistantWakeupRun",
    "\Microsoft\Windows\WaaSMedic\PerformRemediation",
    "\Microsoft\Windows\InstallService\ScanForUpdates",
    "\Microsoft\Windows\InstallService\ScanForUpdatesAsUser",
    "\Microsoft\Windows\InstallService\SmartRetry",
    "\Microsoft\Windows\InstallService\WakeUpAndContinueUpdates",
    "\Microsoft\Windows\InstallService\WakeUpAndScanForUpdates",
    "\Microsoft\Windows\UpdateAssistant\UpdateAssistant",
    "\Microsoft\Windows\UpdateAssistant\UpdateAssistantCalendarRun",
    "\Microsoft\Windows\UpdateAssistant\UpdateAssistantWakeupRun",
    "\Microsoft\Windows\UNP\RunCampaignManager"
)

foreach ($taskName in $scheduledTasks) {
    Disable-ScheduledTaskSafe -TaskName $taskName
}

Register-ReassertTask

try {
    $wuStart = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\wuauserv" -Name "Start" -ErrorAction SilentlyContinue).Start
    $noAuto = (Get-ItemProperty -Path $auPolicyPath -Name "NoAutoUpdate" -ErrorAction SilentlyContinue).NoAutoUpdate
    Write-LockdownLog "Pruefung: wuauserv.Start=$wuStart, NoAutoUpdate=$noAuto"
} catch {
    Write-LockdownLog "Abschlusspruefung nicht vollstaendig moeglich: $($_.Exception.Message)" "WARN"
}

if ($script:HadWarnings) {
    Write-LockdownLog "Windows Update Lockdown abgeschlossen mit Warnungen. Details siehe Log." "WARN"
} else {
    Write-LockdownLog "Windows Update Lockdown erfolgreich abgeschlossen."
}

# Installer soll nicht abbrechen, wenn einzelne geschuetzte Windows-Komponenten
# sich verweigern. Der Re-Assert-Task setzt die Policy bei jedem Boot/Login neu.
exit 0
