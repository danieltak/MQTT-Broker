# Builds the Windows app as a one-folder bundle (Qt stays as separate, replaceable DLLs for LGPL compliance).
param(
    [string]$Python = "python",
    [string]$Version = "",
    # Override to build outside synced folders (e.g. OneDrive locks files during the build)
    [string]$DistPath = "dist",
    [string]$WorkPath = "build"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    # PyInstaller logs to stderr; Windows PowerShell would treat that as an error under "Stop"
    $ErrorActionPreference = "Continue"
    & $Python -m PyInstaller --noconfirm --clean --windowed `
        --name MQTTBroker `
        --specpath $WorkPath `
        --workpath $WorkPath `
        --distpath $DistPath `
        --collect-data mqtt_broker `
        --hidden-import mqtt_broker.plugin `
        --hidden-import amqtt.plugins.authentication `
        packaging/launcher.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
    $ErrorActionPreference = "Stop"

    $app = Join-Path $DistPath "MQTTBroker"
    Copy-Item LICENSE (Join-Path $app "LICENSE.txt")
    Copy-Item packaging/THIRD_PARTY_NOTICES.txt (Join-Path $app "THIRD_PARTY_NOTICES.txt")

    if ($Version) {
        $zip = Join-Path $DistPath "MQTTBroker-v$Version-windows-x64.zip"
        if (Test-Path $zip) { Remove-Item $zip }
        Compress-Archive -Path $app -DestinationPath $zip
        Write-Output "Created $zip"
    }
}
finally {
    Pop-Location
}
