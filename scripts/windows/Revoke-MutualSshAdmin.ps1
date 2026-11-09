#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^ssh-ed25519\s+[A-Za-z0-9+/]+={0,3}(?:\s+[^\r\n]+)?$')]
    [string] $AuthorizedPublicKey,

    [ValidateNotNullOrEmpty()]
    [string] $FirewallRuleName = 'Dafeiyu-Mutual-SSH',

    [switch] $RemoveFirewallRule
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$authorizedKeys = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
$target = $AuthorizedPublicKey.Trim()
if (Test-Path -LiteralPath $authorizedKeys) {
    $lines = @(Get-Content -LiteralPath $authorizedKeys | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $remaining = @($lines | Where-Object { $_ -cne $target })
    if ($remaining.Count -eq $lines.Count) {
        throw 'The exact public key was not present; nothing was changed.'
    }
    if ($PSCmdlet.ShouldProcess($authorizedKeys, 'Remove exactly one peer public key')) {
        Copy-Item -LiteralPath $authorizedKeys -Destination "$authorizedKeys.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
        [System.IO.File]::WriteAllLines($authorizedKeys, $remaining, (New-Object System.Text.UTF8Encoding($false)))
        & icacls.exe $authorizedKeys /inheritance:r | Out-Null
        & icacls.exe $authorizedKeys /grant:r '*S-1-5-32-544:F' | Out-Null
        & icacls.exe $authorizedKeys /grant:r '*S-1-5-18:F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to restore the authorized_keys ACL.' }
    }
}

if ($RemoveFirewallRule) {
    $rule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
    if ($rule -and $PSCmdlet.ShouldProcess($FirewallRuleName, 'Remove peer-only SSH firewall rule')) {
        $rule | Remove-NetFirewallRule
    }
}

Restart-Service sshd
Write-Host 'Peer SSH authorization revoked. Other authorized keys were preserved.' -ForegroundColor Green

