<#
.SYNOPSIS
    Gracefully stop authserver.exe / worldserver.exe, falling back to a force kill.

.DESCRIPTION
    build_and_run.bat used to `taskkill /F` the servers. That skips World::StopNow,
    so log appenders never flush and online players (including every bot) never
    save -- which is why a crash used to leave nothing readable behind.

    worldserver installs a Boost.Asio signal_set for SIGINT/SIGTERM/SIGBREAK
    (src/server/apps/worldserver/Main.cpp:229-233). On Windows, Asio maps those to
    a console control handler that fires on CTRL_C_EVENT and CTRL_BREAK_EVENT.

    Note that `taskkill` without /F does NOT reach that handler: it posts WM_CLOSE,
    which a console app receives as CTRL_CLOSE_EVENT, which Asio does not hook --
    so the default handler terminates the process just as abruptly. The only way to
    get a graceful stop from outside the process is to attach to its console and
    raise a control event ourselves, which is what this script does.

    Two hard-won details in that dance:

    * It raises CTRL_C_EVENT, not CTRL_BREAK_EVENT. GenerateConsoleCtrlEvent
      signals *every* process attached to the console -- including the process that
      raised it. SetConsoleCtrlHandler(NULL, TRUE) makes the caller ignore CTRL_C,
      but there is no way to ignore CTRL_BREAK. With CTRL_BREAK this script died of
      STATUS_CONTROL_C_EXIT (0xC000013A), and cmd.exe, seeing that exit code from
      the child it was waiting on, printed "Terminate batch job (Y/N)?" and ended
      build_and_run.bat right after the LLM-chatter shutdown -- every run.

    * The attach/signal happens in a short-lived child process (-SignalPid), not
      here. Borrowing another console means FreeConsole()ing our own, after which
      this script's own Write-Host output goes nowhere. Keeping the console juggling
      in a child leaves the parent's console intact so its progress lines are still
      readable, and gives a second layer of insulation for the exit code cmd sees.

.PARAMETER Names
    Process names to stop. Defaults to worldserver.exe and authserver.exe.

.PARAMETER TimeoutSeconds
    How long to wait for a graceful exit before force killing. Default 20.

.PARAMETER SignalPid
    Internal. When set, this invocation is the signalling child: it attaches to
    that process's console, raises CTRL_C there, and exits (0 = raised).
#>
[CmdletBinding()]
param(
    [string[]] $Names = @('worldserver.exe', 'authserver.exe'),
    [int]      $TimeoutSeconds = 20,
    [int]      $SignalPid = 0
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Child mode: borrow the target's console and raise CTRL_C in it.
# ---------------------------------------------------------------------------
if ($SignalPid -gt 0) {
    Add-Type -Namespace Win32 -Name ConsoleCtrl -MemberDefinition @'
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool AttachConsole(uint dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool FreeConsole();

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
'@

    $CTRL_C_EVENT = 0

    # Ignore CTRL_C before detaching: the event we are about to raise comes back
    # to us as well, and dying here would hand cmd.exe a control-C exit code.
    [void][Win32.ConsoleCtrl]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
    [void][Win32.ConsoleCtrl]::FreeConsole()

    if (-not [Win32.ConsoleCtrl]::AttachConsole([uint32] $SignalPid)) { exit 3 }

    # The ignore flag is per-console, so re-apply it on the borrowed one.
    [void][Win32.ConsoleCtrl]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
    $sent = [Win32.ConsoleCtrl]::GenerateConsoleCtrlEvent([uint32] $CTRL_C_EVENT, [uint32] 0)
    [void][Win32.ConsoleCtrl]::FreeConsole()

    exit ($(if ($sent) { 0 } else { 3 }))
}

# ---------------------------------------------------------------------------
# Parent mode
# ---------------------------------------------------------------------------
$selfExe = (Get-Process -Id $PID).Path

function Send-CtrlC {
    param([int] $ProcessId)

    $child = Start-Process -FilePath $selfExe -NoNewWindow -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-SignalPid', $ProcessId
    )
    return ($child.ExitCode -eq 0)
}

$anyRunning = $false

foreach ($name in $Names) {
    $procs = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($name)) -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { continue }
    $anyRunning = $true

    foreach ($p in $procs) {
        $sent = $false
        try { $sent = Send-CtrlC -ProcessId $p.Id } catch { $sent = $false }

        if (-not $sent) {
            Write-Host "      $name (PID $($p.Id)): could not signal, force killing."
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
            continue
        }

        if ($p.WaitForExit($TimeoutSeconds * 1000)) {
            Write-Host "      $name stopped gracefully."
        }
        else {
            Write-Host "      $name did not exit in ${TimeoutSeconds}s - force killing."
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}

if (-not $anyRunning) {
    Write-Host '      No servers were running.'
}

# Signal to the caller whether anything was stopped, so it can decide to pause.
exit ($(if ($anyRunning) { 1 } else { 0 }))
