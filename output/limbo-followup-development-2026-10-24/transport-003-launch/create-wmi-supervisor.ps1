param([string]$RequestPath)
$ErrorActionPreference = 'Stop'
$r = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0; CreateFlags=[uint32]$r.creationflags}
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=[string]$r.command_line; CurrentDirectory=[string]$r.cwd; ProcessStartupInformation=$startup}
$json = @{ProcessId=$result.ProcessId; ReturnValue=$result.ReturnValue} | ConvertTo-Json
[System.IO.File]::WriteAllText([string]$r.result, $json, [System.Text.UTF8Encoding]::new($false))
if ($result.ReturnValue -ne 0) { exit 1 }
