[CmdletBinding()]
param(
    [string]$CoreUrl = $env:JARVIS_CORE_URL,
    [string]$OwnerId = $env:JARVIS_OWNER_ID,
    [string]$IdentityId = $env:JARVIS_IDENTITY_ID,
    [string]$DeviceId = $env:JARVIS_NODE_ID,
    [string]$Credential = $env:JARVIS_SATELLITE_CREDENTIAL
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($setting in @{
    JARVIS_CORE_URL = $CoreUrl
    JARVIS_OWNER_ID = $OwnerId
    JARVIS_IDENTITY_ID = $IdentityId
    JARVIS_NODE_ID = $DeviceId
    JARVIS_SATELLITE_CREDENTIAL = $Credential
}.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace($setting.Value)) {
        throw "Missing required setting: $($setting.Key)"
    }
}

$env:JARVIS_CORE_URL = $CoreUrl
$env:JARVIS_OWNER_ID = $OwnerId
$env:JARVIS_IDENTITY_ID = $IdentityId
$env:JARVIS_NODE_ID = $DeviceId
$env:JARVIS_SATELLITE_CREDENTIAL = $Credential

python -m jarvis.satellite_agent
