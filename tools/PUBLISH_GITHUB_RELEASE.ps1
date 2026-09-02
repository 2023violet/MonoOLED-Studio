param(
    [Parameter(Mandatory=$false)]
    [string]$Tag = $env:GITHUB_REF_NAME
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Get-Content 'src/VERSION' -Raw).Trim()
$ExpectedTag = "v$Version"
if ($Tag -ne $ExpectedTag) {
    throw "Tag/version mismatch: tag='$Tag' expected='$ExpectedTag'"
}

& python tools\VERIFY_RELEASE_TAG.py $Tag --require-git-head
if ($LASTEXITCODE -ne 0) { throw "Release tag/HEAD verification failed" }
$GitCommit = (& git rev-parse HEAD).Trim()
if (-not $GitCommit) { throw "Unable to resolve release git commit" }

$Zip = "release/MonoOLEDStudio_v${Version}_Windows_x64.zip"
$Sha = "release/MonoOLEDStudio_v${Version}_Windows_x64.zip.sha256"
if (-not (Test-Path $Zip)) { throw "Missing release asset: $Zip" }
if (-not (Test-Path $Sha)) { throw "Missing release checksum: $Sha" }

& python tools\BUILD_WINDOWS_RUNTIME_ZIP.py --verify $Zip --expected-version $Version --checksum $Sha --expected-git-commit $GitCommit
if ($LASTEXITCODE -ne 0) { throw "Runtime ZIP/checksum verification failed" }

# gh returns exit code 1 when the release does not exist. Invoke through cmd so
# PowerShell 7 does not surface that expected probe result as a terminating
# NativeCommandError under $ErrorActionPreference = 'Stop'.
cmd.exe /d /s /c "gh release view $Tag >nul 2>nul"
$ReleaseExists = ($LASTEXITCODE -eq 0)
if ($ReleaseExists) {
    # Published release assets are immutable in this workflow. A rerun may be
    # a no-op only when the already-published ZIP and checksum are byte-identical.
    $Temp = Join-Path ([IO.Path]::GetTempPath()) ("monooled-release-{0}-{1}" -f $Version, $PID)
    if (Test-Path $Temp) { Remove-Item -Recurse -Force $Temp }
    New-Item -ItemType Directory -Path $Temp | Out-Null
    try {
        $ZipName = Split-Path $Zip -Leaf
        $ShaName = Split-Path $Sha -Leaf
        & gh release download $Tag -p $ZipName -p $ShaName -D $Temp
        if ($LASTEXITCODE -ne 0) {
            throw "Existing release is incomplete or its assets cannot be downloaded; refusing mutation"
        }
        $RemoteZip = Join-Path $Temp $ZipName
        $RemoteSha = Join-Path $Temp $ShaName
        if (-not (Test-Path $RemoteZip) -or -not (Test-Path $RemoteSha)) {
            throw "Existing release is missing required Windows assets; refusing mutation"
        }
        & python tools\BUILD_WINDOWS_RUNTIME_ZIP.py --verify $RemoteZip --expected-version $Version --checksum $RemoteSha --expected-git-commit $GitCommit
        if ($LASTEXITCODE -ne 0) {
            throw "Existing release assets failed integrity/provenance verification"
        }
        $LocalShaText = [IO.File]::ReadAllText((Resolve-Path $Sha).Path).Trim()
        $RemoteShaText = [IO.File]::ReadAllText((Resolve-Path $RemoteSha).Path).Trim()
        if ($LocalShaText -ne $RemoteShaText) {
            throw "Refusing to replace existing release assets: local and published checksums differ"
        }
        Write-Host "[PASS] Existing release assets are identical; publish is an idempotent no-op."
        return
    }
    finally {
        if (Test-Path $Temp) { Remove-Item -Recurse -Force $Temp }
    }
}

Write-Host "[INFO] Creating GitHub Release $Tag."
& gh release create $Tag $Zip $Sha --verify-tag --generate-notes --title "MonoOLED Studio $Tag"
if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }

Write-Host "[PASS] GitHub Release assets published:"
Write-Host "       $Zip"
Write-Host "       $Sha"
