param([Parameter(Mandatory=$true)][string]$ProgramPath, [ValidateRange(1,65535)][int]$Port = 8769, [switch]$Elevated)
$ErrorActionPreference = 'Stop'
$program = (Resolve-Path -LiteralPath $ProgramPath).Path
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($Elevated) { throw 'Administrator permission was not granted.' }
    # Single-quoted values are escaped for the child PowerShell invocation.
    $scriptQuoted = "'" + $PSCommandPath.Replace("'", "''") + "'"
    $programQuoted = "'" + $program.Replace("'", "''") + "'"
    $command = "& $scriptQuoted -ProgramPath $programQuoted -Port $Port -Elevated"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList @('-NoProfile','-EncodedCommand',$encoded) -Wait
    exit
}
$rule = "AirBridgeScreenshot-Community-$Port"
if (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue) {
    Remove-NetFirewallRule -Name $rule
}
New-NetFirewallRule -Name $rule -DisplayName 'AirBridge Screenshot — local network' -Direction Inbound -Action Allow -Profile Private -RemoteAddress LocalSubnet -Protocol TCP -LocalPort $Port -Program $program | Out-Null
$discoveryRule = "AirBridgeScreenshot-Community-mDNS-$Port"
if (Get-NetFirewallRule -Name $discoveryRule -ErrorAction SilentlyContinue) {
    Remove-NetFirewallRule -Name $discoveryRule
}
New-NetFirewallRule -Name $discoveryRule -DisplayName 'AirBridge Screenshot — local discovery' -Direction Inbound -Action Allow -Profile Private -RemoteAddress LocalSubnet -Protocol UDP -LocalPort 5353 -Program $program | Out-Null
