# Executar como usuario comum. Nao altera Firewall, energia nem tarefas.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host 'ERRO: ambiente virtual nao encontrado. Execute py -m venv .venv e instale requirements.txt.' -ForegroundColor Red
    exit 1
}
# Usa o interpretador da .venv diretamente, sem depender de Activate.ps1.
$env:VIRTUAL_ENV = Join-Path $ProjectRoot '.venv'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + ';' + $env:PATH
$env:PYTHONUNBUFFERED = '1'
$LogDirectory = Join-Path $ProjectRoot 'logs'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogPath = Join-Path $LogDirectory 'app.log'
# Rotaciona na inicializacao a partir de 5 MB; mantem ate quatro historicos.
if ((Test-Path -LiteralPath $LogPath) -and (Get-Item -LiteralPath $LogPath).Length -ge 5MB) {
    for ($index = 4; $index -ge 1; $index--) {
        $Previous = if ($index -eq 1) { $LogPath } else { "$LogPath.$($index - 1)" }
        if (Test-Path -LiteralPath $Previous) {
            Move-Item -LiteralPath $Previous -Destination "$LogPath.$index" -Force
        }
    }
}
"`r`n=== Inicio $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Tee-Object -FilePath $LogPath -Append
try {
    # Erros de programas nativos devem chegar ao log e preservar o codigo de saida.
    $ErrorActionPreference = 'Continue'
    & $Python -m services.auth --check 2>&1 | Tee-Object -FilePath $LogPath -Append
    $AuthExit = $LASTEXITCODE
    if ($AuthExit -ne 0) {
        'Configure a senha primeiro: .\.venv\Scripts\python.exe scripts\configurar_senha.py' | Tee-Object -FilePath $LogPath -Append
        exit $AuthExit
    }
    & $Python -m services.network 2>&1 | Tee-Object -FilePath $LogPath -Append
    'Iniciando o app na porta 8501. Para encerrar nesta janela: Ctrl+C.' | Tee-Object -FilePath $LogPath -Append
    # services.launcher faz backup antes de iniciar o Streamlit; espera ate ele terminar.
    & $Python -m services.launcher 2>&1 | Tee-Object -FilePath $LogPath -Append
    $AppExit = $LASTEXITCODE
    "Aplicativo encerrado com codigo $AppExit." | Tee-Object -FilePath $LogPath -Append
    exit $AppExit
} catch {
    # Nao registrar valores de senha ou dados financeiros.
    'Falha ao iniciar o aplicativo. Confira a .venv, a configuracao da senha e permissoes da pasta.' | Tee-Object -FilePath $LogPath -Append
    exit 1
}
