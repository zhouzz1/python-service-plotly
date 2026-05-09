$ErrorActionPreference = 'Stop'

function Find-PythonExe {
  $candidates = @(
    "py -3",
    "py",
    "python",
    "python3",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Program Files\Python311\python.exe",
    "C:\Program Files\Python310\python.exe",
    "C:\Program Files (x86)\Python312\python.exe",
    "C:\Program Files (x86)\Python311\python.exe",
    "C:\Program Files (x86)\Python310\python.exe"
  )

  foreach ($cmd in $candidates) {
    try {
      if ($cmd -eq "py" -or $cmd -eq "py -3") {
        & cmd /c "$cmd --version" > $null 2>&1
        if ($LASTEXITCODE -eq 0) { return $cmd }
        continue
      }

      if (Test-Path $cmd) { return $cmd }
      $resolved = Get-Command $cmd -ErrorAction Stop
      if ($resolved.Source -notlike "*WindowsApps*") { return $resolved.Source }
    } catch {}
  }

  return $null
}

$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  Write-Host "[INFO] Using existing virtualenv python: $venvPython"
} else {
  $pythonExe = Find-PythonExe
  if (-not $pythonExe) {
    Write-Host ""
    Write-Host "[ERROR] Python not found."
    Write-Host "Install Python 3.10+ and re-run this script."
    Write-Host "Download: https://www.python.org/downloads/windows/"
    Write-Host ""
    exit 1
  }

  Write-Host "[INFO] Using python: $pythonExe"

  if ($pythonExe -eq "py" -or $pythonExe -eq "py -3") {
    & cmd /c "$pythonExe -m venv .venv"
  } else {
    & $pythonExe -m venv .venv
  }

  if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Failed to create virtual environment (.venv)."
    exit 1
  }
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not $env:APP_PORT) { $env:APP_PORT = '5001' }
if (-not $env:NACOS_SERVER_ADDR) { $env:NACOS_SERVER_ADDR = '192.168.10.187:8848' }
if (-not $env:NACOS_SERVICE_NAME) { $env:NACOS_SERVICE_NAME = 'python-service' }
# 固定注册到 Java 可访问网段，避免自动探测到 192.168.10.x 导致 Feign Connection refused
if (-not $env:NACOS_DISCOVERY_IP) { $env:NACOS_DISCOVERY_IP = '192.168.2.150' }

Write-Host "[INFO] APP_PORT=$($env:APP_PORT)"
Write-Host "[INFO] NACOS_SERVER_ADDR=$($env:NACOS_SERVER_ADDR)"
Write-Host "[INFO] NACOS_SERVICE_NAME=$($env:NACOS_SERVICE_NAME)"
Write-Host "[INFO] NACOS_DISCOVERY_IP=$($env:NACOS_DISCOVERY_IP)"

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $env:APP_PORT

