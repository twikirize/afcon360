<#
.SYNOPSIS
  One-command adb control for the Pamoja apps on a USB-attached phone.

.DESCRIPTION
  `adb` is installed on this machine but is NOT on PATH, so a bare `adb devices`
  fails with "The term 'adb' is not recognized".

  The machine can also have an emulator attached at the same time. While two
  devices are ready, every adb command fails with "more than one
  device/emulator", so this wrapper always resolves a single target and passes
  it as `adb -s <serial>`. Use -Serial when more than one is attached.

  Coordinates must come from `dump`, never from eyeballed screenshot pixels: the
  pulled PNG can be taller than the real screen because the image includes
  navigation-bar padding (a 720x1520 screenshot on a 720x1496 screen shifted
  every tap by 24px). `dump` prints the centre of each labelled node directly.

.PARAMETER Action
  devices  Show attached devices, their state and the screen size.
  size     Report the true screen size and density used by `input tap`.
  shot     Screenshot the target and pull it to disk (default: %TEMP%).
  dump     Pull the view tree and list each labelled node with its tap point.
  tap      `tap <x> <y>`
  swipe    `swipe <x1> <y1> <x2> <y2> [durationMs]`
  key      `key <keycode|name>` e.g. key 4 for Back.
  launch   Cold-launch the app; `launch 2` performs the two cold starts an OTA
           needs before the new bundle runs.

.PARAMETER Serial
  The adb serial to target, e.g. HQ61BR0F03 (phone) or emulator-5556.
  Required only when more than one device is attached.

.EXAMPLE
  .\adb-phone.ps1 devices

.EXAMPLE
  .\adb-phone.ps1 -Serial HQ61BR0F03 dump

.EXAMPLE
  .\adb-phone.ps1 tap 609 1321

.EXAMPLE
  .\adb-phone.ps1 shot -Out .\before.png
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet("devices", "size", "shot", "dump", "tap", "swipe", "key", "launch")]
  [string]$Action = "devices",

  [Parameter(Position = 1)][string]$Arg1,
  [Parameter(Position = 2)][string]$Arg2,
  [Parameter(Position = 3)][string]$Arg3,
  [Parameter(Position = 4)][string]$Arg4,

  [string]$Serial,
  [string]$Package = "space.pamoja.afcon360.user.preview",
  [string]$Out
)

$ErrorActionPreference = "Stop"

function Resolve-Adb {
  $candidates = @()
  if ($env:ANDROID_SDK_ROOT) { $candidates += (Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe") }
  if ($env:ANDROID_HOME) { $candidates += (Join-Path $env:ANDROID_HOME "platform-tools\adb.exe") }
  $candidates += (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe")
  $candidates += (Join-Path $env:USERPROFILE "AppData\Local\Android\Sdk\platform-tools\adb.exe")
  $onPath = Get-Command adb -ErrorAction SilentlyContinue
  if ($onPath) { $candidates += $onPath.Source }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
  }
  throw "adb.exe not found. Install Android platform-tools, or set ANDROID_SDK_ROOT / ANDROID_HOME."
}

$adb = Resolve-Adb
$script:target = $null

$knownStates = @("device", "offline", "unauthorized", "recovery", "sideload", "bootloader")

function Get-DeviceStates {
  $table = @(& $adb devices)
  $states = @()
  foreach ($line in $table) {
    $parts = @($line -split "\s+" | Where-Object { $_ -ne "" })
    if ($parts.Count -ge 2 -and ($knownStates -contains $parts[1])) {
      $states += [pscustomobject]@{
        Serial     = $parts[0]
        State      = $parts[1]
        IsEmulator = ($parts[0] -like "emulator-*")
      }
    }
  }
  return $states
}

function Assert-Device {
  $states = @(Get-DeviceStates)
  if ($states.Count -eq 0) {
    throw "No Android device attached. Enable USB debugging, use a data cable (not charge-only), and unlock the phone."
  }

  $ready = @($states | Where-Object { $_.State -eq "device" })
  if ($ready.Count -eq 0) {
    foreach ($entry in $states) {
      if ($entry.State -eq "unauthorized") {
        throw "Device $($entry.Serial) is unauthorized. Unlock the phone and accept the 'Allow USB debugging' prompt, then retry."
      }
    }
    foreach ($entry in $states) {
      if ($entry.State -eq "offline") {
        & $adb kill-server | Out-Null
        & $adb start-server | Out-Null
        throw "Device $($entry.Serial) was offline; the adb server has been restarted. Retry the command."
      }
    }
    throw "No device is ready. States: $(($states | ForEach-Object { "$($_.Serial)=$($_.State)" }) -join ', ')."
  }

  if ($Serial) {
    $match = @($ready | Where-Object { $_.Serial -eq $Serial })
    if ($match.Count -eq 0) {
      throw "Serial '$Serial' is not attached and ready. Ready: $(($ready | ForEach-Object { $_.Serial }) -join ', ')."
    }
    $script:target = $match[0].Serial
    return $script:target
  }

  if ($ready.Count -gt 1) {
    $phone = @($ready | Where-Object { -not $_.IsEmulator })
    $hint = if ($phone.Count -eq 1) {
      "For the attached phone: -Serial $($phone[0].Serial)"
    } else {
      "Pass -Serial <serial> to choose one."
    }
    throw "More than one device is ready ($(($ready | ForEach-Object { $_.Serial }) -join ', ')). $hint"
  }

  $script:target = $ready[0].Serial
  return $script:target
}

function Adb {
  & $adb -s $script:target @args
}

function Get-ScreenSize {
  $line = (Adb shell wm size) -join " "
  if ($line -match "(\d+)x(\d+)") { return @{ Width = [int]$matches[1]; Height = [int]$matches[2] } }
  return $null
}

switch ($Action) {
  "devices" {
    "adb: $adb"
    $states = @(Get-DeviceStates)
    if ($states.Count -eq 0) {
      "No devices attached."
      ""
      "STATE: none -- enable USB debugging, use a data cable, and unlock the phone."
      break
    }
    "Serial             Kind       State"
    "------------------------------------------"
    foreach ($entry in $states) {
      $kind = if ($entry.IsEmulator) { "emulator" } else { "phone" }
      "{0,-18} {1,-10} {2}" -f $entry.Serial, $kind, $entry.State
    }

    $ready = @($states | Where-Object { $_.State -eq "device" })
    ""
    foreach ($entry in $states) {
      if ($entry.State -eq "unauthorized") { "NOTE: $($entry.Serial) is unauthorized -- accept the 'Allow USB debugging' prompt on the phone." }
      if ($entry.State -eq "offline") { "NOTE: $($entry.Serial) is offline -- run 'adb kill-server' then 'adb start-server'." }
    }
    if ($ready.Count -gt 1) {
      "NOTE: $($ready.Count) devices are ready, so plain adb commands fail with 'more than one device/emulator'. Pass -Serial."
    }
    if ($ready.Count -ge 1) {
      $script:target = if ($Serial) { $Serial } else { $ready[0].Serial }
      "target: $script:target"
      "model:  $((Adb shell getprop ro.product.model) -join '')"
      "android:$((Adb shell getprop ro.build.version.release) -join '')"
      "screen: $((Adb shell wm size) -join '')"
      "density:$((Adb shell wm density) -join '')"
    }
  }

  "size" {
    Assert-Device | Out-Null
    Adb shell wm size
    Adb shell wm density
  }

  "shot" {
    Assert-Device | Out-Null
    $destination = if ($Out) { $Out } else { Join-Path $env:TEMP ("pamoja-shot-{0:yyyyMMdd-HHmmss}.png" -f (Get-Date)) }
    Adb shell screencap -p /sdcard/pamoja-shot.png
    Adb pull /sdcard/pamoja-shot.png $destination
    Adb shell rm -f /sdcard/pamoja-shot.png | Out-Null
    "Saved: $destination"
  }

  "dump" {
    Assert-Device | Out-Null
    $destination = if ($Out) { $Out } else { Join-Path $env:TEMP "pamoja-ui.xml" }
    Adb shell uiautomator dump /sdcard/pamoja-ui.xml | Out-Null
    Adb pull /sdcard/pamoja-ui.xml $destination | Out-Null
    Adb shell rm -f /sdcard/pamoja-ui.xml | Out-Null

    $screen = Get-ScreenSize
    if ($screen) { "Screen (from wm size): $($screen.Width)x$($screen.Height) -- tap coordinates must come from here"; "" }

    $document = [xml](Get-Content -LiteralPath $destination -Raw)
    "{0,-42} {1,-10} {2}" -f "LABEL", "TAP", "FLAGS"
    "-------------------------------------------------------------------------"
    foreach ($node in $document.SelectNodes("//node")) {
      $label = if ($node.'content-desc') { $node.'content-desc' } elseif ($node.text) { $node.text } else { "" }
      $label = ($label -replace "\s+", " ").Trim()
      if (-not $label) { continue }
      if ($node.bounds -notmatch "\[(\d+),(\d+)\]\[(\d+),(\d+)\]") { continue }
      $x1 = [int]$matches[1]; $y1 = [int]$matches[2]; $x2 = [int]$matches[3]; $y2 = [int]$matches[4]
      $centreX = [int](($x1 + $x2) / 2)
      $centreY = [int](($y1 + $y2) / 2)

      $flags = @()
      if ($node.clickable -eq "true") { $flags += "clickable" }
      if ($node.selected -eq "true") { $flags += "selected" }
      if ($node.enabled -eq "false") { $flags += "disabled" }
      if ($node.class -eq "android.widget.EditText") { $flags += "input" }

      if ($label.Length -gt 41) { $label = $label.Substring(0, 38) + "..." }
      "{0,-42} {1,-10} {2}" -f $label, "$centreX,$centreY", ($flags -join " ")
    }
    ""
    "Full tree: $destination"
  }

  "tap" {
    Assert-Device | Out-Null
    if (-not $Arg1 -or -not $Arg2) { throw "Usage: adb-phone.ps1 tap <x> <y>" }
    $screen = Get-ScreenSize
    if ($screen) {
      $x = [int]$Arg1; $y = [int]$Arg2
      if ($x -lt 0 -or $x -gt $screen.Width -or $y -lt 0 -or $y -gt $screen.Height) {
        throw "Tap $x,$y is outside the real screen ($($screen.Width)x$($screen.Height)). Screenshot coordinates can be shifted by navigation-bar padding -- use 'dump'."
      }
    }
    Adb shell input tap ([int]$Arg1) ([int]$Arg2)
    "Tapped $Arg1,$Arg2 on $script:target"
  }

  "swipe" {
    Assert-Device | Out-Null
    if (-not $Arg1 -or -not $Arg4) { throw "Usage: adb-phone.ps1 swipe <x1> <y1> <x2> <y2> [durationMs]" }
    $duration = 300
    if ($Arg4) { $duration = [int]$Arg4 }
    Adb shell input swipe ([int]$Arg1) ([int]$Arg2) ([int]$Arg3) ([int]$Arg4) $duration
    "Swiped $Arg1,$Arg2 to $Arg3,$Arg4 over ${duration}ms on $script:target"
  }

  "key" {
    Assert-Device | Out-Null
    if (-not $Arg1) { throw "Usage: adb-phone.ps1 key <keycode|name>  (4 = Back, 3 = Home, 82 = Unlock)" }
    Adb shell input keyevent $Arg1
    "Sent keyevent $Arg1 to $script:target"
  }

  "launch" {
    Assert-Device | Out-Null
    $times = 1
    if ($Arg1) { $times = [int]$Arg1 }
    if ($times -lt 1) { $times = 1 }

    # adb writes progress and warnings to stderr, and $ErrorActionPreference = "Stop"
    # turns any of that into a terminating error even when the command succeeded.
    # Relax it here and judge each step by its exit code instead.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    $component = $null
    foreach ($line in (& $adb -s $script:target shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER $Package 2>&1)) {
      if ("$line" -match "\S+/\S+") { $component = "$line".Trim() }
    }
    if (-not $component) {
      $ErrorActionPreference = $previous
      throw "Could not resolve a launcher activity for $Package on $script:target."
    }

    for ($run = 1; $run -le $times; $run++) {
      & $adb -s $script:target shell am force-stop $Package 2>&1 | Out-Null
      Start-Sleep -Milliseconds 800
      # -W waits for the process, which is what makes this a cold start rather
      # than a request the shell forgets about.
      $startOutput = & $adb -s $script:target shell am start -W -n $component 2>&1
      $code = $LASTEXITCODE
      if ($code -ne 0) {
        $ErrorActionPreference = $previous
        throw "am start failed (exit $code) for $component on $script:target."
      }
      $status = ($startOutput | Select-String -Pattern "Status:" | Select-Object -First 1)
      $label = "Cold start ${run} of ${times}: $component on $script:target"
      if ($status) { $label = $label + " (" + $status.ToString().Trim() + ")" }
      $label
      if ($run -lt $times) { Start-Sleep -Seconds 20 }
    }

    foreach ($line in (& $adb -s $script:target shell dumpsys window 2>&1)) {
      if ("$line" -match "mCurrentFocus") {
        "In front: " + ("$line".Trim() -replace "\s+", " ")
        break
      }
    }
    $ErrorActionPreference = $previous

    if ($times -gt 1) {
      "Note: the first launch downloads the update, the second applies it. Let both settle before asserting anything on screen."
    }
  }
}