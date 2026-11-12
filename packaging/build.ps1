# Builds the app as a one-folder bundle (Qt stays as separate, replaceable libraries for LGPL compliance).
# Packages it per platform: Windows .zip, Linux .tar.gz, macOS .app in a .zip.
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
    $notices = @{ "LICENSE" = "LICENSE.txt"; "packaging/THIRD_PARTY_NOTICES.txt" = "THIRD_PARTY_NOTICES.txt" }
    foreach ($source in $notices.Keys) { Copy-Item $source (Join-Path $app $notices[$source]) }

    if ($Version) {
        $arch = if ($IsLinux -or $IsMacOS) { (uname -m) } else { $env:PROCESSOR_ARCHITECTURE }
        $arch = switch -Regex ($arch) {
            '^(x86_64|AMD64)$' { 'x64' }
            '^(arm64|aarch64|ARM64)$' { 'arm64' }
            default { $arch.ToLower() }
        }
        $base = Join-Path $DistPath "MQTTBroker-v$Version"
        if ($IsMacOS) {
            $stage = "$base-macos"
            $archive = "$base-macos-$arch.zip"
            Remove-Item -Recurse -Force $stage, $archive -ErrorAction SilentlyContinue
            New-Item -ItemType Directory $stage | Out-Null
            # ditto keeps the bundle's framework symlinks and executable bits
            ditto (Join-Path $DistPath "MQTTBroker.app") (Join-Path $stage "MQTTBroker.app")
            foreach ($source in $notices.Keys) { Copy-Item $source (Join-Path $stage $notices[$source]) }
            ditto -c -k --keepParent $stage $archive
        }
        elseif ($IsLinux) {
            $archive = "$base-linux-$arch.tar.gz"
            Remove-Item $archive -ErrorAction SilentlyContinue
            tar -czf $archive -C $DistPath MQTTBroker
        }
        else {
            $archive = "$base-windows-$arch.zip"
            Remove-Item $archive -ErrorAction SilentlyContinue
            Compress-Archive -Path $app -DestinationPath $archive
        }
        if (-not (Test-Path $archive)) { throw "Packaging failed: $archive was not created" }
        Write-Output "Created $archive"
    }
}
finally {
    Pop-Location
}
