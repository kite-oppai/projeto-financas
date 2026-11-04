# Minhas finanças

Aplicativo de controle financeiro pessoal em português, executado no seu computador com **Python 3.11+, Streamlit e SQLite**. Registre receitas e despesas, acompanhe orçamento e metas, importe extratos e visualize seu histórico mensal e anual.

## Instalação e execução

Abra um terminal **na pasta deste projeto**. Crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative-o no Linux/macOS:

```bash
source .venv/bin/activate
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instale as dependências e execute:

```bash
pip install -r requirements.txt
streamlit run app.py
```

O terminal informa o endereço da interface, normalmente `http://127.0.0.1:8501`. Para encerrar, pressione `Ctrl+C`. As tabelas e categorias padrão são criadas automaticamente na primeira execução. Não há conta de acesso, cadastro online nem servidor de banco para configurar.

A instalação das bibliotecas requer internet; o uso do aplicativo com as dependências instaladas é local. Não use opções que exponham o Streamlit na rede: a configuração fornecida escuta somente em `127.0.0.1`.

## Começando

1. Cadastre uma conta corrente, poupança, dinheiro ou cartão e informe o saldo inicial.
2. Registre um lançamento com data, descrição, valor positivo, tipo, categoria e conta. O tipo determina se o valor entra ou sai.
3. Escolha mês e ano para acompanhar receitas, despesas, saldo do período, gráficos e comparação com o mês anterior.
4. Defina limites mensais por categoria. A partir de 80% do limite há alerta; a partir de 100%, o limite foi atingido ou ultrapassado.
5. Use as demais páginas para importar extratos, configurar recorrências, acompanhar metas e exportar dados.

Valores aceitam `1234,56`, `1.234,56` e `1234.56`. O aplicativo não arredonda entradas com mais de duas casas decimais. Valores são exibidos como `R$ 1.234,56`; datas, como `dd/mm/aaaa`.

Categorias padrão: Moradia, Mercado, Transporte, Lazer, Saúde, Educação, Assinaturas e Outros. Categorias e contas em uso não podem ser excluídas: altere ou remova os registros vinculados antes. A exclusão de um lançamento é definitiva; mantenha backups.

### Saldos e cartões

O saldo de uma conta é o saldo inicial mais todas as receitas menos todas as despesas registradas nela. Ele considera também lançamentos futuros cadastrados. O saldo mensal do dashboard é apenas receitas menos despesas daquele mês, sem o saldo inicial.

Cartões usam o mesmo registro de movimentos: compras são despesas integrais na data da compra; saldo negativo representa dívida. Este MVP **não gerencia faturas, fechamento, vencimento, parcelamento ou transferências entre contas**. Não duplique uma compra como outra despesa ao registrar um pagamento, pois isso duplicaria o gasto nos relatórios. Para manter a análise de gastos do cartão, registre as compras nele; uma conciliação de pagamentos entre contas exigirá uma evolução específica do modelo.

### Recorrências

Crie uma regra mensal com dia, mês inicial, mês final opcional, conta e categoria. Ao abrir ou atualizar o aplicativo, as competências pendentes com data já alcançada são geradas automaticamente sem repetir uma mesma regra no mesmo mês. Dias 29, 30 e 31 são ajustados ao último dia de meses mais curtos. A regra pode ser desativada para suspender novas gerações; ao reativá-la, os meses pendentes durante a pausa também são recuperados. Para encerrar uma obrigação, defina o mês final. Editar a regra não altera o histórico já gerado. Excluir um lançamento gerado não faz com que ele reapareça.

O aplicativo não é um agendador em segundo plano: se ficar fechado, a recuperação dos meses pendentes ocorre na próxima abertura. Revise o mês inicial antes de salvar uma regra retroativa.

### Metas

Uma meta tem nome, valor-alvo e prazo. O progresso é a soma dos **aportes registrados manualmente**. Aportes são anotações para acompanhamento: não criam lançamentos, não movimentam contas e não reservam saldo automaticamente. Registre eventual movimento financeiro também na conta correspondente, conforme seu controle.

## Importação e exportação

A importação CSV permite escolher codificação (UTF-8 ou Latin-1), separador (ponto e vírgula, vírgula, tabulação ou barra vertical), formato de data e as colunas de data, descrição e valor. Tipo e observação são opcionais. Escolha a conta e a categoria que receberão os movimentos; depois poderá editar os lançamentos individualmente.

No modo de tipo automático, valores negativos são despesas e positivos são receitas. Com tipo fixo, o valor representa o montante do lançamento. Datas brasileiras e ISO são suportadas conforme o formato escolhido. OFX simples também é aceito: são lidos os movimentos, valores, datas, nomes e observações, sem conectar ao banco.

Confira a prévia antes de salvar. Linhas inválidas bloqueiam a importação inteira. São consideradas possíveis duplicatas as linhas com mesma data, descrição normalizada, valor, tipo e conta, tanto no banco quanto no próprio arquivo; categoria e observação não diferenciam esses movimentos. Por padrão, duplicatas são puladas. Só permita sua inclusão quando tiver confirmado que representam movimentos distintos.

As exportações contêm todas as tabelas: **CSV em um arquivo ZIP**, com um CSV por tabela, ou **Excel**, com uma aba por tabela. Datas saem em `dd/mm/aaaa`; valores monetários em reais com vírgula decimal, preservados como texto para não perder centavos. Textos potencialmente interpretados como fórmulas por planilhas são protegidos. A exportação serve para consulta; para backup e restauração completos, copie o arquivo SQLite com o aplicativo encerrado.

## Demonstração opcional

Para experimentar sem misturar dados reais:

```bash
python seed.py
```

Isso cria `data/demo.db` com três meses de movimentos fictícios, duas contas, orçamentos, uma recorrência para o próximo mês e uma meta. Repetir o comando não duplica os dados. O script ignora `FINANCAS_DB_PATH` e só usa `--db` quando informado explicitamente; recusa um banco existente que não tenha sido criado como demonstração.

Abra a base demonstrativa no Linux/macOS:

```bash
FINANCAS_DB_PATH=data/demo.db streamlit run app.py
```

No Windows PowerShell:

```powershell
$env:FINANCAS_DB_PATH = "data/demo.db"
streamlit run app.py
```

Para voltar à base pessoal, encerre o app e remova a variável (`unset FINANCAS_DB_PATH` no Linux/macOS ou `Remove-Item Env:FINANCAS_DB_PATH` no PowerShell). Também é possível criar outra demonstração: `python seed.py --db data/outra-demo.db`.

## Dados, privacidade e backup

- O banco padrão é `data/financas.db`, relativo à pasta do projeto. Para escolher outro, defina `FINANCAS_DB_PATH` antes de iniciar o app.
- Os cálculos usam centavos inteiros; conversões monetárias usam `Decimal`. O SQLite mantém tudo em um arquivo e ativa integridade referencial.
- As migrações são executadas automaticamente na inicialização e controladas por `PRAGMA user_version`. Antes de atualizar o projeto, encerre o app e copie o banco para um local seguro. Para restaurar, encerre o app e substitua o arquivo por sua cópia.
- O app não faz chamadas a APIs, não carrega fontes ou imagens remotas e desativa a telemetria do Streamlit em `.streamlit/config.toml`. Arquivos importados são processados no processo local; gráficos também são renderizados localmente.
- O banco não é criptografado e o app não tem autenticação. Use a proteção de acesso e criptografia de disco do seu sistema. Não compartilhe a pasta de dados.
- Bancos, CSV, OFX, planilhas, arquivos `.env` e segredos locais são ignorados pelo Git. Isso não remove arquivos que já tenham sido versionados anteriormente; confira `git status` antes de publicar alterações.

## Testes e verificação manual

Execute:

```bash
python -m pytest -q
```

Os testes usam bancos temporários e cobrem validação de valores, saldos, orçamento, recorrências, importação e dados de demonstração. Não precisam do seu banco pessoal.

Roteiro rápido na base de demonstração:

1. Confira receitas e despesas do mês atual e do anterior, gráfico por categoria, evolução e maiores despesas.
2. Cadastre uma despesa de `10,50`; confirme que o saldo da conta diminui exatamente esse valor. Edite para `12,50` e depois exclua para conferir a reversão.
3. Confira os três estados de orçamento: Moradia abaixo de 80%, Mercado acima de 80% e Lazer acima do limite.
4. Crie uma regra com início no mês atual e dia 1, atualize a página duas vezes e confira que existe somente um lançamento daquela competência.
5. Registre um aporte em uma meta e confira o progresso; o saldo da conta deve permanecer igual.
6. Importe um pequeno extrato com prévia e depois o mesmo arquivo novamente para conferir a detecção de duplicatas.
7. Exporte os dados e abra o CSV/Excel para conferir moeda, datas e registros.

## VS Code

Abra a pasta do projeto no VS Code e instale as extensões Python e Python Debugger sugeridas. Selecione o interpretador de `.venv`. Em **Executar e Depurar**, escolha **Finanças: executar e depurar**; os breakpoints funcionam nas páginas e serviços Python. **Finanças: demonstração** usa `data/demo.db` (execute `python seed.py` antes). Os testes aparecem no painel de testes via pytest.

## Estrutura e arquitetura

```text
app.py                 Entrada Streamlit, banco e navegação
database/              Conexão SQLite, esquema e migrações
services/              Regras, validações, importação e relatórios
ui/                    Páginas e componentes de interface
tests/                 Testes automatizados com bancos temporários
seed.py                Demonstração opcional e isolada
data/                  Bancos locais, fora do Git
.streamlit/            Tema, interface local e telemetria desativada
.vscode/               Configurações de execução e depuração
CLAUDE.md              Convenções para manutenção
```

As páginas chamam serviços; regras financeiras não ficam em callbacks da interface. Os serviços validam entradas e consultam/persistem dados em SQLite. Plotly apresenta os gráficos; a exportação Excel usa openpyxl. Pandas está disponível para análises locais. Erros de validação são mostrados em português.
