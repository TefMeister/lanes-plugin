# runner.ps1 - the part of Lanes' "quiet installs" that runs with administrator rights (0.110.0, 2026-11-11).
#
# A Windows task ("Lanes quiet install", made once by setup.ps1 with one Yes click) runs the COPY of this file that
# sits in a folder only administrators can change. tools/quiet_install.py puts a small request file into queue\ and
# starts the task; this file reads the requests, installs or updates the named programs with the Windows package
# installer (winget) and writes one answer per request into results\.
#
# WHAT IT WILL DO, AND NOTHING ELSE
#   One kind of order: "install" or "upgrade" one package id from the official winget catalogue, optionally at one
#   version. The id and the version may only hold letters, digits and . + _ - ; the command line is built HERE, never
#   taken from the request. No other program, script, path or switch can be handed in. winget itself is taken from its
#   own protected install folder, not from the search path.
# The two Test* parameters exist for the test suite and are refused when this runs with administrator rights.
param([string]$TestRoot = "", [string]$TestWinget = "")

$ErrorActionPreference = "Stop"
$MaxRequestBytes = 65536
$MaxItems = 40
$PerPackageMinutes = 30
$KeepResultsDays = 7
$TailChars = 600            # how much of the installer's last words goes into the answer
$MsPerMinute = 60000
$MaxRounds = 50             # how often the queue is looked at again in one run (orders that arrived meanwhile)
$IdPattern = '^[A-Za-z0-9][A-Za-z0-9.+_-]{1,99}$'
$VersionPattern = '^[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}$'
$NamePattern = '^[a-f0-9]{32}\.json$'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$elevated = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($elevated -and ($TestRoot -or $TestWinget)) { exit 3 }

$Root = $PSScriptRoot
if ($TestRoot) { $Root = $TestRoot }
$Queue = Join-Path $Root "queue"
$Results = Join-Path $Root "results"
$Log = Join-Path $Root "runner.log"

function Write-Log([string]$text) {
    try { Add-Content -LiteralPath $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text) -Encoding UTF8 } catch { }
}

function Find-Winget {
    if ($TestWinget) { return $TestWinget }
    try {
        $pkg = Get-AppxPackage -Name Microsoft.DesktopAppInstaller | Sort-Object Version -Descending | Select-Object -First 1
        if ($pkg -and (Test-Path -LiteralPath (Join-Path $pkg.InstallLocation "winget.exe"))) {
            return (Join-Path $pkg.InstallLocation "winget.exe")
        }
    } catch { }
    $found = Get-ChildItem -Path (Join-Path $env:ProgramFiles "WindowsApps") -Filter "Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if ($found -and (Test-Path -LiteralPath (Join-Path $found.FullName "winget.exe"))) {
        return (Join-Path $found.FullName "winget.exe")
    }
    return ""
}

function Invoke-One($winget, $item) {
    $answer = @{ package = [string]$item.package; action = [string]$item.action; status = "refused"; exit = $null; tail = "" }
    if (@("install", "upgrade") -notcontains $answer.action) { $answer.tail = "only install and upgrade are done"; return $answer }
    if ($answer.package -notmatch $IdPattern) { $answer.tail = "not a package id"; return $answer }
    $version = [string]$item.version
    if ($version -and ($version -notmatch $VersionPattern)) { $answer.tail = "not a version"; return $answer }
    $list = @($answer.action, "--id", $answer.package, "--exact", "--source", "winget", "--silent",
              "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity")
    if ($version) { $list += @("--version", $version) }
    if ($item.force -eq $true -and $answer.action -eq "install") { $list += "--force" }
    $out = [IO.Path]::GetTempFileName()
    $err = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $winget -ArgumentList $list -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $null = $p.Handle                       # keeps the exit code readable after the wait (Windows PowerShell 5.1)
        if (-not $p.WaitForExit($PerPackageMinutes * $MsPerMinute)) {
            & (Join-Path $env:SystemRoot "System32\taskkill.exe") /T /F /PID $p.Id 2>$null | Out-Null
            $answer.status = "timeout"
            $answer.tail = "stopped after $PerPackageMinutes minutes"
            return $answer
        }
        $p.WaitForExit()
        $answer.exit = $p.ExitCode
        $text = @(Get-Content -LiteralPath $out -Encoding UTF8 -ErrorAction SilentlyContinue) + @(Get-Content -LiteralPath $err -Encoding UTF8 -ErrorAction SilentlyContinue)
        $lines = @($text | Where-Object { $_ -and ($_ -match '[A-Za-z0-9]{3}') -and ($_ -notmatch '[^\x00-\x7F]{3}') })
        $answer.tail = (($lines | Select-Object -Last 4) -join " | ")
        if ($answer.tail.Length -gt $TailChars) { $answer.tail = $answer.tail.Substring($answer.tail.Length - $TailChars) }
        $answer.status = "ran"
    } catch {
        $answer.status = "error"
        $answer.tail = "$_"
    } finally {
        Remove-Item -LiteralPath $out, $err -Force -ErrorAction SilentlyContinue
    }
    return $answer
}

if (-not (Test-Path -LiteralPath $Queue) -or -not (Test-Path -LiteralPath $Results)) { exit 2 }
$winget = Find-Winget
$wingetVersion = ""
if ($winget) { try { $wingetVersion = (& $winget --version 2>$null | Select-Object -First 1) } catch { } }

for ($round = 0; $round -lt $MaxRounds; $round++) {
    $files = @(Get-ChildItem -LiteralPath $Queue -File -Filter "*.json" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $NamePattern -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
        Sort-Object LastWriteTimeUtc)
    if ($files.Count -eq 0) { break }
    foreach ($f in $files) {
        $result = @{ id = $f.BaseName; elevated = $elevated; winget = [string]$wingetVersion; items = @(); error = "" }
        try {
            if ($f.Length -gt $MaxRequestBytes) { throw "the request is too large" }
            $req = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $items = @($req.items)
            if ($items.Count -gt $MaxItems) { throw "more than $MaxItems packages in one request" }
            if ($items.Count -gt 0 -and -not $winget) { throw "winget was not found in its install folder" }
            foreach ($item in $items) {
                $one = Invoke-One $winget $item
                Write-Log ("{0} {1} -> {2} {3}" -f $one.action, $one.package, $one.status, $one.exit)
                $result.items += $one
            }
        } catch {
            $result.error = "$_"
            Write-Log ("request {0}: {1}" -f $f.BaseName, $_)
        }
        $result.done = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        $target = Join-Path $Results $f.Name
        $tmp = "$target.tmp"
        [IO.File]::WriteAllText($tmp, ($result | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $tmp -Destination $target -Force
        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
    }
}

Get-ChildItem -LiteralPath $Results -File -Filter "*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepResultsDays) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
exit 0
