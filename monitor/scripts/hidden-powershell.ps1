function Start-HiddenPowerShellFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = "",
        [switch]$STA,
        [switch]$Wait
    )

    if (-not (Test-Path $ScriptPath)) {
        throw "Script not found: $ScriptPath"
    }

    $argList = New-Object System.Collections.Generic.List[string]
    [void]$argList.Add("-NoProfile")
    if ($STA) { [void]$argList.Add("-STA") }
    [void]$argList.Add("-ExecutionPolicy")
    [void]$argList.Add("Bypass")
    [void]$argList.Add("-WindowStyle")
    [void]$argList.Add("Hidden")
    [void]$argList.Add("-File")
    [void]$argList.Add($ScriptPath)
    foreach ($item in $Arguments) {
        if ($null -ne $item -and "$item".Length -gt 0) {
            [void]$argList.Add([string]$item)
        }
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $psi.Arguments = [string]::Join(" ", ($argList | ForEach-Object {
        $text = [string]$_
        if ($text -match '[\s"]') { '"' + ($text -replace '"', '""') + '"' } else { $text }
    }))
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    if ($WorkingDirectory) {
        $psi.WorkingDirectory = $WorkingDirectory
    }

    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($null -eq $proc) {
        throw "Failed to start hidden PowerShell for $ScriptPath"
    }
    if ($Wait) {
        $proc.WaitForExit()
        return $proc
    }
    return $proc
}
