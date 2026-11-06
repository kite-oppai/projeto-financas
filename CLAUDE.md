# Convenções do projeto

Aplicativo pessoal local em Python 3.11+, Streamlit, SQLite, Pandas e Plotly. Interface e documentação em português do Brasil. Veja `README.md` para instalação e uso.

## Comandos

Execute da raiz do repositório, preferencialmente com `.venv` ativado:

```bash
pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
python seed.py
python scripts/configurar_senha.py
python -m services.auth --check
python -m services.launcher
```

No Windows, `run_mobile.bat` executa com a `.venv` e mantém os logs. Instalar/remover autostart e liberar Firewall são ações manuais do usuário, não parte automática dos testes.

`seed.py` cria uma demonstração em `data/demo.db`; não popula a base pessoal. `FINANCAS_DB_PATH=data/demo.db streamlit run app.py` abre essa demonstração em shells POSIX. No PowerShell, atribua `$env:FINANCAS_DB_PATH` separadamente.

## Camadas

- `database/core.py`: conexão, integridade referencial e migrações transacionais por `PRAGMA user_version`.
- `services/`: validação e regras de negócio; recebe conexão SQLite explicitamente, sem dependência de Streamlit.
- `ui/`: apresentação, entradas, mensagens e navegação. Nenhum SQL ou cálculo de negócio nas páginas.
- `app.py`: autenticação, inicialização, geração de recorrências e navegação.
- `services/auth.py`, `backup.py`, `network.py` e `launcher.py`: acesso, cópia consistente, descoberta local de endereços e inicialização do servidor.
- `scripts/`: auxiliares de configuração Windows e senha; sem alterações automáticas no sistema durante testes.
- `tests/`: testes com bancos temporários, datas controladas e nenhuma dependência de dados reais.

Prefira funções pequenas e nomes claros a abstrações genéricas. Consulte as assinaturas atuais antes de mudar chamadas entre camadas.

## Interface e estilos

- Quatro áreas principais: **Resumo**, **Movimentos**, **Planejamento** e **Ajustes**. Mostre apenas a subseção ativa; preserve acesso a todos os recursos existentes.
- O Resumo mostra saldo do mês, receitas, despesas, um gráfico por categoria e cinco lançamentos. Análises adicionais só são renderizadas ao ativar **Ver detalhes**.
- `ui/styles.css` centraliza os tokens e estilos locais; `ui/styles.py` aplica o tema e `ui/shell.py` cuida da navegação e competência. Não espalhe folhas CSS pelas páginas.
- Vidro/translucidez apenas em superfícies flutuantes ou de destaque, como navegação, saldo principal, login e diálogos. Conteúdo e formulários devem ter boa legibilidade. Inclua fallback sólido e `prefers-reduced-motion`.
- Use seletores estáveis (classes próprias, chaves `st.container` e atributos semânticos do Streamlit); evite classes geradas aleatoriamente. Não esconda controles de erro, acessibilidade ou segurança por CSS.
- Priorize controles nativos. A navegação horizontal responsiva fica no fluxo da página para não cobrir conteúdo em telas pequenas. Mantenha foco visível, rótulos e áreas confortáveis de toque.
- Cadastros/edições de lançamentos usam `st.dialog` com cancelamento explícito e rerun completo após sucesso. Cada execução de fragmento deve revalidar login e abrir/fechar sua própria conexão: não reutilize a conexão que `app.py` encerrou.
- Valores e descrições de usuários inseridos em HTML de apresentação devem ser escapados. Nenhum HTML fornecido pelo usuário pode ser renderizado diretamente.
- Não mude regras, esquema SQLite, autenticação, backup ou rede para resolver um problema de layout.

## Dinheiro e datas

- Toda persistência e soma monetária usa **centavos inteiros**. Nunca crie dinheiro com `float`, inclusive entradas de formulário, importação ou dados de demonstração.
- Use `services.money.parse_money` na entrada e `format_money` na saída. `Decimal` só na conversão; não arredonde silenciosamente frações de centavo.
- Valores de lançamento são positivos; `type` é `receita` ou `despesa`. Saldos e diferenças podem ser negativos.
- Datas são ISO `AAAA-MM-DD` no banco e `dd/mm/aaaa` na interface. Competências e orçamentos usam `AAAA-MM`.
- Gráficos devem conservar centavos nos dados e formatar rótulos/hover em reais; porcentagens visuais podem usar proporções sem contaminar cálculos monetários.

## Decisões do MVP

- Saldo de conta: saldo inicial + receitas − despesas de todos os lançamentos nela, inclusive futuros cadastrados. Dashboard mensal não incorpora saldo inicial.
- Cartão: despesa integral na data da compra; saldo negativo é dívida. Sem faturas, fechamento, vencimento, parcelamento ou transferências entre contas.
- Categorias e contas referenciadas não são excluídas silenciosamente; peça ao usuário que resolva as referências.
- Orçamento por categoria/mês: aviso em 80%; atingido/excedido em 100%. Gastos de outras competências não entram no cálculo.
- Recorrências: geração na abertura/atualização, recuperação de competências vencidas pendentes, último dia válido nos meses curtos e idempotência por regra/mês. Reativar recupera também os meses da pausa; um mês final encerra a obrigação. Alterar regra não reescreve lançamentos anteriores. Preserve o controle de geração ao remover um lançamento recorrente para não recriá-lo inesperadamente.
- Metas: aportes manuais independentes das contas; não movimentam saldo nem criam lançamentos.
- Importação: mapeamento explícito, prévia antes de gravar, validação por linha e detecção de duplicatas. Não persista parcialmente arquivos inválidos sem decisão explícita.

## Segurança e privacidade

Os dados financeiros permanecem no PC. Acesso por navegador é permitido apenas pela LAN confiável ou pela rede privada Tailscale, com login obrigatório. Não adicione APIs, analytics, fontes remotas, CDNs ou envio de dados a serviços externos. Nunca use Tailscale Funnel, ngrok, encaminhamento de portas no roteador ou hospedagem pública.

Mantenha `server.address="0.0.0.0"`, `server.port=8501`, `server.headless=true` e `browser.gatherUsageStats=false`. A escuta em todas as interfaces precisa da regra de Firewall restrita: TCP8501, perfil Privado e origens LAN/Tailscale. Não transforme redes ou adaptadores em Privados automaticamente nem amplie para perfil Público. O adaptador Tailscale pode ter perfil Público e exigir diagnóstico/configuração manual deliberada.

A autenticação vem antes de navegação, consultas financeiras e exportações. Hash bcrypt em `.streamlit/secrets.toml`, seção `[auth]`, chave `password_hash`; senha ausente ou hash inválido bloqueia acesso. Não implemente um modo sem login. Sessão expira após 30 minutos sem interação; cinco falhas em um minuto provocam espera compartilhada por processo. Trocar o hash invalida sessões antigas na próxima interação. Senhas são solicitadas interativamente via `scripts/configurar_senha.py`, sem argumentos ou persistência de texto puro. Logout deve limpar os dados financeiros e autorizações da sessão. Não registre senha, hash ou extratos em logs.

`run_mobile.bat`/`.ps1` usam a `.venv`, mostram os endereços, registram saída em `logs/app.log` e esperam o processo terminar. Preserve o código de saída para o reinício do Agendador. A tarefa `MinhasFinancas-Mobile` executa no logon do usuário, não antes de entrar no Windows, com privilégio limitado e sem senha Windows armazenada. A regra de Firewall do projeto chama-se `MinhasFinancas-Mobile-8501`. Não execute scripts que alterem Firewall ou Agendador sem autorização explícita; apenas criar os arquivos não instala nada. Scripts devem explicar efeitos e privilégios necessários, apoiar `-WhatIf` e não tentar elevar privilégios sozinhos.

Backups usam a API consistente do SQLite, antes das migrações/recorrências, uma vez por processo; conservar sete cópias por banco e não criar cópias em cada rerun. O launcher faz backup antes de iniciar o servidor; a execução direta do Streamlit só executa o app na primeira sessão do navegador. Falhas de backup não devem provocar sobrescrita ou descarte do banco original. Nunca use uma cópia simples do arquivo aberto como implementação de backup automático.

Nunca versione bancos, extratos, planilhas, `.env`, segredos nem backups. Use bancos temporários nos testes. Não mostre conteúdo financeiro em logs de depuração. SQL deve usar parâmetros, e erros apresentados ao usuário devem ser claros, sem traceback ou exposição de caminhos internos desnecessários.

Migrações novas devem preservar dados e incrementar a versão. Faça backup com o aplicativo encerrado antes de testar uma migração em dados reais. Não apague o banco para resolver incompatibilidades.

## Verificação

Implemente em etapas pequenas; execute os testes afetados ao final de cada uma e a suíte completa antes de entregar. Cubra regras com resultados financeiros exatos, casos inválidos, limites de mês e idempotência. Teste também login negado/correto, logout, proteção das páginas/exportações, backup e retenção, IPs ausentes e Tailscale não instalado. Use mocks para comandos Windows nos testes; nunca execute comandos de alteração do sistema como teste. Declare separadamente o que foi validado no Linux e o que exige checklist no Windows/celular. Mudanças na interface precisam de verificação manual ou `streamlit.testing.v1.AppTest`, sem reutilizar dados pessoais.

O AppTest do Streamlit 1.50 pode manter nós de widgets removidos após reruns internos, incluindo diálogos fechados e confirmações de importação. Nesses pontos, os testes verificam o estado descartado e os valores persistidos antes de abrir uma nova sessão autenticada. Valide também o fechamento/reabertura na mesma sessão em um navegador; não altere regras ou mantenha formulários visíveis apenas para contornar limitações do executor de testes.

Cada tarefa na nuvem já possui ambiente isolado: use o checkout existente. Não crie `git worktree` sem solicitação explícita do usuário.
