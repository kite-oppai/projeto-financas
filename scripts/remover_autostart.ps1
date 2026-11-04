[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param()
$ErrorActionPreference = 'Stop'
$TaskName = 'MinhasFinancas-Mobile'
Write-Host "Sera removida apenas a tarefa $TaskName."
Write-Host 'O aplicativo em execucao nao sera encerrado; nenhum banco, backup ou regra de Firewall sera removido.'
Write-Host 'Use a mesma conta que instalou a tarefa. Se houver acesso negado, execute como administrador dessa conta.'
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $Task) {
    Write-Host 'Tarefa nao encontrada; nada a remover.'
    exit 0
}
if ($PSCmdlet.ShouldProcess($TaskName, 'Remover tarefa de inicializacao')) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host 'Inicializacao automatica removida.'
}
