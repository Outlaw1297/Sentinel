$log = "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot20260625.txt"
Select-String -Path $log -Pattern "Snuffles|Starting Emulator" | Select-Object -Last 10 | ForEach-Object { $_.Line }
