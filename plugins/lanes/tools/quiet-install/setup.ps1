# setup.ps1 - makes (or removes) the Windows task behind Lanes' "quiet installs". Runs ONCE, with administrator
# rights: tools/quiet_install.py starts it, and that start is the one Yes click (0.110.0, 2026-11-11).
#
# It makes a folder only administrators can change, copies runner.ps1 into it, and registers the task
# "Lanes quiet install": run by hand only (no schedule), as the person who is logged on, with the highest rights.
# Afterwards that person's own programs can START the task without a Yes click, but cannot change what it runs.
param(
    [Parameter(Mandatory = $true)][string]$Root,       # the protected folder (under ProgramData)
    [string]$Source = "",                               # the plugin's runner.ps1 to copy in
    [string]$User = "",                                 # who may start the task: the person logged on
    [string]$Report = "",                               # where to write what happened (the person's own Lanes folder)
    [string]$TaskName = "Lanes quiet install",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ADMINS = "*S-1-5-32-544"
$SYSTEM = "*S-1-5-18"
$USERS = "*S-1-5-32-545"
$icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
$result = @{ ok = $false; error = ""; root = $Root; task = $TaskName }

function Save-Report {
    if ($Report) {
        try { [IO.File]::WriteAllText($Report, ($result | ConvertTo-Json), (New-Object Text.UTF8Encoding($false))) } catch { }
    }
}

try {
    $me = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "this needs administrator rights (the Yes click)" }
    $programData = [IO.Path]::GetFullPath($env:ProgramData).TrimEnd("\")
    $full = [IO.Path]::GetFullPath($Root).TrimEnd("\")
    if (-not $full.StartsWith($programData + "\", [StringComparison]::OrdinalIgnoreCase) -or $full.Length -lt ($programData.Length + 5)) {
        throw "the folder must be inside ProgramData"
    }

    if ($Remove) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
        $result.ok = $true
        Save-Report
        exit 0
    }

    if (-not $User) { throw "no user named" }
    if (-not (Test-Path -LiteralPath $Source)) { throw "the runner to copy was not found" }

    # The folder: made fresh, owned by the administrators, nothing inherited. Anything already there is not ours.
    if (Test-Path -LiteralPath $full) {
        & $icacls $full /setowner $ADMINS /T /C /Q | Out-Null
        & $icacls $full /reset /T /C /Q | Out-Null
        Remove-Item -LiteralPath $full -Recurse -Force
    }
    New-Item -ItemType Directory -Path $full | Out-Null
    & $icacls $full /setowner $ADMINS /Q | Out-Null
    & $icacls $full /inheritance:r /grant:r "${ADMINS}:(OI)(CI)F" "${SYSTEM}:(OI)(CI)F" "${USERS}:(OI)(CI)RX" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not set the folder's rights" }
    New-Item -ItemType Directory -Path (Join-Path $full "queue") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $full "results") | Out-Null
    # queue\: the person's programs may put request files in and take them out; they may not replace the folder itself
    & $icacls (Join-Path $full "queue") /grant "${USERS}:(RX,WD,AD)" "${USERS}:(OI)(CI)(IO)M" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not set the queue's rights" }

    $runner = Join-Path $full "runner.ps1"
    Copy-Item -LiteralPath $Source -Destination $runner -Force
    $hash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash.ToLower()

    $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $action = New-ScheduledTaskAction -Execute $powershell -Argument ("-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`"" -f $runner)
    $principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 8)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal -Settings $settings -Force `
        -Description "Lanes: installs and updates programs from the Windows package catalogue without a Yes click. It can do nothing else. Made by tools/quiet_install.py setup; remove with quiet_install.py uninstall." | Out-Null

    $info = @{ sha256 = $hash; when = (Get-Date -Format "yyyy-MM-dd HH:mm:ss"); task = $TaskName }
    [IO.File]::WriteAllText((Join-Path $full "installed.json"), ($info | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    $result.ok = $true
    $result.sha256 = $hash
} catch {
    $result.error = "$_"
}
Save-Report
if ($result.ok) { exit 0 } else { exit 1 }
