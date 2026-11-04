# Cria uma tarefa apenas quando este arquivo for executado manualmente.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param()
$ErrorActionPreference = 'Stop'
$TaskName = 'MinhasFinancas-Mobile'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $ProjectRoot 'run_mobile.bat'
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$User = $Identity.Name
$IsAdmin = ([Security.Principal.WindowsPrincipal]$Identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "Sera criada/atualizada a tarefa $TaskName para $User."
Write-Host 'Ela iniciara no LOGON (depois de entrar no Windows), em janela oculta, sem senha salva.'
Write-Host 'O app roda como usuario comum. A tarefa tenta reiniciar a cada minuto, ate 3 vezes, em caso de falha.'
Write-Host 'Nao altera Firewall, Tailscale ou opcoes de energia. Nao abre portas no roteador.'
if (-not $IsAdmin) {
    Write-Host 'Tentativa como usuario comum. Se o Windows negar acesso ao Agendador, execute este script como administrador da MESMA conta.'
}
if (-not (Test-Path -LiteralPath $Runner) -or -not (Test-Path -LiteralPath $Python)) {
    throw 'run_mobile.bat ou .venv ausente. Prepare o projeto e suas dependencias primeiro.'
}
if ($PSCmdlet.ShouldProcess("$TaskName ($User)", 'Registrar tarefa de inicializacao no logon')) {
    # Apostrofos no caminho sao escapados para o comando PowerShell.
    $EscapedRunner = $Runner.Replace("'", "''")
    $Arguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -Command "& ''' + $EscapedRunner + '''; exit $LASTEXITCODE"'
    $Action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $Arguments -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
    $Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Financas pessoais via LAN/Tailscale. Executa apenas apos logon do usuario.' -Force | Out-Null
    } catch {
        throw 'Nao foi possivel registrar a tarefa. Confira permissoes/politicas do Windows; se necessario, use PowerShell como administrador da mesma conta.'
    }
    Write-Host 'Tarefa registrada. Ela nao foi iniciada agora; teste o app manualmente antes do proximo logon.'
}
