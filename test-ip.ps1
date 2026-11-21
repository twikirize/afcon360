function Get-LocalLanIP {
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.PrefixOrigin -in @('Dhcp', 'Manual') -and
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.InterfaceAlias -notlike '*Loopback*' -and
        $_.InterfaceAlias -notlike '*VPN*' -and
        $_.InterfaceAlias -notlike '*Tunnel*' -and
        $_.InterfaceAlias -notlike '*Pseudo*'
    } | Select-Object -ExpandProperty IPAddress)

    Write-Host "DEBUG: ips count = $($ips.Count)"
    Write-Host "DEBUG: ips type = $($ips.GetType().Name)"
    Write-Host "DEBUG: ips = $ips"

    if ($ips.Count -eq 0) {
        Write-Error "No LAN IP found"
        exit 1
    }

    $preferred = $ips | Where-Object { $_ -like '192.168.*' -or $_ -like '10.*' -or $_ -like '172.1[6-9].*' -or $_ -like '172.2[0-9].*' -or $_ -like '172.3[0-1].*' }
    Write-Host "DEBUG: preferred count = $($preferred.Count)"
    Write-Host "DEBUG: preferred = $preferred"

    if ($preferred.Count -gt 0) {
        return $preferred[0]
    }
    return $ips[0]
}

$result = Get-LocalLanIP
Write-Host "RESULT: $result"