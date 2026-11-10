param(
    [string] $ContainerName = 'dfyqq-astrbot'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$lockPath = Join-Path $repoRoot 'plugins.lock.json'
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$tempBase = [IO.Path]::GetTempPath()
$tempRoot = Join-Path $tempBase ("dfyqq-plugins-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot | Out-Null

function Copy-PluginToContainer {
    param(
        [Parameter(Mandatory = $true)][string] $Source,
        [Parameter(Mandatory = $true)][string] $Name
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Plugin source is missing: $Source"
    }
    docker exec $ContainerName sh -lc "mkdir -p /AstrBot/data/plugins/$Name"
    if ($LASTEXITCODE -ne 0) { throw "Could not create plugin directory: $Name" }
    docker cp "$Source/." "${ContainerName}:/AstrBot/data/plugins/$Name"
    if ($LASTEXITCODE -ne 0) { throw "Could not copy plugin: $Name" }
    if ($Name -eq 'astrbot_plugin_group_chat_plus') {
        docker exec $ContainerName sh -lc `
            "test -f /AstrBot/data/plugins/$Name/private_chat/private_chat_utils/_session_guard.py || cp /AstrBot/data/plugins/$Name/utils/_session_guard.py /AstrBot/data/plugins/$Name/private_chat/private_chat_utils/_session_guard.py"
        if ($LASTEXITCODE -ne 0) { throw 'Could not apply Group Chat Plus compatibility shim.' }
    }
}

try {
    $groups = $lock.plugins | Where-Object repository -ne 'local' | Group-Object repository
    foreach ($group in $groups) {
        $repoDir = Join-Path $tempRoot ("repo-" + [guid]::NewGuid().ToString('N'))
        git clone --quiet $group.Name $repoDir
        if ($LASTEXITCODE -ne 0) { throw "Could not clone $($group.Name)" }
        foreach ($plugin in $group.Group) {
            git -C $repoDir checkout --quiet --detach $plugin.commit
            if ($LASTEXITCODE -ne 0) { throw "Could not check out $($plugin.name)" }
            $source = if ($plugin.subdirectory) {
                Join-Path $repoDir $plugin.subdirectory
            } else {
                $repoDir
            }
            Copy-PluginToContainer -Source $source -Name $plugin.name
        }
    }

    foreach ($plugin in ($lock.plugins | Where-Object repository -eq 'local')) {
        Copy-PluginToContainer `
            -Source (Join-Path $repoRoot $plugin.subdirectory) `
            -Name $plugin.name
    }
} finally {
    $resolvedTemp = [IO.Path]::GetFullPath($tempRoot)
    $resolvedBase = [IO.Path]::GetFullPath($tempBase)
    if ($resolvedTemp.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemp).StartsWith('dfyqq-plugins-')) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "Installed $($lock.plugins.Count) pinned plugins into $ContainerName."
