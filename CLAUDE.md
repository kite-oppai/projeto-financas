# Convenções do projeto

Aplicativo pessoal local em Python 3.11+, Streamlit, SQLite, Pandas e Plotly. Interface e documentação em português do Brasil. Veja `README.md` para instalação e uso.

## Comandos

Execute da raiz do repositório, preferencialmente com `.venv` ativado:

```bash
pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
python seed.py
```

`seed.py` cria uma demonstração em `data/demo.db`; não popula a base pessoal. `FINANCAS_DB_PATH=data/demo.db streamlit run app.py` abre essa demonstração em shells POSIX. No PowerShell, atribua `$env:FINANCAS_DB_PATH` separadamente.

## Camadas

- `database/core.py`: conexão, integridade referencial e migrações transacionais por `PRAGMA user_version`.
- `services/`: validação e regras de negócio; recebe conexão SQLite explicitamente, sem dependência de Streamlit.
- `ui/`: apresentação, entradas, mensagens e navegação. Nenhum SQL ou cálculo de negócio nas páginas.
- `app.py`: inicialização, geração de recorrências e navegação.
- `tests/`: testes com bancos temporários, datas controladas e nenhuma dependência de dados reais.

Prefira funções pequenas e nomes claros a abstrações genéricas. Consulte as assinaturas atuais antes de mudar chamadas entre camadas.

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

Tudo financeiro permanece local. Não adicione APIs, analytics, fontes remotas, CDNs, bibliotecas que enviem telemetria ou upload de dados sem autorização explícita. Mantenha `browser.gatherUsageStats=false` e `server.address="127.0.0.1"` em `.streamlit/config.toml`.

Nunca versione bancos, extratos, planilhas, `.env`, segredos nem backups. Use bancos temporários nos testes. Não mostre conteúdo financeiro em logs de depuração. SQL deve usar parâmetros, e erros apresentados ao usuário devem ser claros, sem traceback ou exposição de caminhos internos desnecessários.

Migrações novas devem preservar dados e incrementar a versão. Faça backup com o aplicativo encerrado antes de testar uma migração em dados reais. Não apague o banco para resolver incompatibilidades.

## Verificação

Implemente em etapas pequenas; execute os testes afetados ao final de cada uma e a suíte completa antes de entregar. Cubra regras com resultados financeiros exatos, casos inválidos, limites de mês e idempotência. Mudanças na interface precisam de verificação manual ou `streamlit.testing.v1.AppTest`, sem reutilizar dados pessoais.

Cada tarefa na nuvem já possui ambiente isolado: use o checkout existente. Não crie `git worktree` sem solicitação explícita do usuário.
