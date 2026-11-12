# Launches the packaged app and fails if it crashes or (on Windows) never shows its main window.
param([string]$DistPath = "dist", [int]$Seconds = 15)
$ErrorActionPreference = "Stop"

if ($IsMacOS) {
    $exe = Join-Path $DistPath "MQTTBroker.app/Contents/MacOS/MQTTBroker"
}
elseif ($IsLinux) {
    $exe = Join-Path $DistPath "MQTTBroker/MQTTBroker"
}
else {
    $exe = Join-Path $DistPath "MQTTBroker/MQTTBroker.exe"
}
if (-not (Test-Path $exe)) { throw "Executable not found: $exe" }
# CI runners on Linux/macOS have no display server
if ($IsLinux -or $IsMacOS) { $env:QT_QPA_PLATFORM = "offscreen" }

$p = Start-Process (Resolve-Path $exe).Path -PassThru
try {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $windowShown = $false
    do {
        Start-Sleep -Seconds 1
        $p.Refresh()
        if (-not ($IsLinux -or $IsMacOS)) { $windowShown = $p.MainWindowTitle -eq "MQTT Broker" }
    } until ($p.HasExited -or $windowShown -or (Get-Date) -gt $deadline)

    if ($p.HasExited) { throw "App exited during startup (exit code $($p.ExitCode))" }
    if (-not ($IsLinux -or $IsMacOS) -and -not $windowShown) { throw "Main window was not shown" }
}
finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
}
Write-Output "Smoke test passed: $exe"
