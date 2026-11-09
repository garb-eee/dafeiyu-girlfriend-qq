#Requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $TargetHost,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $User,
    [Parameter(Mandatory = $true)][ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })][string] $IdentityFile,
    [Parameter(Mandatory = $true)][ValidatePattern('^SHA256:[A-Za-z0-9+/]+$')][string] $ExpectedHostFingerprint
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$knownHosts = [System.IO.Path]::GetTempFileName()
try {
    $scan = @(& ssh-keyscan.exe -T 5 -t ed25519 $TargetHost 2>$null)
    if ($LASTEXITCODE -ne 0 -or $scan.Count -eq 0) {
        throw "Could not read the ED25519 SSH host key from $TargetHost."
    }
    [System.IO.File]::WriteAllLines($knownHosts, $scan, (New-Object System.Text.UTF8Encoding($false)))

    $fingerprintLine = (& ssh-keygen.exe -lf $knownHosts -E sha256) -join ' '
    if ($fingerprintLine -notmatch '(SHA256:[A-Za-z0-9+/]+)') {
        throw 'ssh-keygen did not return a SHA256 host fingerprint.'
    }
    $actual = $Matches[1]
    if ($actual -cne $ExpectedHostFingerprint) {
        throw "HOST IDENTITY MISMATCH. Expected $ExpectedHostFingerprint but received $actual. Connection aborted."
    }

    Write-Host "Host fingerprint verified: $actual" -ForegroundColor Green
    & ssh.exe -i $IdentityFile -o BatchMode=yes -o IdentitiesOnly=yes `
        -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" `
        "$User@$TargetHost" 'whoami; hostname'
    if ($LASTEXITCODE -ne 0) {
        throw "SSH authentication or read-only test failed with exit code $LASTEXITCODE."
    }
} finally {
    Remove-Item -LiteralPath $knownHosts -Force -ErrorAction SilentlyContinue
}

