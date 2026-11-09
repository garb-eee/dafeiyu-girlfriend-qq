#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $AuthorizedPublicKey,

    [Parameter(Mandatory = $true)]
    [ValidateScript({
        $parsed = $null
        [System.Net.IPAddress]::TryParse($_, [ref] $parsed)
    })]
    [string] $AllowedRemoteTailscaleIp,

    [ValidateNotNullOrEmpty()]
    [string] $AdminUser = $env:USERNAME,

    [ValidateNotNullOrEmpty()]
    [string] $FirewallRuleName = 'Dafeiyu-Mutual-SSH',

    [switch] $InstallOpenSshIfMissing
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Ed25519PublicKey {
    param([Parameter(Mandatory = $true)][string] $Key)

    $trimmed = $Key.Trim()
    if ($trimmed -notmatch '^ssh-ed25519\s+[A-Za-z0-9+/]+={0,3}(?:\s+[^\r\n]+)?$') {
        throw 'AuthorizedPublicKey must be one complete ssh-ed25519 public-key line.'
    }
    return $trimmed
}

function Write-Utf8NoBomLines {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][string[]] $Lines
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $Lines, $encoding)
}

$publicKey = Assert-Ed25519PublicKey -Key $AuthorizedPublicKey
$openSshCapability = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
if ($openSshCapability.State -ne 'Installed') {
    if (-not $InstallOpenSshIfMissing) {
        throw 'OpenSSH Server is not installed. Re-run with -InstallOpenSshIfMissing.'
    }
    if ($PSCmdlet.ShouldProcess('OpenSSH.Server~~~~0.0.1.0', 'Install Windows capability')) {
        Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' | Out-Null
    }
}

$localUser = Get-LocalUser -Name $AdminUser -ErrorAction Stop
$administrators = Get-LocalGroup -SID 'S-1-5-32-544'
$alreadyAdmin = Get-LocalGroupMember -Group $administrators.Name -ErrorAction Stop |
    Where-Object { $_.SID -eq $localUser.SID }
if (-not $alreadyAdmin) {
    if ($PSCmdlet.ShouldProcess($AdminUser, 'Add local user to Administrators')) {
        Add-LocalGroupMember -Group $administrators.Name -Member $localUser
    }
}

$sshRoot = Join-Path $env:ProgramData 'ssh'
$sshdConfig = Join-Path $sshRoot 'sshd_config'
$authorizedKeys = Join-Path $sshRoot 'administrators_authorized_keys'
if (-not (Test-Path -LiteralPath $sshdConfig)) {
    throw "OpenSSH configuration was not found: $sshdConfig"
}

$configText = Get-Content -LiteralPath $sshdConfig -Raw
$hasAdminMatch = $configText -match '(?im)^\s*Match\s+Group\s+administrators\s*$'
$hasAdminKeyFile = $configText -match '(?im)^\s*AuthorizedKeysFile\s+__PROGRAMDATA__/ssh/administrators_authorized_keys\s*$'
if (-not ($hasAdminMatch -and $hasAdminKeyFile)) {
    throw 'sshd_config does not contain the standard Windows administrators_authorized_keys block. No configuration was changed.'
}

$existing = @()
if (Test-Path -LiteralPath $authorizedKeys) {
    $existing = @(Get-Content -LiteralPath $authorizedKeys | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $backupPath = "$authorizedKeys.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item -LiteralPath $authorizedKeys -Destination $backupPath -Force
}
$updated = @($existing + $publicKey | Select-Object -Unique)
if ($PSCmdlet.ShouldProcess($authorizedKeys, 'Add peer public key and secure ACL')) {
    Write-Utf8NoBomLines -Path $authorizedKeys -Lines $updated
    & icacls.exe $authorizedKeys /inheritance:r | Out-Null
    & icacls.exe $authorizedKeys /grant:r '*S-1-5-32-544:F' | Out-Null
    & icacls.exe $authorizedKeys /grant:r '*S-1-5-18:F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to secure administrators_authorized_keys ACL.' }
}

$powerShell7 = Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'
$defaultShell = if (Test-Path -LiteralPath $powerShell7) {
    $powerShell7
} else {
    Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
}
if ($PSCmdlet.ShouldProcess('HKLM:\SOFTWARE\OpenSSH', "Set DefaultShell to $defaultShell")) {
    New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value $defaultShell -PropertyType String -Force | Out-Null
}

$sshdExe = Join-Path $env:SystemRoot 'System32\OpenSSH\sshd.exe'
& $sshdExe -t
if ($LASTEXITCODE -ne 0) { throw 'sshd_config validation failed; sshd was not restarted.' }

$existingRule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
if ($existingRule) {
    if ($PSCmdlet.ShouldProcess($FirewallRuleName, "Restrict SSH to $AllowedRemoteTailscaleIp")) {
        $existingRule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any
        $existingRule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $AllowedRemoteTailscaleIp
        $existingRule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 22
    }
} else {
    if ($PSCmdlet.ShouldProcess($FirewallRuleName, "Allow SSH only from $AllowedRemoteTailscaleIp")) {
        New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Action Allow -Enabled True `
            -Profile Any -Protocol TCP -LocalPort 22 -RemoteAddress $AllowedRemoteTailscaleIp | Out-Null
    }
}

Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -ne $FirewallRuleName } |
    Disable-NetFirewallRule

Set-Service -Name sshd -StartupType Automatic
Restart-Service -Name sshd

$hostPublicKey = Join-Path $sshRoot 'ssh_host_ed25519_key.pub'
if (-not (Test-Path -LiteralPath $hostPublicKey)) {
    throw "SSH is running, but the ED25519 host public key is missing: $hostPublicKey"
}

$fingerprintLine = (& ssh-keygen.exe -lf $hostPublicKey -E sha256) -join ' '
$fingerprint = if ($fingerprintLine -match '(SHA256:[A-Za-z0-9+/]+)') { $Matches[1] } else { 'UNAVAILABLE' }

[pscustomobject]@{
    ComputerName       = $env:COMPUTERNAME
    AdminUser          = $AdminUser
    AllowedRemoteIp    = $AllowedRemoteTailscaleIp
    FirewallRule       = $FirewallRuleName
    SshdStatus         = (Get-Service sshd).Status
    HostKeyFingerprint = $fingerprint
    HostPublicKey      = (Get-Content -LiteralPath $hostPublicKey -Raw).Trim()
}

