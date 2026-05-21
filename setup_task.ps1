# =============================================================================
# setup_task.ps1 — Registra tarefa agendada no Windows Task Scheduler
# para baixar o DOE-PE (Poder Executivo) diariamente.
#
# Execute UMA VEZ como Administrador:
#   powershell -ExecutionPolicy Bypass -File setup_task.ps1
#
# Parâmetros opcionais:
#   -Time     Horário de execução (padrão: 07:30)
#   -TaskName Nome da tarefa      (padrão: DOE-PE-Download-Diario)
#   -Remove   Remove a tarefa existente
# =============================================================================

param(
    [string]$Time     = "07:30",
    [string]$TaskName = "DOE-PE-Download-Diario",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# ── Caminho absoluto do projeto (onde este script está) ──────────────────────
$ProjectRoot = $PSScriptRoot

# ── Remove tarefa existente ──────────────────────────────────────────────────
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarefa '$TaskName' removida."
    exit 0
}

# ── Localiza o Python do ambiente atual ─────────────────────────────────────
try {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
} catch {
    Write-Error "Python nao encontrado no PATH. Instale o Python e tente novamente."
    exit 1
}

$Script  = Join-Path $ProjectRoot "src\downloader.py"
$LogFile = Join-Path $ProjectRoot "logs\downloader.log"

# Garante que a pasta de logs existe
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "logs") | Out-Null

if (-not (Test-Path $Script)) {
    Write-Error "Script nao encontrado: $Script"
    exit 1
}

Write-Host ""
Write-Host "Configuracao da tarefa:"
Write-Host "  Nome:       $TaskName"
Write-Host "  Python:     $PythonExe"
Write-Host "  Script:     $Script"
Write-Host "  Log:        $LogFile"
Write-Host "  Horario:    diariamente as $Time"
Write-Host "  Diretorio:  $ProjectRoot"
Write-Host ""

# ── Cria a tarefa ────────────────────────────────────────────────────────────
$Action = New-ScheduledTaskAction `
    -Execute    $PythonExe `
    -Argument   "`"$Script`" --log `"$LogFile`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit      (New-TimeSpan -Hours 1)   `
    -RestartCount            3                          `
    -RestartInterval         (New-TimeSpan -Minutes 15)`
    -StartWhenAvailable                                 `
    -RunOnlyIfNetworkAvailable                          `
    -MultipleInstances       IgnoreNew

# Registra — sobrescreve se já existir
Register-ScheduledTask `
    -TaskName   $TaskName `
    -Action     $Action   `
    -Trigger    $Trigger  `
    -Settings   $Settings `
    -Description "Baixa edicao diaria do Diario Oficial de Pernambuco (Poder Executivo)" `
    -RunLevel   Highest   `
    -Force | Out-Null

Write-Host "Tarefa '$TaskName' registrada com sucesso!"
Write-Host ""
Write-Host "Comandos uteis:"
Write-Host "  Executar agora:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Ver historico:   Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "  Ver log:         Get-Content '$LogFile' -Tail 50"
Write-Host "  Remover tarefa:  .\setup_task.ps1 -Remove"
Write-Host ""
Write-Host "Para baixar edicoes anteriores, execute no terminal:"
Write-Host "  python src\downloader.py --days 365"
