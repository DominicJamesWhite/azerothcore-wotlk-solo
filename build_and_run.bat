@ECHO OFF
SETLOCAL EnableDelayedExpansion

REM ============================================================
REM  Alonecraft Build & Run Script
REM  Stop server -> Build C++ -> Build DBC -> Deploy MPQ -> Start server
REM ============================================================

REM -- Configuration -------------------------------------------
SET "SOURCE_DIR=%~dp0."
SET "BUILD_DIR=C:\Build"
SET "SLN_PATH=%BUILD_DIR%\AzerothCore.sln"
SET "BUILD_CONFIG=RelWithDebInfo"
SET "SERVER_DIR=%BUILD_DIR%\bin\RelWithDebInfo"
SET "SERVER_EXE=worldserver.exe"
SET "DBC_SCRIPT_DIR=%~dp0modules\world_of_alonecraft\dbc"
SET "DBC_SCRIPT=build_dbc.py"
SET "MPQ_OUTPUT=%~dp0modules\world_of_alonecraft\dbc\output\patch-4.mpq"
SET "WOW_DATA=C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Data"
SET "PYTHON=python"
SET "VERIFY_SCRIPT=%~dp0tools\verify_scripts.py"
SET "VERIFY_DB_SCRIPT=%~dp0tools\verify_db.py"
SET "WOW_CACHE=C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Cache"
SET "LLM_BRIDGE_SCRIPT=%~dp0modules\mod-llm-chatter\tools\llm_chatter_bridge.py"
SET "LLM_BRIDGE_CONF=%BUILD_DIR%\bin\%BUILD_CONFIG%\configs\modules\mod_llm_chatter.conf"

REM -- Parse command-line flags --------------------------------
SET "SKIP_CMAKE=0"
SET "SKIP_BUILD=0"
SET "SKIP_DBC=0"
SET "SKIP_UI=0"
SET "SKIP_COPY=0"
SET "SKIP_SERVER=0"
SET "SKIP_VERIFY=0"
SET "SKIP_BRIDGE=0"

:PARSE_ARGS
IF "%~1"=="" GOTO ARGS_DONE
IF /I "%~1"=="--skip-cmake"  SET "SKIP_CMAKE=1"  & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-build"  SET "SKIP_BUILD=1"  & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-dbc"    SET "SKIP_DBC=1"    & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-ui"     SET "SKIP_UI=1"     & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-copy"   SET "SKIP_COPY=1"   & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-server" SET "SKIP_SERVER=1"  & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-verify" SET "SKIP_VERIFY=1" & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--skip-bridge" SET "SKIP_BRIDGE=1" & SHIFT & GOTO PARSE_ARGS
IF /I "%~1"=="--help" GOTO SHOW_HELP
ECHO Unknown flag: %~1
GOTO SHOW_HELP
:ARGS_DONE

REM ============================================================
REM  STEP 1: Stop servers if running
REM ============================================================
ECHO.
ECHO [1/5] Stopping servers if running...
SET "KILLED=0"
REM Also kill any running LLM chatter bridge: the python process plus the
REM "cmd /k" wrapper it was launched from (which stays open on its own once
REM python exits). Matching is restricted to python* processes because the
REM FOR /F helper "cmd /c" and PowerShell itself carry the search string in
REM their own command lines and would otherwise match themselves.
SET "BRIDGE_KILLED=0"
FOR /F "usebackq tokens=*" %%p IN (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*llm_chatter_bridge*' } | ForEach-Object { $_.ProcessId; $par = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.ParentProcessId); if ($par -and $par.Name -eq 'cmd.exe') { $par.ProcessId } }" 2^>NUL`) DO (
    taskkill /PID %%p /F /T >NUL 2>&1
    SET "BRIDGE_KILLED=1"
    SET "KILLED=1"
)
IF "!BRIDGE_KILLED!"=="1" ECHO       LLM chatter bridge stopped.
FOR %%s IN (worldserver.exe authserver.exe) DO (
    tasklist /FI "IMAGENAME eq %%s" 2>NUL | %SystemRoot%\System32\find.exe /I "%%s" >NUL
    IF !ERRORLEVEL!==0 (
        taskkill /IM %%s /F >NUL 2>&1
        ECHO       %%s stopped.
        SET "KILLED=1"
    )
)
IF "%KILLED%"=="0" ECHO       No servers were running.
IF "%KILLED%"=="1" timeout /t 2 /nobreak >NUL

REM -- Clear WoW client cache so changed data is picked up -----
IF EXIST "%WOW_CACHE%" (
    RMDIR /S /Q "%WOW_CACHE%" >NUL 2>&1
    ECHO       WoW client cache cleared.
) ELSE (
    ECHO       No client cache to clear.
)

REM ============================================================
REM  STEP 1.5: Verify script consistency
REM ============================================================
IF "%SKIP_VERIFY%"=="1" (
    ECHO.
    ECHO [1.5/5] Script verification SKIPPED ^(--skip-verify^)
    GOTO AFTER_VERIFY
)

IF EXIST "%VERIFY_SCRIPT%" (
    ECHO.
    ECHO [1.5/5] Verifying script consistency...
    %PYTHON% "%VERIFY_SCRIPT%"
    REM Must be !ERRORLEVEL!, not %ERRORLEVEL%: this IF lives inside the
    REM parenthesised IF EXIST block, so %VAR% would be expanded once when the
    REM block is parsed -- i.e. before python runs -- and would test a stale
    REM value, prompting even when the checker passed.
    IF !ERRORLEVEL! NEQ 0 (
        ECHO.
        ECHO  Script consistency issues found. Review above and fix before building.
        SET /P "CONTINUE=  Continue anyway? (y/N): "
        IF /I NOT "!CONTINUE!"=="y" EXIT /B 1
    )
) ELSE (
    ECHO.
    ECHO [1.5/5] verify_scripts.py not found, skipping consistency check.
)
:AFTER_VERIFY

REM ============================================================
REM  STEP 1.8: CMake configure/generate
REM ============================================================
IF "%SKIP_BUILD%"=="1" GOTO AFTER_CMAKE
IF "%SKIP_CMAKE%"=="1" (
    IF EXIST "%SLN_PATH%" (
        ECHO.
        ECHO [1.8/5] CMake SKIPPED ^(--skip-cmake^)
        GOTO AFTER_CMAKE
    )
    ECHO.
    ECHO       WARNING: --skip-cmake ignored because %SLN_PATH% does not exist.
)

REM Find cmake.exe
SET "CMAKE="
WHERE cmake >NUL 2>&1
IF %ERRORLEVEL%==0 (
    SET "CMAKE=cmake"
) ELSE (
    REM Check common installation paths
    IF EXIST "C:\Program Files\CMake\bin\cmake.exe" SET "CMAKE=C:\Program Files\CMake\bin\cmake.exe"
)
IF NOT DEFINED CMAKE (
    ECHO ERROR: cmake.exe not found. Install CMake and ensure it is on PATH.
    EXIT /B 1
)

IF NOT EXIST "%BUILD_DIR%" MKDIR "%BUILD_DIR%"

ECHO.
ECHO [1.8/5] Running CMake configure...
ECHO       Source: %SOURCE_DIR%
ECHO       Build:  %BUILD_DIR%

REM If a CMakeCache already exists, reconfigure without -G/-A to respect the
REM existing generator and platform.  Only specify them for a fresh build dir.
IF EXIST "%BUILD_DIR%\CMakeCache.txt" (
    ECHO       (reusing existing CMake cache)
    ECHO.
    "%CMAKE%" -S "%SOURCE_DIR%" -B "%BUILD_DIR%" ^
        -DSCRIPTS=static -DMODULES=static -DAPPS_BUILD=all -DTOOLS_BUILD=none
) ELSE (
    ECHO.
    "%CMAKE%" -S "%SOURCE_DIR%" -B "%BUILD_DIR%" -G "Visual Studio 17 2022" -A x64 ^
        -DSCRIPTS=static -DMODULES=static -DAPPS_BUILD=all -DTOOLS_BUILD=none
)
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO ************************************************************
    ECHO  CMAKE CONFIGURE FAILED! Fix errors above and re-run.
    ECHO ************************************************************
    EXIT /B 1
)

ECHO.
ECHO       CMake configure succeeded.
:AFTER_CMAKE

REM ============================================================
REM  STEP 2: Build C++ via MSBuild
REM ============================================================
IF "%SKIP_BUILD%"=="1" (
    ECHO.
    ECHO [2/5] C++ build SKIPPED ^(--skip-build^)
    GOTO AFTER_BUILD
)

ECHO.
ECHO [2/5] Building C++ project...

REM Find MSBuild - try vswhere first, then known paths
SET "MSBUILD="
SET VSWHERE_DIR=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer
IF EXIST "%VSWHERE_DIR%\vswhere.exe" (
    FOR /F "usebackq tokens=*" %%i IN (`"%VSWHERE_DIR%\vswhere.exe" -latest -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe"`) DO SET "MSBUILD=%%i"
)
REM Fallback: check common VS2022 Community path
IF NOT DEFINED MSBUILD (
    IF EXIST "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" (
        SET "MSBUILD=C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
    )
)
IF NOT DEFINED MSBUILD (
    ECHO ERROR: MSBuild.exe not found. Ensure VS2022 C++ workload is installed.
    EXIT /B 1
)

ECHO       MSBuild: %MSBUILD%
ECHO       Solution: %SLN_PATH%
ECHO       Config: %BUILD_CONFIG%
ECHO.

"%MSBUILD%" "%SLN_PATH%" /p:Configuration=%BUILD_CONFIG% /p:Platform=x64 /m /verbosity:minimal
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO ************************************************************
    ECHO  BUILD FAILED! Fix errors above and re-run.
    ECHO ************************************************************
    EXIT /B 1
)

ECHO.
ECHO       C++ build succeeded.
:AFTER_BUILD

REM ============================================================
REM  STEP 2.5: Pre-apply module SQL (so DBC build sees latest data)
REM ============================================================
IF "%SKIP_DBC%"=="1" GOTO AFTER_SQL

SET "MODULE_SQL_DIR=%SOURCE_DIR%\modules\world_of_alonecraft\data\sql\db-world"

IF NOT EXIST "%MODULE_SQL_DIR%" (
    ECHO.
    ECHO [2.5/5] No module SQL directory found, skipping pre-apply.
    GOTO AFTER_SQL
)

ECHO.
ECHO [2.5/5] Pre-applying module SQL to database...

FOR /F "tokens=*" %%f IN ('DIR /B /O:N "%MODULE_SQL_DIR%\*.sql" 2^>NUL') DO (
    mysql -h 127.0.0.1 -u acore -pacore acore_world < "%MODULE_SQL_DIR%\%%f"
    IF !ERRORLEVEL! NEQ 0 (
        ECHO       WARNING: Failed to apply %%f
    )
)

ECHO       Module SQL pre-applied.
:AFTER_SQL

REM ============================================================
REM  STEP 3: Build DBC (patched Spell.dbc + patch-4.mpq)
REM ============================================================
IF "%SKIP_DBC%"=="1" (
    ECHO.
    ECHO [3/5] DBC build SKIPPED ^(--skip-dbc^)
    GOTO AFTER_DBC
)

ECHO.
ECHO [3/5] Building patched DBC...

PUSHD "%DBC_SCRIPT_DIR%"
%PYTHON% "%DBC_SCRIPT%"
IF %ERRORLEVEL% NEQ 0 (
    POPD
    ECHO.
    ECHO ************************************************************
    ECHO  DBC BUILD FAILED! Check errors above.
    ECHO ************************************************************
    EXIT /B 1
)
POPD

ECHO       DBC build succeeded.
:AFTER_DBC

REM ============================================================
REM  STEP 3.5: Build Interface (pack custom UI into patch-4.mpq)
REM ============================================================
IF "%SKIP_UI%"=="1" (
    ECHO.
    ECHO [3.5/5] Interface build SKIPPED ^(--skip-ui^)
    GOTO AFTER_UI
)

SET "UI_SCRIPT_DIR=%~dp0Interface"
SET "UI_SCRIPT=build_interface.py"

IF NOT EXIST "%UI_SCRIPT_DIR%\%UI_SCRIPT%" (
    ECHO.
    ECHO [3.5/5] build_interface.py not found, skipping UI build.
    GOTO AFTER_UI
)

ECHO.
ECHO [3.5/5] Building Interface (custom UI files)...

%PYTHON% "%UI_SCRIPT_DIR%\%UI_SCRIPT%"
IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO       WARNING: Interface build had errors. Continuing anyway.
)

ECHO       Interface build step done.
:AFTER_UI

REM ============================================================
REM  STEP 4: Copy patch-4.mpq to WoW client
REM ============================================================
IF "%SKIP_COPY%"=="1" (
    ECHO.
    ECHO [4/5] MPQ copy SKIPPED ^(--skip-copy^)
    GOTO AFTER_COPY
)

ECHO.
ECHO [4/5] Copying patch-4.mpq to WoW client...

IF NOT EXIST "%MPQ_OUTPUT%" (
    ECHO ERROR: patch-4.mpq not found at "%MPQ_OUTPUT%"
    ECHO        Run DBC build first.
    EXIT /B 1
)

COPY /Y "%MPQ_OUTPUT%" "%WOW_DATA%\patch-4.mpq" >NUL
IF %ERRORLEVEL% NEQ 0 (
    ECHO ERROR: Failed to copy patch-4.mpq to "%WOW_DATA%"
    EXIT /B 1
)

ECHO       Copied to: %WOW_DATA%\patch-4.mpq

REM Also deploy the patched DBCs to the server's DBC directory.
REM The server reads these too, not just the client -- Talent.dbc in
REM particular, where Flags=1 (addToSpellBook) is what makes
REM Player::LearnTalent actually call learnSpell() for talents we
REM redesigned from passives into active abilities.
SET "SERVER_DBC_DIR=%BUILD_DIR%\bin\%BUILD_CONFIG%\Data\dbc"
FOR %%D IN (Spell.dbc Talent.dbc SpellShapeshiftForm.dbc) DO (
    SET "PATCHED_DBC=%DBC_SCRIPT_DIR%\output\DBFilesClient\%%D"
    IF EXIST "!PATCHED_DBC!" (
        COPY /Y "!PATCHED_DBC!" "%SERVER_DBC_DIR%\%%D" >NUL
        IF !ERRORLEVEL! NEQ 0 (
            ECHO       WARNING: Failed to copy patched %%D to server DBC directory.
        ) ELSE (
            ECHO       Copied patched %%D to server.
        )
    )
)
:AFTER_COPY

REM ============================================================
REM  STEP 5: Start worldserver
REM ============================================================
IF "%SKIP_SERVER%"=="1" (
    ECHO.
    ECHO [5/5] Server start SKIPPED ^(--skip-server^)
    GOTO DONE
)

ECHO.
ECHO [5/5] Starting servers...

IF NOT EXIST "%SERVER_DIR%\authserver.exe" (
    ECHO ERROR: authserver.exe not found at "%SERVER_DIR%"
    EXIT /B 1
)
IF NOT EXIST "%SERVER_DIR%\worldserver.exe" (
    ECHO ERROR: worldserver.exe not found at "%SERVER_DIR%"
    EXIT /B 1
)

START "Authserver" /D "%SERVER_DIR%" "%SERVER_DIR%\authserver.exe"
ECHO       Authserver launched in new window.
START "Worldserver" /D "%SERVER_DIR%" "%SERVER_DIR%\worldserver.exe"
ECHO       Worldserver launched in new window.

IF "%SKIP_BRIDGE%"=="1" (
    ECHO       LLM chatter bridge SKIPPED ^(--skip-bridge^)
) ELSE IF EXIST "%LLM_BRIDGE_SCRIPT%" (
    IF EXIST "%LLM_BRIDGE_CONF%" (
        START "LLM Chatter Bridge" cmd /k %PYTHON% "%LLM_BRIDGE_SCRIPT%" --config "%LLM_BRIDGE_CONF%"
        ECHO       LLM chatter bridge launched in new window.
    ) ELSE (
        ECHO       LLM chatter bridge config not found, skipping.
    )
) ELSE (
    ECHO       LLM chatter bridge script not found, skipping.
)

REM ============================================================
REM  STEP 5.5: Post-start database verification
REM ============================================================
IF "%SKIP_VERIFY%"=="1" GOTO DONE
IF "%SKIP_SERVER%"=="1" GOTO DONE

IF EXIST "%VERIFY_DB_SCRIPT%" (
    ECHO.
    ECHO [5.5/5] Waiting for SQL auto-apply, then verifying database...
    timeout /t 8 /nobreak >NUL
    %PYTHON% "%VERIFY_DB_SCRIPT%"
) ELSE (
    ECHO.
    ECHO [5.5/5] verify_db.py not found, skipping database verification.
)

REM ============================================================
:DONE
ECHO.
ECHO ============================================================
ECHO  All steps completed successfully!
ECHO ============================================================
ECHO.
EXIT /B 0

REM ============================================================
:SHOW_HELP
ECHO.
ECHO Usage: build_and_run.bat [options]
ECHO.
ECHO Options:
ECHO   --skip-cmake    Skip CMake configure (reuses existing solution)
ECHO   --skip-build    Skip C++ MSBuild step (also skips CMake)
ECHO   --skip-dbc      Skip DBC build (build_dbc.py)
ECHO   --skip-ui       Skip Interface UI build (build_interface.py)
ECHO   --skip-copy     Skip copying patch-4.mpq to WoW client
ECHO   --skip-server   Skip launching worldserver
ECHO   --skip-verify   Skip pre-build consistency check and post-start DB verify
ECHO   --skip-bridge   Skip launching LLM chatter bridge
ECHO   --help          Show this help message
ECHO.
ECHO Examples:
ECHO   build_and_run.bat                        Full cycle (with verification)
ECHO   build_and_run.bat --skip-cmake           Build without re-running CMake
ECHO   build_and_run.bat --skip-build           DBC only + deploy + restart
ECHO   build_and_run.bat --skip-dbc --skip-copy Build C++ + restart server only
ECHO.
EXIT /B 0
