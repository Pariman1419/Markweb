# preflight_17.ps1 — Preflight verification for deploying Mark Automation on 10.153.90.17
# Built-in PowerShell 5.1 cmdlets only. Never prints secrets from .env.
[CmdletBinding()]
param(
    [string[]]$Ports = @("8090..8099"),
    [string]$EnvFile = ".\.env",
    [switch]$WritePort
)

$hasError = $false

Write-Host "=== Preflight Verification for Mark Automation Deployment ===" -ForegroundColor Cyan
Write-Host "Timestamp : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Env file  : $EnvFile"
Write-Host ""

# -----------------------------------------------------------------------------
# 1. Checkout Checks
# -----------------------------------------------------------------------------
Write-Host "--- 1. Checkout ---" -ForegroundColor Yellow

# Tracked changes check (ignoring untracked files)
$gitTracked = git status --porcelain -uno
if ($gitTracked) {
    Write-Host "[FAIL] Checkout: working tree not clean (uncommitted tracked changes present)" -ForegroundColor Red
    $hasError = $true
} else {
    Write-Host "[PASS] Checkout: working tree clean (no uncommitted tracked changes)" -ForegroundColor Green
}

# Sync with origin/phase2/trial
git fetch origin phase2/trial 2>&1 | Out-Null
$headCommit = (git rev-parse HEAD 2>&1).ToString().Trim()
$originCommit = (git rev-parse origin/phase2/trial 2>&1).ToString().Trim()
if ($headCommit -and $originCommit -and ($headCommit -eq $originCommit)) {
    Write-Host "[PASS] Checkout: HEAD matches origin/phase2/trial ($headCommit)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Checkout: HEAD ($headCommit) does not match origin/phase2/trial ($originCommit)" -ForegroundColor Red
    $hasError = $true
}

# -----------------------------------------------------------------------------
# 2. Tooling Checks
# -----------------------------------------------------------------------------
Write-Host "`n--- 2. Tools ---" -ForegroundColor Yellow

# Python 3.12.x
$pyVer = cmd /c "python --version 2>&1"
if ($pyVer -match 'Python 3\.12\.\d+') {
    Write-Host "[PASS] Python: $pyVer" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Python: expected 3.12.x, got '$pyVer'" -ForegroundColor Red
    $hasError = $true
}

# Node.js
$nodeVer = cmd /c "node --version 2>&1"
if ($nodeVer -match 'v\d+\.\d+') {
    Write-Host "[PASS] Node: $nodeVer" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Node: not found or invalid ('$nodeVer')" -ForegroundColor Red
    $hasError = $true
}

# Git
$gitVer = cmd /c "git --version 2>&1"
if ($gitVer -match 'git version \d+') {
    Write-Host "[PASS] Git: $gitVer" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Git: not found or invalid ('$gitVer')" -ForegroundColor Red
    $hasError = $true
}

# Java 17+ (check $env:JAVA first, then PATH, then common JDK installs on Windows)
$javaCandidates = @()
if ($env:JAVA -and (Test-Path $env:JAVA)) { $javaCandidates += $env:JAVA }
if (Get-Command java -ErrorAction SilentlyContinue) { $javaCandidates += "java" }
$javaCandidates += (Get-ChildItem -Path "C:\Program Files\Java" -Filter "java.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)

$chosenJava = $null
$chosenJavaMajor = 0
$chosenJavaRaw = ""

foreach ($cand in $javaCandidates) {
    $outStr = ((cmd /c "`"$cand`" -version 2>&1") -join " ")
    $major = 0
    if ($outStr -match 'version "(?:1\.)?(\d+)') {
        $major = [int]$matches[1]
    }
    if ($major -ge 17) {
        $chosenJava = $cand
        $chosenJavaMajor = $major
        $chosenJavaRaw = $outStr
        break
    } elseif (-not $chosenJava) {
        $chosenJava = $cand
        $chosenJavaMajor = $major
        $chosenJavaRaw = $outStr
    }
}

if ($chosenJavaMajor -ge 17) {
    Write-Host "[PASS] Java: version $chosenJavaMajor (>= 17 required for Jenkins agent) [$chosenJava]" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Java: expected version >= 17, got major version $chosenJavaMajor ('$chosenJavaRaw')" -ForegroundColor Red
    $hasError = $true
}

# Docker OSType linux
$osType = (docker info --format "{{.OSType}}" 2>&1).ToString().Trim()
if ($osType -eq "linux") {
    Write-Host "[PASS] Docker: OSType is linux" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Docker: expected OSType 'linux', got '$osType'" -ForegroundColor Red
    $hasError = $true
}

# -----------------------------------------------------------------------------
# 3. Disk Space Check (≥ 10 GB on repo drive)
# -----------------------------------------------------------------------------
Write-Host "`n--- 3. Disk Space ---" -ForegroundColor Yellow
$freeGB = [math]::Round((Get-Item .).PSDrive.Free / 1GB, 2)
if ($freeGB -ge 10.0) {
    Write-Host "[PASS] Disk: $freeGB GB free (>= 10 GB required)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Disk: only $freeGB GB free (minimum 10 GB required)" -ForegroundColor Red
    $hasError = $true
}

# -----------------------------------------------------------------------------
# 4. Port Selection
# -----------------------------------------------------------------------------
Write-Host "`n--- 4. Port Availability ---" -ForegroundColor Yellow

# Parse candidate ports (handles "8088,8090", "8090..8099", or arrays)
$expandedPorts = @()
foreach ($entry in $Ports) {
    foreach ($item in ($entry -split '[,; ]+')) {
        if ($item -match '^\s*(\d+)\.\.(\d+)\s*$') {
            $expandedPorts += ([int]$matches[1]..[int]$matches[2])
        } elseif ($item -match '^\s*(\d+)\s*$') {
            $expandedPorts += [int]$matches[1]
        }
    }
}
if ($expandedPorts.Count -eq 0) {
    $expandedPorts = 8090..8099
}

$listeningPorts = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort
$dockerPortsStr = (docker ps -a --format "{{.Ports}}" 2>&1) -join " "

$excludedRanges = @()
$netshOut = netsh int ipv4 show excludedportrange protocol=tcp
foreach ($line in $netshOut) {
    if ($line -match '^\s*(\d+)\s+(\d+)') {
        $excludedRanges += ,@([int]$matches[1], [int]$matches[2])
    }
}

$chosenPort = $null
foreach ($p in $expandedPorts) {
    $isListening = $listeningPorts -contains $p
    $isDocker = ($dockerPortsStr -match ":$p(->|/)") -or ($dockerPortsStr -match "(^|\s)$p(\s|$)")
    $isExcluded = $false
    foreach ($r in $excludedRanges) {
        if ($p -ge $r[0] -and $p -le $r[1]) {
            $isExcluded = $true
            break
        }
    }

    if (-not $isListening -and -not $isDocker -and -not $isExcluded) {
        $chosenPort = $p
        break
    } else {
        $reasons = @()
        if ($isListening) { $reasons += "listening" }
        if ($isDocker) { $reasons += "docker published" }
        if ($isExcluded) { $reasons += "windows excluded range" }
        Write-Host "       Port $p is unavailable: $($reasons -join ', ')"
    }
}

if ($chosenPort) {
    Write-Host "PORT $chosenPort" -ForegroundColor Cyan
    Write-Host "[PASS] Port: selected free port $chosenPort" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Port: no free port found in candidates ($($expandedPorts -join ', '))" -ForegroundColor Red
    $hasError = $true
}

# -----------------------------------------------------------------------------
# 5. Internal Network Connectivity
# -----------------------------------------------------------------------------
Write-Host "`n--- 5. Internal Network ---" -ForegroundColor Yellow
$netTargets = @(
    @{ Host = "10.151.28.2";  Port = 5432;  Desc = "PostgreSQL" },
    @{ Host = "10.151.26.3";  Port = 1521;  Desc = "Oracle ACTL" },
    @{ Host = "10.151.28.9";  Port = 50051; Desc = "A100 gRPC Inference" },
    @{ Host = "th1srnas03";   Port = 445;   Desc = "NAS CIFS Storage" }
)

foreach ($t in $netTargets) {
    $res = Test-NetConnection -ComputerName $t.Host -Port $t.Port -WarningAction SilentlyContinue
    if ($res.TcpTestSucceeded) {
        Write-Host "[PASS] Network: $($t.Host):$($t.Port) ($($t.Desc)) reachable" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Network: $($t.Host):$($t.Port) ($($t.Desc)) unreachable" -ForegroundColor Red
        $hasError = $true
    }
}

# -----------------------------------------------------------------------------
# 6. Build Download Reachability (Head request, 10s)
# -----------------------------------------------------------------------------
Write-Host "`n--- 6. Build Downloads ---" -ForegroundColor Yellow
$downloadUrls = @(
    "https://pypi.org/simple/",
    "https://registry.npmjs.org/",
    "https://registry-1.docker.io/v2/",
    "https://download.oracle.com/",
    "https://github.com/"
)

foreach ($u in $downloadUrls) {
    $status = 0
    try {
        $res = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 10 -UseBasicParsing
        $status = [int]$res.StatusCode
    } catch {
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
        }
    }

    # Note: 401 on registry-1.docker.io/v2/ is valid/reachable (auth challenge)
    if ($status -ge 200 -and $status -lt 400 -or $status -eq 401) {
        Write-Host "[PASS] Download: $u (HTTP $status)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Download: $u unreachable (HTTP $status)" -ForegroundColor Red
        $hasError = $true
    }
}

# -----------------------------------------------------------------------------
# 7. Secrets & Environment Configuration (KEY NAMES ONLY, NEVER VALUES)
# -----------------------------------------------------------------------------
Write-Host "`n--- 7. Secrets & .env Keys ---" -ForegroundColor Yellow
$requiredKeys = @(
    "MARK_PG_PASSWORD",
    "MARK_WORKER_PG_PASSWORD",
    "ACTL_USER",
    "ACTL_PASSWORD",
    "NAS_USER",
    "NAS_PASSWORD",
    "MARK_INFERENCE_API_KEY"
)

if (-not (Test-Path $EnvFile)) {
    Write-Host "[FAIL] .env file '$EnvFile' does not exist" -ForegroundColor Red
    $hasError = $true
} else {
    $envMap = @{}
    foreach ($line in (Get-Content $EnvFile)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $k = $matches[1]
            $v = $matches[2].Trim("`"' ")
            $envMap[$k] = $v
        }
    }

    foreach ($k in $requiredKeys) {
        if ($envMap.ContainsKey($k) -and [string]::IsNullOrWhiteSpace($envMap[$k]) -eq $false) {
            Write-Host "[PASS] .env key: $k is set" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] .env key: $k is missing or empty" -ForegroundColor Red
            $hasError = $true
        }
    }
}

# -----------------------------------------------------------------------------
# 8. Firewall Check for Chosen Port
# -----------------------------------------------------------------------------
Write-Host "`n--- 8. Firewall Rule ---" -ForegroundColor Yellow
if ($chosenPort) {
    $hasFwRule = $false
    try {
        $fwOut = netsh advfirewall firewall show rule name=all dir=in
        $curEnabled = ""
        $curAction = ""
        $curProtocol = ""
        $curLocalPort = ""

        foreach ($line in $fwOut) {
            if ($line -match '^Rule Name:\s*(.*)') {
                if ($curEnabled -eq "Yes" -and $curAction -eq "Allow" -and $curProtocol -eq "TCP") {
                    if ($curLocalPort -match "(^|,|\s)$chosenPort(,|`$|\s)" -or $curLocalPort -eq "Any") {
                        $hasFwRule = $true
                        break
                    }
                }
                $curEnabled = ""
                $curAction = ""
                $curProtocol = ""
                $curLocalPort = ""
            } elseif ($line -match '^\s*Enabled:\s*(.*)') {
                $curEnabled = $matches[1].Trim()
            } elseif ($line -match '^\s*Action:\s*(.*)') {
                $curAction = $matches[1].Trim()
            } elseif ($line -match '^\s*Protocol:\s*(.*)') {
                $curProtocol = $matches[1].Trim()
            } elseif ($line -match '^\s*LocalPort:\s*(.*)') {
                $curLocalPort = $matches[1].Trim()
            }
        }
        if (-not $hasFwRule -and $curEnabled -eq "Yes" -and $curAction -eq "Allow" -and $curProtocol -eq "TCP") {
            if ($curLocalPort -match "(^|,|\s)$chosenPort(,|`$|\s)" -or $curLocalPort -eq "Any") {
                $hasFwRule = $true
            }
        }
    } catch {
        # continue to warn
    }

    if ($hasFwRule) {
        Write-Host "[PASS] Firewall: inbound rule allows TCP port $chosenPort" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Firewall: no enabled inbound allow rule covers port $chosenPort" -ForegroundColor Yellow
        Write-Host "       Run as administrator to allow:" -ForegroundColor Yellow
        Write-Host "       New-NetFirewallRule -DisplayName `"Mark Web $chosenPort`" -Direction Inbound -Protocol TCP -LocalPort $chosenPort -Action Allow" -ForegroundColor Yellow
    }
}

# -----------------------------------------------------------------------------
# 9. Optional -WritePort Action
# -----------------------------------------------------------------------------
if ($WritePort -and $chosenPort) {
    Write-Host "`n--- 9. Writing Port to Config ---" -ForegroundColor Yellow
    if (Test-Path $EnvFile) {
        $envLines = Get-Content $EnvFile
        $foundKey = $false
        $newLines = @()
        foreach ($line in $envLines) {
            if ($line -match '^\s*MARK_WEB_PORT=') {
                $newLines += "MARK_WEB_PORT=$chosenPort"
                $foundKey = $true
            } else {
                $newLines += $line
            }
        }
        if (-not $foundKey) {
            $newLines += "MARK_WEB_PORT=$chosenPort"
        }
        Set-Content -Path $EnvFile -Value $newLines -Encoding UTF8
        Write-Host "[PASS] Config: wrote MARK_WEB_PORT=$chosenPort to $EnvFile" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Config: cannot write port, $EnvFile does not exist" -ForegroundColor Red
        $hasError = $true
    }
}

# -----------------------------------------------------------------------------
# Summary & Exit
# -----------------------------------------------------------------------------
Write-Host ""
if ($hasError) {
    Write-Host "=== PREFLIGHT RESULT: FAILED ===" -ForegroundColor Red
    exit 1
} else {
    Write-Host "=== PREFLIGHT RESULT: ALL CHECKS PASSED ===" -ForegroundColor Green
    exit 0
}
