$log = "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot20260625.txt"
Select-String -Path $log -Pattern "Pausing bot|Stopping bot|Starting bot" | Select-Object -Last 8 | ForEach-Object { $_.Line }
