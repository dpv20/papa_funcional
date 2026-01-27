# funciones/install_run.ps1
$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

# ---------------- Config ----------------
$VenvName      = "constru"
$PythonExe     = "python-3.11.5-amd64.exe"
$GitExeSetup   = "Git-2.51.0-64-bit.exe"
$IconAppRel    = "media\pavez_P_logo.ico"   # ícono app (lnk a la app)
$IconInstRel   = "media\pavez_logo.ico"     # ícono instalador (lnk al .bat raíz)
$DoGitPush     = $true
$GitRemoteUrl  = "https://github.com/dpv20/papa_funcional"
$AppShortcut   = "Pavez Budget.lnk"
$InstShortcut  = "Instalar Pavez.lnk"

# ------------- Ubicaciones -------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-RepoRoot([string]$startDir) {
  $p = (Resolve-Path $startDir).Path
  for ($i=0; $i -lt 6; $i++) {
    if (Test-Path (Join-Path $p ".git")) { return $p }
    $parent = Split-Path -Parent $p
    if ($parent -eq $p) { break }
    $p = $parent
  }
  return (Split-Path -Parent $startDir)
}

$Root = Find-RepoRoot $ScriptDir
Set-Location $Root

$PythonInstaller = Join-Path $Root $PythonExe
$GitInstaller    = Join-Path $Root $GitExeSetup
$IconAppPath     = Join-Path $Root $IconAppRel
$IconInstPath    = Join-Path $Root $IconInstRel

function Test-Command($cmd) {
  $old = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
  $ok = (Get-Command $cmd -ErrorAction SilentlyContinue) -ne $null
  $ErrorActionPreference = $old
  return $ok
}

# ------------- .gitignore (ignorar venv) -------------
$GitIgnorePath = Join-Path $Root ".gitignore"
$IgnoreLines = @(
  "constru/",
  ".venv/",
  "venv/",
  "__pycache__/",
  "*.py[cod]",
  "*.pyo",
  "*.pyd",
  "*.egg-info/",
  ".streamlit/secrets.toml",
  ".DS_Store",
  "Thumbs.db",
  ".vscode/",
  ".idea/"
)
if (-not (Test-Path $GitIgnorePath)) {
  $IgnoreLines -join "`r`n" | Out-File -Encoding ascii $GitIgnorePath
} else {
  $existing = Get-Content $GitIgnorePath -ErrorAction SilentlyContinue
  foreach ($line in $IgnoreLines) {
    if ($existing -notcontains $line) { Add-Content -Path $GitIgnorePath -Value $line }
  }
}

# ------------- Python -------------
Write-Host "==> Instalando/Verificando Python..."
if (-not (Test-Command "python") -and -not (Test-Command "py")) {
  if (-not (Test-Path $PythonInstaller)) { Write-Error "Falta $PythonExe en $Root"; exit 1 }
  Start-Process -FilePath $PythonInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait
} else { Write-Host "Python ya presente." }

$PyCmd = $null
if (Test-Command "py") { try { & python -V | Out-Null; $PyCmd = "python" } catch {} }
if (-not $PyCmd) { $PyCmd = "python" }

# ------------- Git -------------
Write-Host "==> Instalando/Verificando Git..."
if (-not (Test-Command "git")) {
  if (-not (Test-Path $GitInstaller)) { Write-Error "Falta $GitExeSetup en $Root"; exit 1 }
  Start-Process -FilePath $GitInstaller -ArgumentList "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES" -Wait
} else { Write-Host "Git ya presente." }
$GitCmd = if (Test-Command "git") { "git" } else { "C:\Program Files\Git\bin\git.exe" }

# ------------- Venv + deps -------------
Write-Host "==> Creando/actualizando venv '$VenvName'..."
& $PyCmd -m venv (Join-Path $Root $VenvName)
$VenvPython = Join-Path $Root "$VenvName\Scripts\python.exe"
$VenvPip    = Join-Path $Root "$VenvName\Scripts\pip.exe"
if (-not (Test-Path $VenvPython)) { Write-Error "No se creó el venv."; exit 1 }

Write-Host "==> Instalando requirements..."
& $VenvPython -m pip install --upgrade pip setuptools wheel
if (-not (Test-Path (Join-Path $Root "requirements.txt"))) { Write-Error "Falta requirements.txt en $Root"; exit 1 }
& $VenvPip install -r (Join-Path $Root "requirements.txt")

# ------------- Lanzadores en raíz (sin consola) -------------
Write-Host "==> Generando 'run_app.cmd' en raíz..."
$RunCmdPath = Join-Path $Root "run_app.cmd"
@"
@echo off
setlocal
cd /d "%~dp0"
"%~dp0$VenvName\Scripts\python.exe" -m streamlit run app.py
"@ | Out-File -Encoding ascii $RunCmdPath -Force

# run_app_hidden.vbs eliminado - ya no se genera

# ------------- Instalador .BAT en RAÍZ (no en funciones) -------------
Write-Host "==> Wrapper 'install_run.bat' en raíz..."
$InstallerBatPath = Join-Path $Root "install_run.bat"
@"
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0funciones\install_run.ps1"
"@ | Out-File -Encoding ascii $InstallerBatPath -Force

# (Opcional) borra el .bat viejo en funciones si existía
$OldBat = Join-Path $ScriptDir "install_run.bat"
if (Test-Path $OldBat) { Remove-Item $OldBat -Force }

# ------------- Accesos directos en Escritorio -------------
$Desktop = [Environment]::GetFolderPath("Desktop")

Write-Host "==> Acceso directo APP..."
$AppLnk  = Join-Path $Desktop $AppShortcut
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($AppLnk)
$Shortcut.TargetPath = $RunCmdPath
$Shortcut.WorkingDirectory = $Root
if (Test-Path $IconAppPath) { $Shortcut.IconLocation = $IconAppPath }
$Shortcut.Description = "Abrir app de presupuesto (Streamlit)"
$Shortcut.Save()

Write-Host "==> Acceso directo del INSTALADOR apuntando al .bat de RAÍZ..."
$InstLnk = Join-Path $Desktop $InstShortcut
$Shortcut2 = $WshShell.CreateShortcut($InstLnk)
$Shortcut2.TargetPath = $InstallerBatPath          # <-- .bat en la RAÍZ
$Shortcut2.WorkingDirectory = $Root
if (Test-Path $IconInstPath) { $Shortcut2.IconLocation = $IconInstPath }  # media\pavez_logo.ico
$Shortcut2.Description = "Instalar / Reparar Pavez"
$Shortcut2.Save()

# ------------- (Opcional) Push inicial -------------
Write-Host "==> (Opcional) Git push..."
if ($DoGitPush -and (Test-Path (Join-Path $Root ".git"))) {
  try {
    $origin = & $GitCmd remote get-url origin 2>$null
    if (-not $origin) { & $GitCmd remote add origin $GitRemoteUrl }
    & $GitCmd add -A
    & $GitCmd commit -m ("Installer auto-commit " + (Get-Date -Format s)) 2>$null
    & $GitCmd pull --rebase origin main 2>$null
    & $GitCmd push origin main
  } catch {
    Write-Warning "No se pudo sincronizar automáticamente. Revisa credenciales o conflictos."
  }
} else { Write-Host "Git push omitido." }

Write-Host "`nListo. El .bat quedó en la RAÍZ y el acceso directo usa el ícono de media/pavez_logo.ico."
