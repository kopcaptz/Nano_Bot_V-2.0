# Скрипт перезапуска Nano Bot V-2.0
# Останавливает все экземпляры и запускает один

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\kopca\OneDrive\Desktop\Cursor Ai\Nano_Bot_V-2.0"

Write-Host "Остановка всех экземпляров бота..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmd -like '*main.py*' -or $cmd -like '*nanobot*') {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  Stopped PID $($_.Id)" -ForegroundColor Gray
    }
}

Start-Sleep -Seconds 2

Write-Host "`nЗапуск бота (режим src/main.py с Gmail)..." -ForegroundColor Green
Set-Location $ProjectRoot
python src/main.py

# Если скрипт завершился (Ctrl+C), показать сообщение
Write-Host "`nБот остановлен." -ForegroundColor Red
