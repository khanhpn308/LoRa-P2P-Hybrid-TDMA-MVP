param(
    [string]$Compiler = 'gcc',
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
$taskExe = Join-Path $taskOutput 'event-input-tests.exe'
& $Compiler -std=c99 -Wall -Wextra -Werror -pedantic "-I$taskRoot/components/event_input/include" "$taskRoot/components/event_input/event_input.c" "$PSScriptRoot/test_event_input.c" -o $taskExe
if ($LASTEXITCODE -ne 0) { throw 'Host compilation failed' }
& $taskExe
if ($LASTEXITCODE -ne 0) { throw 'Host tests failed' }
