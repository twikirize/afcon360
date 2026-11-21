$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.PrefixOrigin -in @('Dhcp', 'Manual') -and
    $_.IPAddress -notlike '127.*' -and
    $_.IPAddress -notlike '169.254.*' -and
    $_.InterfaceAlias -notlike '*Loopback*' -and
    $_.InterfaceAlias -notlike '*VPN*' -and
    $_.InterfaceAlias -notlike '*Tunnel*' -and
    $_.InterfaceAlias -notlike '*Pseudo*'
} | Select-Object -ExpandProperty IPAddress

Write-Host "All IPs count: $($ips.Count)"
Write-Host "All IPs type: $($ips.GetType().Name)"
Write-Host "All IPs: $ips"

$preferred = $ips | Where-Object { $_ -like '192.168.*' -or $_ -like '10.*' -or $_ -like '172.1[6-9].*' -or $_ -like '172.2[0-9].*' -or $_ -like '172.3[0-1].*' }
Write-Host "Preferred count: $($preferred.Count)"
Write-Host "Preferred: $preferred"

if ($preferred.Count -gt 0) { $preferred[0] } else { $ips[0] }