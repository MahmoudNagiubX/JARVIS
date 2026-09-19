<#!
.SYNOPSIS
    Run one JARVIS cloud-provider acceptance probe without persisting an API key.

.DESCRIPTION
    Prompts for one owner secret as a SecureString, places it only in this
    PowerShell process environment, runs the bounded JARVIS provider probe, and
    removes the environment value before exiting. The key is never accepted as
    a command-line argument, written to .env, or printed by this helper.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('groq', 'gemini')]
    [string]$Provider
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$environmentName = if ($Provider -eq 'groq') { 'GROQ_API_KEY' } else { 'GEMINI_API_KEY' }
$enabledName = if ($Provider -eq 'groq') { 'JARVIS_GROQ_ENABLED' } else { 'JARVIS_GEMINI_ENABLED' }
$secret = Read-Host -Prompt ("Enter {0} API key (input is hidden; it will not be saved)" -f $Provider) -AsSecureString
$pointer = [IntPtr]::Zero
$plain = $null
$repoRoot = Split-Path -Parent $PSScriptRoot

try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plain)) {
        throw 'An API key is required for this provider probe.'
    }

    [Environment]::SetEnvironmentVariable('JARVIS_MODEL_PROVIDER', 'hybrid', 'Process')
    [Environment]::SetEnvironmentVariable($enabledName, 'true', 'Process')
    [Environment]::SetEnvironmentVariable($environmentName, $plain, 'Process')
    Push-Location $repoRoot
    try {
        & python -m jarvis --model-provider-probe $Provider
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    [Environment]::SetEnvironmentVariable($environmentName, $null, 'Process')
    [Environment]::SetEnvironmentVariable($enabledName, $null, 'Process')
    [Environment]::SetEnvironmentVariable('JARVIS_MODEL_PROVIDER', $null, 'Process')
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $plain = $null
    $secret = $null
}
