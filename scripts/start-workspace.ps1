param(
  [ValidateRange(1, 65535)][int]$Port = 8765,
  [switch]$NoBrowser,
  [string]$Repository = (Join-Path $PSScriptRoot '..')
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath $Repository).Path.TrimEnd('\', '/')
$pythonPath = Join-Path $repositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
  throw "Missing isolated Python environment. Run '$repositoryRoot/scripts/setup-demo.ps1' first."
}
. (Join-Path $repositoryRoot 'scripts/env.ps1')
$workspaceDirectory = Join-Path $repositoryRoot '.cache/workspace'
New-Item -ItemType Directory -Path $workspaceDirectory -Force | Out-Null
$url = "http://127.0.0.1:$Port/"

function Read-WorkspaceHealth {
  try {
    $request = [System.Net.HttpWebRequest]::Create("${url}api/health")
    $request.Proxy = $null
    $request.Timeout = 500
    $request.ReadWriteTimeout = 500
    $response = $request.GetResponse()
    try {
      $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
      try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
  } catch { return $null }
}

function Test-WorkspaceIdentity($Health) {
  if ($null -eq $Health) { return $false }
  try {
    return ($Health.application -eq 'gamingcreator-workspace' -and
      $Health.apiVersion -eq 1 -and [int]$Health.pid -gt 0 -and
      [IO.Path]::GetFullPath([string]$Health.repository).TrimEnd('\', '/') -eq $repositoryRoot)
  } catch { return $false }
}

function Test-ListeningPort {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $pending = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
    try {
      if (-not $pending.AsyncWaitHandle.WaitOne(500)) { return $false }
      $client.EndConnect($pending)
      return $true
    } finally { $pending.AsyncWaitHandle.Close() }
  } catch { return $false } finally { $client.Dispose() }
}

function Stop-OwnedHelper($Helper) {
  $Helper.Refresh()
  if ($Helper.HasExited) { return }
  # ToolHelp32 reads parent IDs without WMI. The held live helper handle keeps
  # its PID from being mistaken for a later unrelated process during cleanup.
  if (-not ('GamingCreatorHelperChildren' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class GamingCreatorHelperChildren {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  struct Entry {
    public uint size, usage, pid;
    public UIntPtr heap;
    public uint module, threads, parent;
    public int priority;
    public uint flags;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string executable;
  }
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint pid);
  [DllImport("kernel32.dll", EntryPoint = "Process32FirstW", SetLastError = true)]
  static extern bool First(IntPtr snapshot, ref Entry entry);
  [DllImport("kernel32.dll", EntryPoint = "Process32NextW", SetLastError = true)]
  static extern bool Next(IntPtr snapshot, ref Entry entry);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  public static uint[] Find(int parent) {
    IntPtr snapshot = CreateToolhelp32Snapshot(2, 0);
    if (snapshot == new IntPtr(-1)) throw new Win32Exception();
    try {
      Entry entry = new Entry(); entry.size = (uint)Marshal.SizeOf(typeof(Entry));
      var children = new List<uint>();
      if (First(snapshot, ref entry)) do {
        if (entry.parent == (uint)parent) children.Add(entry.pid);
      } while (Next(snapshot, ref entry));
      return children.ToArray();
    } finally { CloseHandle(snapshot); }
  }
}
'@
  }
  foreach ($childPid in [GamingCreatorHelperChildren]::Find($Helper.Id)) {
    Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue
  }
  # Stopping its child can make the venv redirector exit immediately.
  try {
    $Helper.Refresh()
    if (-not $Helper.HasExited) { Stop-Process -InputObject $Helper -Force }
  } catch {
    $Helper.Refresh()
    if (-not $Helper.HasExited) { throw }
  }
}

# A per-repository/port lock also makes simultaneous double-clicks reuse one server.
$hash = [Security.Cryptography.SHA256]::Create()
try {
  $repositoryKey = [BitConverter]::ToString($hash.ComputeHash(
    [Text.Encoding]::UTF8.GetBytes($repositoryRoot.ToLowerInvariant()))).Replace('-', '')
} finally { $hash.Dispose() }
$mutex = New-Object System.Threading.Mutex($false, "Local\GamingCreator.Workspace.$repositoryKey.$Port")
$lockAcquired = $false
$serverProcess = $null
try {
  try { $lockAcquired = $mutex.WaitOne(15000) }
  catch [System.Threading.AbandonedMutexException] { $lockAcquired = $true }
  if (-not $lockAcquired) { throw 'Another workspace launch is still starting; retry shortly.' }

  $health = Read-WorkspaceHealth
  $statePath = Join-Path $workspaceDirectory "port-$Port.json"
  if (Test-WorkspaceIdentity $health) {
    Write-Host "Reusing workspace: $url (PID $($health.pid))"
    Write-Host "Local logs and launch state: $workspaceDirectory"
  } else {
    if (Test-ListeningPort) {
      throw "Port $Port is occupied by another service or an older workspace without matching health information. Nothing was stopped. Close that service yourself, or use -Port <free-port>."
    }
    $launchId = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $workspaceDirectory "$launchId.stdout.log"
    $stderrPath = Join-Path $workspaceDirectory "$launchId.stderr.log"
    Write-Host "Starting workspace. Logs: $stdoutPath ; $stderrPath"
    $arguments = @('-B', '-u', '-m', 'gamingcreator.ui', '--host', '127.0.0.1',
      '--port', [string]$Port, '--repository', ('"' + $repositoryRoot + '"'))
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $arguments `
      -WorkingDirectory $repositoryRoot -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    # Keep the process handle: Windows PowerShell otherwise loses a quick exit code.
    $null = $serverProcess.Handle
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
      $health = Read-WorkspaceHealth
      if (Test-WorkspaceIdentity $health) { break }
      $serverProcess.Refresh()
      if ($serverProcess.HasExited) {
        throw "Workspace exited with code $($serverProcess.ExitCode). See $stderrPath"
      }
      Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not (Test-WorkspaceIdentity $health)) {
      throw "Workspace did not become ready within 15 seconds. See $stderrPath"
    }
    # A Windows venv executable may launch the actual interpreter as its child.
    $servicePid = [int]$health.pid
    if ($servicePid -ne $serverProcess.Id -and [int]$health.parentPid -ne $serverProcess.Id) {
      throw "The responding service does not belong to this launch. See $stderrPath"
    }
    [ordered]@{
      application = 'gamingcreator-workspace'; repository = $repositoryRoot
      pid = $servicePid; helperPid = $serverProcess.Id; port = $Port; url = $url; launchId = $launchId
      stdout = $stdoutPath; stderr = $stderrPath
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-Host "Workspace ready: $url (PID $($health.pid))"
    Write-Host "Launch state: $statePath"
    # A successfully started background server outlives this launcher.
    $serverProcess = $null
  }
} catch {
  $startupFailure = $_
  if ($null -ne $serverProcess) {
    try { Stop-OwnedHelper $serverProcess }
    catch { Write-Warning "Could not clean up the owned startup helper: $($_.Exception.Message)" }
  }
  throw $startupFailure
} finally {
  if ($lockAcquired) { $mutex.ReleaseMutex() }
  $mutex.Dispose()
}
if (-not $NoBrowser) { Start-Process -FilePath $url }
Write-Host 'Previewing and searching existing results does not start paid analysis.'
