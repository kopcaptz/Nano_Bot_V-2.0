# Create desktop shortcut for Nano Bot with icon

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "NanoBot Agent (Camilla, I'm here).lnk"
$TargetPath = "C:\Users\kopca\Desktop\Запуск NanoBot.bat"
$IconPath = "C:\Windows\System32\SHELL32.dll"
$IconIndex = 165  # Robot/AI icon in shell32.dll

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = "C:\Users\kopca\OneDrive\Desktop\Cursor Ai\Nano_Bot_V-2.0"
$Shortcut.Description = "Nano Bot V-2.0 Agent Mode - Tool-calling enabled"
$Shortcut.IconLocation = "$IconPath,$IconIndex"
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "Icon: Robot from shell32.dll" -ForegroundColor Gray
