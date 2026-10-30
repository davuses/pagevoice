param([Parameter(Mandatory = $true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path $Installer).Path
$installDir = Join-Path $env:RUNNER_TEMP 'PageVoice installer test'
$programs = [Environment]::GetFolderPath('Programs')
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$startLink = Join-Path $programs 'PageVoice Server.lnk'
$desktopLink = Join-Path $desktop 'PageVoice Server.lnk'
$shell = New-Object -ComObject WScript.Shell

function Install-TestBuild([string]$LogName) {
    $log = Join-Path $env:RUNNER_TEMP $LogName
    $process = Start-Process $Installer -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS',
        '/TASKS=desktopicon', '/GROUP="Old Kokoro Group"',
        "/DIR=`"$installDir`"", "/LOG=`"$log`""
    ) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode); $log" }
}

function Assert-LaunchShortcut([string]$Path) {
    if (-not (Test-Path $Path)) { throw "Missing shortcut: $Path" }
    $shortcut = $shell.CreateShortcut($Path)
    if (-not (Test-Path $shortcut.TargetPath)) { throw "Missing shortcut target: $($shortcut.TargetPath)" }
    if ($shortcut.TargetPath -ne "$installDir\PageVoice.exe") { throw 'Wrong launcher' }
    if ($shortcut.WorkingDirectory -ne $installDir) { throw 'Wrong working directory' }
    if ($shortcut.Arguments) { throw 'Unexpected shortcut arguments' }
    if ($shortcut.IconLocation -notlike "$installDir\pagevoice.ico*") { throw 'Wrong icon location' }
    if (-not (Test-Path "$installDir\pagevoice.ico")) { throw 'Icon was not installed' }
    $explorer = New-Object -ComObject Shell.Application
    $item = $explorer.Namespace((Split-Path $Path)).ParseName([IO.Path]::GetFileName($Path))
    if ($item.ExtendedProperty('System.AppUserModel.ID') -ne 'davuses.PageVoice.Server') {
        throw 'Missing PageVoice application identity on shortcut'
    }
    Write-Host "PASS shortcut target, arguments, working directory and icon: $Path"
}

try {
    Install-TestBuild 'pagevoice-install.log'
    Assert-LaunchShortcut $startLink
    Assert-LaunchShortcut $desktopLink

    # Exercise the real Windows launcher with a harmless script instead of
    # downloading models/dependencies in an installer test.
    $marker = Join-Path $installDir 'launcher-started'
    Set-Content "$installDir\start-tray.vbs" @(
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        ('Set output = fso.CreateTextFile("' + $marker + '", True)'),
        'output.Close'
    )
    Start-Process "$installDir\PageVoice.exe" -Wait
    for ($attempt = 0; $attempt -lt 100 -and -not (Test-Path $marker); $attempt++) {
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path $marker)) { throw 'PageVoice.exe did not execute its launcher script' }
    Write-Host 'PASS native launcher executes its script from a path with spaces'

    # Simulate a user missing the Start shortcut, with an older branded link
    # and an existing dependency environment/GPU preference. An in-place
    # reinstall must repair discovery without deleting that environment.
    New-Item -ItemType Directory -Force "$installDir\.venv" | Out-Null
    Set-Content "$installDir\.venv\upgrade-sentinel" 'keep environment'
    Set-Content "$installDir\gpu.flag" 'keep GPU preference'
    $legacy = Join-Path $programs 'Kokoro TTS Server\Kokoro TTS Server.lnk'
    New-Item -ItemType Directory -Force (Split-Path $legacy) | Out-Null
    Copy-Item $startLink $legacy
    Remove-Item $startLink
    Install-TestBuild 'pagevoice-upgrade.log'
    Assert-LaunchShortcut $startLink
    Assert-LaunchShortcut $desktopLink
    if (Test-Path $legacy) { throw 'Legacy shortcut was not removed' }
    if (-not (Test-Path "$installDir\.venv\upgrade-sentinel")) { throw 'Upgrade deleted environment' }
    if (-not (Test-Path "$installDir\gpu.flag")) { throw 'Upgrade deleted GPU preference' }
    Write-Host 'PASS in-place upgrade repairs Start shortcut and preserves environment/GPU preference'
} finally {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (Test-Path $uninstaller) {
        $process = Start-Process $uninstaller -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Uninstall failed: $($process.ExitCode)" }
        if (Test-Path $startLink) { throw 'Uninstall left the Start shortcut' }
        if (Test-Path $desktopLink) { throw 'Uninstall left the desktop shortcut' }
        Write-Host 'PASS uninstall removes shortcuts'
    }
}
