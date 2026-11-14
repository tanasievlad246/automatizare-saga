<#
.SYNOPSIS
    Installs or updates e-Factura pentru SAGA on this Windows PC.

.DESCRIPTION
    Run it as the Windows user who will work with the program, in an ordinary PowerShell
    window (not "Run as administrator"): the program, its settings and its start-up
    entry all belong to that user. Windows asks for an administrator's approval by itself
    at the one step that can need it, installing Git.

    What it does, in order:

      1. Makes sure Git and uv are installed.
      2. Gets the latest release of the program from GitHub into the install folder.
         The first time it clones the repository; later it updates the same folder.
         config.toml and the data folder are never touched.
      3. Installs what the program needs inside that folder (uv fetches Python too,
         if the PC has none).
      4. Writes the first config.toml: a key of its own for the local API, and port 80
         when it is free, so the address needs no port.
      5. Makes two shortcuts. One in the Startup folder starts the program, without a
         window, every time this user signs in to Windows. One on the Desktop opens the
         page, starting the program first if it is not running.
      6. Starts the program and opens the page.

    Running it again later updates the program to the newest release.

.PARAMETER Repo
    The GitHub repository, as owner/name. Default: tanasievlad246/automatizare-saga

.PARAMETER RepoUrl
    A Git address to use instead of GitHub (a mirror, or a server of your own).

.PARAMETER InstallDir
    Where the program goes. Default: AutoSaga in this user's local application data.

.PARAMETER NoStart
    Install or update only; do not start the program or open the page.

.PARAMETER Uninstall
    Stop the program and remove the two shortcuts. The folder, with the settings and
    every saved invoice, is left where it is.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = '',
    [string]$RepoUrl = '',
    [string]$InstallDir = '',
    [switch]$NoStart,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Where the program is published. -Repo installs from another repository instead.
$DefaultRepo = 'tanasievlad246/automatizare-saga'
$ShortcutName = 'e-Factura pentru SAGA.lnk'

# --- small helpers ---------------------------------------------------------------------

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "== $Text" -ForegroundColor Cyan
}

# Run a program and stop the script if it fails. Windows PowerShell does not do that by itself.
function Invoke-Program([string]$What, [string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$What failed (exit code $LASTEXITCODE)."
    }
}

# Programs installed a moment ago are not on this window's PATH yet.
function Update-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Find-Program([string]$Name, [string[]]$UsualPlaces) {
    $found = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        return $found.Path
    }
    foreach ($place in $UsualPlaces) {
        if (Test-Path $place) {
            return $place
        }
    }
    return $null
}

function Find-Git {
    return Find-Program 'git' @((Join-Path $env:ProgramFiles 'Git\cmd\git.exe'))
}

function Find-Uv {
    return Find-Program 'uv' @((Join-Path $env:USERPROFILE '.local\bin\uv.exe'))
}

function Install-Git {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw ('Git is not installed, and winget is not available to install it. ' +
            'Install Git from https://git-scm.com/download/win, then run this script again.')
    }
    Write-Host 'Git is not installed. Installing it with winget; Windows may ask an administrator to approve.'
    Invoke-Program 'Installing Git' 'winget' @('install', '--id', 'Git.Git', '--exact', '--source', 'winget')
    Update-Path
}

function Install-Uv {
    Write-Host 'uv is not installed. Installing it for this user, with its own installer from astral.sh.'
    Invoke-Program 'Installing uv' 'powershell.exe' @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', 'irm https://astral.sh/uv/install.ps1 | iex'
    )
    Update-Path
}

# The tag of the latest release; $null when the repository has no release yet.
function Get-LatestRelease([string]$Git, [string]$Url) {
    if ($Repo) {
        try {
            $headers = @{ 'User-Agent' = 'autosaga-installer'; 'Accept' = 'application/vnd.github+json' }
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $headers
            if ($release.tag_name) {
                return [string]$release.tag_name
            }
        } catch {
            # A private repository, no release yet, or GitHub's hourly limit: ask Git instead.
        }
    }
    # The highest version among the tags, which is what a release is made from.
    $tags = @(& $Git ls-remote --tags --refs '--sort=-v:refname' $Url)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read $Url. Check the address, and that this PC is signed in to it if it is private."
    }
    if ($tags.Count -gt 0 -and $tags[0]) {
        return ($tags[0] -split 'refs/tags/')[1]
    }
    return $null
}

function New-ProgramShortcut([string]$Folder, [string]$Command) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $Folder $ShortcutName))
    # pythonw.exe: Python without a console window.
    $shortcut.TargetPath = $PythonW
    $shortcut.Arguments = "-m efactura --config `"$Config`" $Command"
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = 'e-Factura pentru SAGA'
    $shortcut.Save()
}

function Remove-ProgramShortcut([string]$Folder) {
    $path = Join-Path $Folder $ShortcutName
    if (Test-Path $path) {
        Remove-Item $path
        Write-Host "Removed $path"
    }
}

# Ask the running program to stop. Its files cannot be replaced while it runs.
function Stop-Program {
    if ((Test-Path $Python) -and (Test-Path $Config)) {
        & $Python -m efactura --config $Config stop
        if ($LASTEXITCODE -ne 0) {
            throw 'The running program could not be stopped. Sign out of Windows and in again, then run this script once more.'
        }
    }
}

# --- where things are ------------------------------------------------------------------

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'AutoSaga'
}
$Config = Join-Path $InstallDir 'config.toml'
$Python = Join-Path $InstallDir '.venv\Scripts\python.exe'
$PythonW = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
$Startup = [Environment]::GetFolderPath('Startup')
$Desktop = [Environment]::GetFolderPath('Desktop')

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$elevated = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($elevated) {
    Write-Warning ("This window runs as administrator, as the Windows user $($identity.Name). " +
        'The program will be set up for that user. If someone else will work with it, close ' +
        'this window and run the script from their own account, without "Run as administrator".')
}

# --- removing ----------------------------------------------------------------------------

if ($Uninstall) {
    Write-Step 'Stopping the program and removing its shortcuts'
    Stop-Program
    Remove-ProgramShortcut $Startup
    Remove-ProgramShortcut $Desktop
    Write-Host ''
    Write-Host "Done. The program no longer starts with Windows. Its folder was left in place: $InstallDir"
    Write-Host 'It holds config.toml and every saved invoice. Delete it by hand once nothing in it is needed.'
    return
}

# --- 1. Git and uv -----------------------------------------------------------------------

if (-not $Repo -and -not $RepoUrl) {
    $Repo = $DefaultRepo
}
if (-not $RepoUrl) {
    if ($Repo -notmatch '^[\w.-]+/[\w.-]+$') {
        throw "'$Repo' is not a GitHub repository name. Write it as owner/name."
    }
    $RepoUrl = "https://github.com/$Repo.git"
}

# Older Windows 10 starts PowerShell with TLS 1.0, which GitHub and astral.sh refuse.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

Write-Step 'Checking for Git and uv'
$Git = Find-Git
if (-not $Git) {
    Install-Git
    $Git = Find-Git
    if (-not $Git) {
        throw 'Git was installed but cannot be found. Close this window, open a new one and run the script again.'
    }
}
$Uv = Find-Uv
if (-not $Uv) {
    Install-Uv
    $Uv = Find-Uv
    if (-not $Uv) {
        throw 'uv was installed but cannot be found. Close this window, open a new one and run the script again.'
    }
}
Write-Host "Git: $Git"
Write-Host "uv:  $Uv"

# --- 2. The latest release ---------------------------------------------------------------

Write-Step "Getting the latest release from $RepoUrl"
$release = Get-LatestRelease $Git $RepoUrl
if ($release) {
    $target = $release
    Write-Host "Latest release: $release"
} else {
    $target = 'origin/HEAD'
    Write-Warning 'The repository has no release yet. Installing its main branch as it is now.'
}

$updating = Test-Path (Join-Path $InstallDir '.git')
if ($updating) {
    Write-Host "Updating the program in $InstallDir"
    Stop-Program
    Invoke-Program 'Fetching the release' $Git @('-C', $InstallDir, 'fetch', '--tags', '--prune', 'origin')
} else {
    if ((Test-Path $InstallDir) -and (Get-ChildItem -Force $InstallDir | Select-Object -First 1)) {
        throw "$InstallDir already exists and is not an installation of this program. Choose another folder with -InstallDir."
    }
    Write-Host "Installing the program into $InstallDir"
    Invoke-Program 'Cloning the repository' $Git @('clone', $RepoUrl, $InstallDir)
}
# --detach: the folder holds exactly that release, not a branch that moves.
Invoke-Program "Switching to $target" $Git @(
    '-C', $InstallDir, '-c', 'advice.detachedHead=false', 'checkout', '--detach', $target
)

# --- 3. What the program needs -----------------------------------------------------------

Write-Step 'Installing what the program needs (the first time this downloads Python and takes a few minutes)'
# --frozen: exactly the versions the release was tested with. --no-dev: not the test tools.
Invoke-Program 'Installing the dependencies' $Uv @('sync', '--frozen', '--no-dev', '--project', $InstallDir)
if (-not (Test-Path $PythonW)) {
    throw "The program's Python was not found at $PythonW after installing."
}

# --- 4. The first settings ---------------------------------------------------------------

Write-Step 'Writing the settings'
$answer = & $Python -m efactura --config $Config setup | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "The settings could not be written: $answer"
}
$settings = $answer | ConvertFrom-Json
if ($settings.created) {
    Write-Host "Wrote $Config"
} else {
    Write-Host "Kept the existing $Config"
}
$page = $settings.page

# --- 5. Starting with Windows, and the Desktop shortcut ----------------------------------

Write-Step 'Making the shortcuts'
New-ProgramShortcut $Startup 'start'
New-ProgramShortcut $Desktop 'open'
Write-Host "Starts when $($identity.Name) signs in to Windows: $(Join-Path $Startup $ShortcutName)"
Write-Host "On the Desktop: $(Join-Path $Desktop $ShortcutName)"

# --- 6. Start it -------------------------------------------------------------------------

if (-not $NoStart) {
    Write-Step 'Starting the program and opening the page'
    Invoke-Program 'Starting the program' $Python @('-m', 'efactura', '--config', $Config, 'open')
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
Write-Host "The page:      $page"
Write-Host "The program:   $InstallDir"
Write-Host 'To update:     run this script again.'
Write-Host 'To remove:     run this script with -Uninstall.'
Write-Host 'Next, on the page: "Chei si parole" for the ANAF and OpenRouter keys, then connect to ANAF.'
