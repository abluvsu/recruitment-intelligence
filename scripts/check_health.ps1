<#
.SYNOPSIS
    Daily Pre-flight & Resource Optimization Check for Antigravity & MyOperator.
    Completely non-blocking, headless, and safe for automated/scheduled execution.
#>

$ErrorActionPreference = "SilentlyContinue"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logDir = "D:\myoperator\outputs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir "daily_health.log"

function Log-Msg($msg) {
    if ($Host.UI.RawUI) {
        Write-Host $msg
    }
    Add-Content -Path $logFile -Value $msg
}

Add-Content -Path $logFile -Value "`n============================================================"
Add-Content -Path $logFile -Value "HEALTH CHECK: $timestamp"
Add-Content -Path $logFile -Value "============================================================"

# 1. Virtual Memory & Commit Headroom
$os = Get-CimInstance Win32_OperatingSystem
$totalRam = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeRam = [math]::Round($os.FreePhysicalMemory / 1MB, 2)

$commitLimit = (Get-Counter "\Memory\Commit Limit" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
$commitUsed  = (Get-Counter "\Memory\Committed Bytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue

$limitGB = [math]::Round($commitLimit / 1GB, 2)
$usedGB  = [math]::Round($commitUsed / 1GB, 2)
$freeCommitGB = [math]::Round(($commitLimit - $commitUsed) / 1GB, 2)

Log-Msg "[1] MEMORY STATUS"
Log-Msg "  Physical RAM : $freeRam GB free / $totalRam GB total"
Log-Msg "  Commit Limit : $usedGB GB used / $limitGB GB total ($freeCommitGB GB headroom)"

if ($limitGB -le ($totalRam + 1)) {
    Log-Msg "  [CRITICAL] Pagefile appears DISABLED! Hard limit is at physical RAM."
} elseif ($freeCommitGB -lt 1.5) {
    Log-Msg "  [WARNING] Commit headroom is low (< 1.5 GB)."
} else {
    Log-Msg "  [OK] Healthy commit memory headroom."
}

# 2. Chrome Memory Footprint
$chromeProcs = Get-Process chrome -ErrorAction SilentlyContinue
if ($chromeProcs) {
    $chromeMb = [math]::Round(($chromeProcs | Measure-Object WorkingSet64 -Sum).Sum / 1MB, 1)
    Log-Msg "`n[2] CHROME FOOTPRINT"
    Log-Msg "  Chrome is using $chromeMb MB across $($chromeProcs.Count) processes."
    if ($chromeMb -gt 2200) {
        Log-Msg "  High Chrome memory usage detected (> 2.2 GB)."
    } else {
        Log-Msg "  [OK] Chrome footprint is acceptable."
    }
}

# 3. Clean stale temp/pytest cache
if (Test-Path "D:\myoperator") {
    $cacheItems = Get-ChildItem "D:\myoperator" -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\(__pycache__|\.pytest_cache|tmp-test|\.tmp)$" }
    
    if ($cacheItems.Count -gt 0) {
        Log-Msg "`n[3] CLEANING CACHE"
        Log-Msg "  Cleaning $($cacheItems.Count) temporary build/test cache folders..."
        foreach ($item in $cacheItems) {
            Remove-Item -Path $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        Log-Msg "  [OK] Cleaned workspace caches."
    } else {
        Log-Msg "`n[3] WORKSPACE HYGIENE"
        Log-Msg "  [OK] Workspace cache folders are clean."
    }
}

Log-Msg "CHECK FINISHED`n"
