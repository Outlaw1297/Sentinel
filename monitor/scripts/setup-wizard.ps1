# WinForms first-run setup wizard for Sentinel monitor.

param()

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptsDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $ScriptsDir
$ConfigPath = Join-Path $MonitorRoot "config.json"
$ExamplePath = Join-Path $MonitorRoot "config.example.json"
$EnsureTasksScript = Join-Path $ScriptsDir "ensure-elevated-tasks.ps1"
$StartBat = Join-Path $MonitorRoot "StartGnBotStack.bat"
$SentinelExe = Join-Path $MonitorRoot "Sentinel.exe"
$SetupBat = Join-Path $MonitorRoot "Setup Wizard.bat"

function Read-ConfigJson {
    if (Test-Path $ConfigPath) {
        return Get-Content $ConfigPath -Raw | ConvertFrom-Json
    }
    if (Test-Path $ExamplePath) {
        return Get-Content $ExamplePath -Raw | ConvertFrom-Json
    }
    return [pscustomobject]@{}
}

function Save-ConfigJson([hashtable]$Values) {
    $data = @{}
    if (Test-Path $ConfigPath) {
        $existing = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        $existing.PSObject.Properties | ForEach-Object { $data[$_.Name] = $_.Value }
    } elseif (Test-Path $ExamplePath) {
        $existing = Get-Content $ExamplePath -Raw | ConvertFrom-Json
        $existing.PSObject.Properties | ForEach-Object { $data[$_.Name] = $_.Value }
    }
    foreach ($key in $Values.Keys) {
        $data[$key] = $Values[$key]
    }
    $data["setup_complete"] = $true
    $data | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Test-PortFree([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    return -not $conn
}

function New-Label([string]$Text, [int]$Top) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.AutoSize = $true
    $label.Location = New-Object System.Drawing.Point 24, $Top
    $label.MaximumSize = New-Object System.Drawing.Size 520, 0
    return $label
}

function New-TextBox([string]$Value, [int]$Top, [int]$Width = 500) {
    $box = New-Object System.Windows.Forms.TextBox
    $box.Text = $Value
    $box.Location = New-Object System.Drawing.Point 24, ($Top + 22)
    $box.Width = $Width
    return $box
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Sentinel Setup Wizard"
$form.Size = New-Object System.Drawing.Size 580, 520
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false

$panel = New-Object System.Windows.Forms.Panel
$panel.Dock = "Fill"
$form.Controls.Add($panel)

$btnBack = New-Object System.Windows.Forms.Button
$btnBack.Text = "Back"
$btnBack.Location = New-Object System.Drawing.Point 300, 430
$btnBack.Width = 80
$btnBack.Enabled = $false

$btnNext = New-Object System.Windows.Forms.Button
$btnNext.Text = "Next"
$btnNext.Location = New-Object System.Drawing.Point 390, 430
$btnNext.Width = 80

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Text = "Cancel"
$btnCancel.Location = New-Object System.Drawing.Point 480, 430
$btnCancel.Width = 80
$btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

$panel.Controls.AddRange(@($btnBack, $btnNext, $btnCancel))

$config = Read-ConfigJson
$step = 1
$gnbotsExe = [string]($config.gnbots_exe)
$gnbotsRoot = [string]($config.gnbots_root)
$ldPath = [string]($config.ldplayer_path)
$backupsDir = [string]($config.ldplayer_backups_dir)
$desktopShortcut = $true
$startWithWindows = $false
$registerTasks = $false
$port = if ($config.dashboard_port) { [int]$config.dashboard_port } else { 8787 }

$controls = New-Object System.Collections.Generic.List[System.Windows.Forms.Control]

function Clear-Panel {
    foreach ($ctrl in $controls) {
        $panel.Controls.Remove($ctrl)
    }
    $controls.Clear()
}

function Show-Step {
    Clear-Panel
    switch ($script:step) {
        1 {
            $controls.Add((New-Label "Welcome to Sentinel" 24))
            $controls.Add((New-Label "This wizard configures GnBots paths, optional LDPlayer folders, and startup shortcuts." 56))
            $controls.Add((New-Label "Install folder: $MonitorRoot" 120))
            $btnBack.Enabled = $false
            $btnNext.Text = "Get started"
        }
        2 {
            $controls.Add((New-Label "Monitor install folder" 24))
            $box = New-TextBox $MonitorRoot 56
            $box.ReadOnly = $true
            $controls.Add($box)
            $btnBack.Enabled = $true
            $btnNext.Text = "Next"
        }
        3 {
            $controls.Add((New-Label "Select GnBots.exe" 24))
            $exeBox = New-TextBox $script:gnbotsExe 56 420
            $controls.Add($exeBox)
            $browse = New-Object System.Windows.Forms.Button
            $browse.Text = "Browse…"
            $browse.Location = New-Object System.Drawing.Point 450, 78
            $browse.Add_Click({
                $dlg = New-Object System.Windows.Forms.OpenFileDialog
                $dlg.Filter = "GnBots.exe|GnBots.exe|Executables (*.exe)|*.exe"
                if ($dlg.ShowDialog() -eq "OK") {
                    $exeBox.Text = $dlg.FileName
                    $script:gnbotsRoot = Split-Path -Parent $dlg.FileName
                }
            })
            $controls.Add($browse)
            $btnNext.Text = "Next"
        }
        4 {
            $controls.Add((New-Label "LDPlayer install (optional — leave blank to use GnBots config)" 24))
            $ldBox = New-TextBox $script:ldPath 56 420
            $controls.Add($ldBox)
            $browse = New-Object System.Windows.Forms.Button
            $browse.Text = "Browse…"
            $browse.Location = New-Object System.Drawing.Point 450, 78
            $browse.Add_Click({
                $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
                if ($dlg.ShowDialog() -eq "OK") { $ldBox.Text = $dlg.SelectedPath }
            })
            $controls.Add($browse)
            $btnNext.Text = "Next"
        }
        5 {
            $controls.Add((New-Label "LDPlayer backup folder (.ldbk) — optional" 24))
            $bakBox = New-TextBox $script:backupsDir 56 420
            $controls.Add($bakBox)
            $browse = New-Object System.Windows.Forms.Button
            $browse.Text = "Browse…"
            $browse.Location = New-Object System.Drawing.Point 450, 78
            $browse.Add_Click({
                $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
                if ($dlg.ShowDialog() -eq "OK") { $bakBox.Text = $dlg.SelectedPath }
            })
            $controls.Add($browse)
            $btnNext.Text = "Next"
        }
        6 {
            $controls.Add((New-Label "Optional shortcuts and tasks" 24))
            $chkDesktop = New-Object System.Windows.Forms.CheckBox
            $chkDesktop.Text = "Create desktop shortcut to Sentinel"
            $chkDesktop.Checked = $script:desktopShortcut
            $chkDesktop.Location = New-Object System.Drawing.Point 24, 60
            $chkDesktop.AutoSize = $true
            $controls.Add($chkDesktop)
            $chkStartup = New-Object System.Windows.Forms.CheckBox
            $chkStartup.Text = "Start watcher with Windows logon"
            $chkStartup.Checked = $script:startWithWindows
            $chkStartup.Location = New-Object System.Drawing.Point 24, 92
            $chkStartup.AutoSize = $true
            $controls.Add($chkStartup)
            $chkTasks = New-Object System.Windows.Forms.CheckBox
            $chkTasks.Text = "Register elevated GnBots tasks (UAC prompt)"
            $chkTasks.Checked = $script:registerTasks
            $chkTasks.Location = New-Object System.Drawing.Point 24, 124
            $chkTasks.AutoSize = $true
            $controls.Add($chkTasks)
            $btnNext.Text = "Next"
        }
        7 {
            $controls.Add((New-Label "Ready to finish" 24))
            $controls.Add((New-Label "Sentinel will write config.json, optionally register tasks, and start the stack." 56))
            $btnNext.Text = "Finish"
        }
    }
    $panel.Controls.AddRange($controls.ToArray())
}

$btnNext.Add_Click({
    if ($script:step -eq 3) {
        $exeBox = $panel.Controls | Where-Object { $_ -is [System.Windows.Forms.TextBox] } | Select-Object -First 1
        $script:gnbotsExe = [string]$exeBox.Text.Trim()
        if (-not (Test-Path $script:gnbotsExe)) {
            [System.Windows.Forms.MessageBox]::Show("GnBots.exe was not found.", "Validation", "OK", "Warning") | Out-Null
            return
        }
        $script:gnbotsRoot = Split-Path -Parent $script:gnbotsExe
    }
    if ($script:step -eq 4) {
        $ldBox = $panel.Controls | Where-Object { $_ -is [System.Windows.Forms.TextBox] } | Select-Object -First 1
        $script:ldPath = [string]$ldBox.Text.Trim()
    }
    if ($script:step -eq 5) {
        $bakBox = $panel.Controls | Where-Object { $_ -is [System.Windows.Forms.TextBox] } | Select-Object -First 1
        $script:backupsDir = [string]$bakBox.Text.Trim()
    }
    if ($script:step -eq 6) {
        $checks = $panel.Controls | Where-Object { $_ -is [System.Windows.Forms.CheckBox] }
        $script:desktopShortcut = $checks[0].Checked
        $script:startWithWindows = $checks[1].Checked
        $script:registerTasks = $checks[2].Checked
    }
    if ($script:step -eq 7) {
        if (-not (Test-PortFree $script:port)) {
            $answer = [System.Windows.Forms.MessageBox]::Show(
                "Port $($script:port) is in use. Continue anyway?",
                "Port in use",
                "YesNo",
                "Warning"
            )
            if ($answer -ne "Yes") { return }
        }
        Save-ConfigJson @{
            gnbots_exe = $script:gnbotsExe
            gnbots_root = $script:gnbotsRoot
            ldplayer_path = $script:ldPath
            ldplayer_backups_dir = $script:backupsDir
        }
        if ($script:registerTasks -and (Test-Path $EnsureTasksScript)) {
            Start-Process powershell.exe -Verb RunAs -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$EnsureTasksScript`"", "-Quiet"
            ) -Wait
        }
        if ($script:desktopShortcut) {
            $launcher = if (Test-Path $SentinelExe) { $SentinelExe } elseif (Test-Path $StartBat) { $StartBat } else { $null }
            if ($launcher) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut((Join-Path $env:USERPROFILE "Desktop\Sentinel.lnk"))
            $shortcut.TargetPath = $launcher
            $shortcut.WorkingDirectory = $MonitorRoot
            $shortcut.Description = "Start Sentinel stack and open dashboard"
            $shortcut.Save()
            }
        }
        if ($script:startWithWindows) {
            $watcherVbs = Join-Path ([Environment]::GetFolderPath("Startup")) "GnBotsMonitorWatcher.vbs"
            $watcherScript = Join-Path $ScriptsDir "stack-watcher.ps1"
            @"
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$watcherScript""", 0, False
"@ | Set-Content -Path $watcherVbs -Encoding ASCII
        }
        if (Test-Path $SentinelExe) {
            Start-Process -FilePath $SentinelExe -WorkingDirectory $MonitorRoot
        } elseif (Test-Path $StartBat) {
            Start-Process -FilePath $StartBat -WorkingDirectory $MonitorRoot
        }
        Start-Process "http://127.0.0.1:$($script:port)/"
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
        return
    }
    $script:step++
    Show-Step
})

$btnBack.Add_Click({
    if ($script:step -le 1) { return }
    $script:step--
    Show-Step
})

$form.Add_Shown({ Show-Step })
[void]$form.ShowDialog()
exit 0
