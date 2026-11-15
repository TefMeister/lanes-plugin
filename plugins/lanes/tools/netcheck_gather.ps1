# netcheck_gather.ps1 - reads this PC's network-safety settings and prints them as one JSON object (0.116.0).
# Run by netcheck.py. It READS ONLY: no setting is changed, no program is stopped, nothing is sent anywhere.
# No administrator rights needed; a value it cannot read is left out (null), never guessed.
$ErrorActionPreference = 'SilentlyContinue'
$o = [ordered]@{}
$procs = @{}
foreach ($p in Get-Process) { $procs[[int]$p.Id] = $p.ProcessName }
$o.processes = @($procs.Values | Sort-Object -Unique)

$o.firewall = @(Get-NetFirewallProfile | ForEach-Object {
    [ordered]@{ name = [string]$_.Name; on = ([string]$_.Enabled -eq 'True') } })

$m = Get-MpComputerStatus
if ($m) {
    $o.defender = [ordered]@{ realtime = [bool]$m.RealTimeProtectionEnabled; antivirus = [bool]$m.AntivirusEnabled;
        age_days = [int]$m.AntivirusSignatureAge; mode = [string]$m.AMRunningMode }
}
$o.antivirus = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | ForEach-Object {
    $s = [int]$_.productState
    [ordered]@{ name = [string]$_.displayName; on = (($s -band 0x1000) -ne 0); out_of_date = (($s -band 0x10) -ne 0) } })

$o.networks = @(Get-NetConnectionProfile | ForEach-Object {
    [ordered]@{ category = [string]$_.NetworkCategory; adapter = [string]$_.InterfaceAlias } })

$o.listening = @(Get-NetTCPConnection -State Listen | Where-Object {
        $_.LocalAddress -ne '127.0.0.1' -and $_.LocalAddress -ne '::1' } | ForEach-Object {
    [ordered]@{ port = [int]$_.LocalPort; all = ($_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::');
        program = [string]$procs[[int]$_.OwningProcess] } })

$private = '^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.|::1$|fe80:|fd)'
$o.talking_out = @(Get-NetTCPConnection -State Established | Where-Object { $_.RemoteAddress -notmatch $private } |
    ForEach-Object { [string]$procs[[int]$_.OwningProcess] } | Group-Object | ForEach-Object {
        [ordered]@{ program = $_.Name; connections = $_.Count } })

# The firewall's rules are read from the registry: Get-NetFirewallRule answers "Access is denied" without
# administrator rights on some PCs (seen on the Keeper PC, 2026-11-15). Inbound "allow" rules that are switched on.
$o.inbound_rules = @()
$fw = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules'
if ($fw) {
    foreach ($prop in $fw.PSObject.Properties) {
        if ($prop.Name -like 'PS*') { continue }
        $v = [string]$prop.Value
        if ($v -notmatch '\|Action=Allow\|' -or $v -notmatch '\|Active=TRUE\|' -or $v -notmatch '\|Dir=In\|') { continue }
        $name = if ($v -match '\|Name=([^|]*)\|') { $Matches[1] } else { '' }
        $app = if ($v -match '\|App=([^|]*)\|') { Split-Path -Leaf $Matches[1] } else { '' }
        $prof = if ($v -match '\|Profile=([^|]*)\|') { $Matches[1] } else { 'Any' }
        if ($name.StartsWith('@')) { $name = '' }
        $o.inbound_rules += [ordered]@{ id = [string]$prop.Name; name = $name; program = $app; profile = $prof }
    }
}

$ts = Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server'
if ($ts) { $o.remote_desktop = ($ts.fDenyTSConnections -eq 0) }
$ra = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance'
if ($ra) { $o.remote_assistance = ($ra.fAllowToGetHelp -eq 1) }
$o.smb1 = [bool](Get-Service -Name mrxsmb10)

$o.startup = @()
foreach ($key in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
                 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run') {
    $props = Get-ItemProperty $key
    if ($props) {
        foreach ($n in $props.PSObject.Properties.Name) {
            if ($n -notlike 'PS*') { $o.startup += [string]$n }
        }
    }
}
foreach ($dir in ([Environment]::GetFolderPath('Startup')), ([Environment]::GetFolderPath('CommonStartup'))) {
    if ($dir -and (Test-Path $dir)) { Get-ChildItem $dir -File | ForEach-Object { $o.startup += [string]$_.Name } }
}

$hf = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
if ($hf) { $o.last_update = $hf.InstalledOn.ToString('yyyy-MM-dd') }

$o.dns = @(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | ForEach-Object {
    [string]($_.ServerAddresses -join ',') } | Sort-Object -Unique)

$hosts = Join-Path $env:WINDIR 'System32\drivers\etc\hosts'
$o.hosts = @(Get-Content $hosts | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | ForEach-Object { $_.Trim() })

$o | ConvertTo-Json -Depth 5 -Compress
