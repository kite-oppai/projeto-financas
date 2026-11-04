# Executar manualmente em PowerShell como administrador. Nao altera perfis.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param()
$ErrorActionPreference = 'Stop'
$RuleName = 'MinhasFinancas-Mobile-8501'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$IsAdmin = ([Security.Principal.WindowsPrincipal]$Identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host 'Sera criada/atualizada UMA regra de entrada para TCP 8501.'
Write-Host 'Somente perfil PRIVADO; origens Tailscale 100.64.0.0/10 e sub-redes LAN privadas identificadas.'
Write-Host 'Nao permite perfil Publico, nao muda categoria de redes e nao altera o roteador.'
Write-Host "Para desfazer: Remove-NetFirewallRule -Name '$RuleName' (como administrador)."
if (-not $IsAdmin -and -not $WhatIfPreference) {
    throw 'Este script precisa de PowerShell executado como administrador. Nada foi alterado.'
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Python da .venv nao encontrado. Crie o ambiente virtual e instale as dependencias primeiro.'
}
# Uma regra de permissao restrita so protege o servidor se as demais origens
# forem bloqueadas pelo Firewall efetivo. Consulta apenas; nunca muda politica.
try {
    $EffectiveProfiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore)
} catch {
    throw 'Nao foi possivel consultar a politica efetiva do Firewall. Nao inicie o app em 0.0.0.0 antes de revisar o Firewall; nenhuma regra foi alterada.'
}
foreach ($ProfileName in @('Domain', 'Private', 'Public')) {
    $Effective = @($EffectiveProfiles | Where-Object { $_.Name -eq $ProfileName })
    if ($Effective.Count -ne 1) {
        throw "Nao foi possivel confirmar o perfil efetivo $ProfileName. Nenhuma regra foi alterada. Revise a politica do Firewall antes de expor o app na rede."
    }
    if ([string]$Effective[0].Enabled -ne 'True') {
        throw "O Firewall do perfil $ProfileName esta desativado ou indeterminado. Uma regra restrita nao protege o app em 0.0.0.0 nesse caso. Revise a configuracao com o administrador; nada foi alterado."
    }
    if ([string]$Effective[0].DefaultInboundAction -ne 'Block') {
        throw "O perfil $ProfileName nao confirma bloqueio padrao de entrada (Block). Allow/NotConfigured nao permitem confirmar a restricao. Revise a politica efetiva com o administrador; nada foi alterado."
    }
}
$Profiles = @(Get-NetConnectionProfile)
foreach ($Profile in $Profiles) {
    if ($Profile.InterfaceAlias -match 'Tailscale' -and $Profile.NetworkCategory -ne 'Private') {
        Write-Warning 'O adaptador Tailscale nao esta no perfil Privado. Esta regra pode nao permitir acesso pela VPN. Confira o README; nenhum perfil sera alterado automaticamente.'
    }
}
$TailscaleAdapters = @(Get-NetAdapter | Where-Object { $_.Name -match 'Tailscale' -or $_.InterfaceDescription -match 'Tailscale' })
foreach ($Adapter in $TailscaleAdapters) {
    if (-not @($Profiles | Where-Object { $_.InterfaceIndex -eq $Adapter.InterfaceIndex })) {
        Write-Warning 'Existe um adaptador Tailscale sem perfil de conexao identificavel. Nao foi possivel confirmar a aplicacao da regra Privada a VPN. Revise o perfil manualmente; nenhum perfil sera alterado.'
    }
}
$RemoteRanges = @('100.64.0.0/10')
foreach ($Configuration in Get-NetIPConfiguration) {
    if (-not $Configuration.IPv4DefaultGateway) { continue }
    $PrivateProfile = @($Profiles | Where-Object { $_.InterfaceIndex -eq $Configuration.InterfaceIndex -and $_.NetworkCategory -eq 'Private' })
    if (-not $PrivateProfile) { continue }
    foreach ($Address in Get-NetIPAddress -InterfaceIndex $Configuration.InterfaceIndex -AddressFamily IPv4) {
        if ($Address.AddressState -ne 'Preferred') { continue }
        if ($Address.IPAddress -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)') { continue }
        $Prefix = [int]$Address.PrefixLength
        # Recusa prefixos que poderiam incluir a internet por erro de configuracao.
        $Minimum = if ($Address.IPAddress.StartsWith('10.')) { 8 } elseif ($Address.IPAddress.StartsWith('172.')) { 12 } else { 16 }
        if ($Prefix -lt $Minimum) {
            Write-Warning 'Prefixo LAN amplo demais; interface ignorada. Revise a configuracao de rede.'
            continue
        }
        $Octets = [System.Net.IPAddress]::Parse($Address.IPAddress).GetAddressBytes()
        for ($Index = 0; $Index -lt 4; $Index++) {
            $Bits = [Math]::Max(0, [Math]::Min(8, $Prefix - $Index * 8))
            $Mask = [int](256 - [Math]::Pow(2, 8 - $Bits))
            $Octets[$Index] = [byte]($Octets[$Index] -band $Mask)
        }
        $NetworkAddress = New-Object System.Net.IPAddress -ArgumentList (, $Octets)
        $RemoteRanges += "$($NetworkAddress.ToString())/$Prefix"
    }
}
$RemoteRanges = @($RemoteRanges | Sort-Object -Unique)
if ($RemoteRanges.Count -eq 1) {
    Write-Warning 'Nenhuma LAN em perfil Privado foi identificada. A regra tera apenas o intervalo Tailscale; confira a rede Wi-Fi/cabo antes de tentar acesso local.'
}
Write-Host ('Origens permitidas: ' + ($RemoteRanges -join ', '))
# Uma regra restrita NAO neutraliza regras amplas que ja estejam habilitadas.
$OtherRules = @(Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | Where-Object { $_.Name -ne $RuleName })
foreach ($Rule in $OtherRules) {
    $PortFilter = $Rule | Get-NetFirewallPortFilter
    $AppFilter = $Rule | Get-NetFirewallApplicationFilter
    $IncludesPort = $false
    foreach ($PortSpec in @($PortFilter.LocalPort)) {
        $PortText = [string]$PortSpec
        if ($PortText -eq 'Any' -or $PortText -eq '8501') { $IncludesPort = $true }
        elseif ($PortText -match '^(\d+)-(\d+)$') {
            if ([int]$Matches[1] -le 8501 -and [int]$Matches[2] -ge 8501) { $IncludesPort = $true }
        }
    }
    if (($PortFilter.Protocol -eq 'TCP' -or $PortFilter.Protocol -eq 'Any') -and
        $IncludesPort -and
        ($AppFilter.Program -eq 'Any' -or $AppFilter.Program -match '(?i)python(?:w)?\.exe$')) {
        Write-Warning "Existe outra regra possivelmente aplicavel ao Python/8501: $($Rule.DisplayName) [$($Rule.Name)]. Revise-a no Firewall; ela pode permitir mais acesso que esta regra. Ela nao sera modificada."
    }
}
if ($PSCmdlet.ShouldProcess("$RuleName; Privado; TCP 8501; $($RemoteRanges -join ', ')", 'Criar/atualizar regra restrita de Firewall')) {
    $Existing = Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue
    if ($Existing) { Remove-NetFirewallRule -Name $RuleName -Confirm:$false }
    New-NetFirewallRule -Name $RuleName -DisplayName 'Minhas Financas - LAN e Tailscale - TCP 8501' -Description 'Somente perfil Privado, LAN detectada e intervalo Tailscale; sem acesso publico.' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 -Profile Private -RemoteAddress $RemoteRanges -EdgeTraversalPolicy Block | Out-Null
    Write-Host 'Regra criada. Teste pelo celular e revise outras regras existentes antes de considerar o acesso restrito.'
}
