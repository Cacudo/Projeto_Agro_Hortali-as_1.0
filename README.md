# 🥬 AgroHorti — Gestão de Hortaliças

Sistema web para produtores rurais, agricultores familiares e feirantes controlarem
**colheitas, estoque, perdas e vendas** de hortaliças, que são produtos perecíveis.

Ele responde a perguntas como: quanto foi colhido, quanto há em estoque, quanto foi vendido,
quanto estragou e por quê, quais produtos têm mais desperdício, quanto foi faturado e
quais produtos precisam de atenção.

## Funcionalidades

| Módulo | O que faz |
|---|---|
| **Login** | Autenticação real com senha criptografada (hash), sessão segura e proteção CSRF. No primeiro acesso, o sistema pede a criação do usuário administrador. |
| **Produtos** | Cadastro com categoria, unidade, preço, custo (opcional), estoque mínimo e prazo de conservação. Tem busca, filtro, edição, desativação e exclusão (esta só para produtos sem histórico). Impede nomes duplicados. |
| **Colheitas** | Cada colheita forma um **lote** e entra automaticamente no estoque. A validade do lote é calculada pelo prazo de conservação. |
| **Estoque** | Saldo por produto e por lote, alertas de estoque baixo/zerado e de lotes vencendo, e histórico completo de movimentações. |
| **Perdas e descartes** | Registro com motivo e lote opcional. A baixa nunca ultrapassa o disponível. Mostra o total por motivo e por produto, os valores a preço de venda e o prejuízo estimado a custo. |
| **Vendas** | Venda com vários itens e desconto. Os valores são recalculados no servidor e o estoque é baixado do lote mais antigo. O cancelamento devolve as quantidades ao estoque e mantém o histórico. |
| **Painel** | Indicadores reais do período (7/30/90 dias), alertas, gráfico de faturamento diário, mais vendidos, maiores perdas e movimentações recentes. |
| **Relatórios** | Resumo financeiro, dados por produto, rankings e motivos de descarte, com filtros de período e produto e **exportação CSV** (abre corretamente no Excel em português). |
| **Pulverização** | Módulo herdado da versão anterior: volume de calda = área × dosagem, agora salvo no banco e com edição. |
| **Configurações** | Troca de senha, criação de usuários e ativação/desativação de acessos. |

### Como os números são calculados

- **Estoque**: não fica guardado em nenhum campo. É sempre a soma das movimentações
  (colheitas − vendas − perdas + estornos), então existe uma única fonte de verdade.
- **Faturamento bruto** = soma de quantidade × preço praticado. **Líquido** = bruto − descontos.
- **Custo estimado dos vendidos** e **perdas a custo** usam o custo de produção que estava
  cadastrado no momento da venda ou da perda.
- **Perdas a preço de venda** = receita que deixou de entrar. **Não** é o prejuízo real.
- **Resultado estimado** = faturamento líquido − custo dos vendidos − perdas a custo.
  Só aparece quando todos os itens do período têm custo cadastrado. **Não é o lucro real**:
  não inclui frete, embalagens, taxas da feira e outras despesas.
- **Índice de perda** = perdido ÷ (vendido + perdido) no período.

## Tecnologias

- Python 3.10+ (testado com Python 3.14), Flask 3.1, Flask-SQLAlchemy 3.1 e SQLAlchemy 2.1
- Banco **SQLite** (arquivo `instance/agrohorti.db`, criado automaticamente)
- HTML + Jinja2, CSS próprio e JavaScript puro (sem frameworks)

## Instalação e execução no Windows (VS Code)

1. **Instale o Python** pelo site https://www.python.org/downloads/ e marque
   *"Add python.exe to PATH"* durante a instalação.
2. **Abra a pasta do projeto no VS Code** (*File › Open Folder…*), na pasta onde está o `app.py`.
3. **Abra o terminal** (*Terminal › New Terminal*) e crie o ambiente virtual:
   ```powershell
   python -m venv .venv
   ```
4. **Ative o ambiente virtual**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   Se aparecer um erro de *execução de scripts desabilitada*, rode uma vez
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e tente novamente.
   No *Prompt de Comando* (cmd), use `.venv\Scripts\activate.bat`.
5. **Instale as dependências**:
   ```powershell
   pip install -r requirements.txt
   ```
6. **Execute o sistema**:
   ```powershell
   python app.py
   ```
7. **Acesse** http://127.0.0.1:5000 no navegador. No primeiro acesso, crie o usuário administrador.

O banco de dados e a chave secreta são criados automaticamente na pasta `instance/`.
Não é preciso nenhum comando extra para inicializar o banco.

> Dica: no VS Code, selecione o interpretador do `.venv` com *Ctrl+Shift+P › Python: Select Interpreter*.

### Usar no celular (mesma rede Wi-Fi)

```powershell
$env:AGROHORTI_HOST = "0.0.0.0"
python app.py
```
No celular, acesse `http://IP-DO-COMPUTADOR:5000` (veja o IP com `ipconfig`). O Firewall do
Windows pode pedir permissão. Use essa opção apenas em redes confiáveis: o servidor de
desenvolvimento não usa HTTPS.

### Variáveis de ambiente (opcionais)

| Variável | Para quê | Padrão |
|---|---|---|
| `AGROHORTI_SECRET_KEY` | Chave de sessão. Recomendada em servidor público. | Gerada e salva em `instance/secret_key` |
| `AGROHORTI_DATABASE_URL` | Outro banco/arquivo (URL do SQLAlchemy) | `sqlite:///instance/agrohorti.db` |
| `AGROHORTI_HOST` / `AGROHORTI_PORT` | Endereço e porta do servidor local | `127.0.0.1` / `5000` |
| `FLASK_DEBUG` | `1` ativa o modo de depuração (só para desenvolvimento) | desativado |

No PowerShell: `$env:AGROHORTI_SECRET_KEY = "uma-frase-longa-e-aleatoria"`.

### Publicação no PythonAnywhere

No arquivo WSGI do PythonAnywhere, aponte para a pasta do projeto e use:
```python
from app import app as application
```
Instale as dependências com `pip install -r requirements.txt` no virtualenv do site e defina
`AGROHORTI_SECRET_KEY` no arquivo WSGI (`os.environ[...]`) antes do import.

## Testes automatizados

```powershell
python -m unittest discover -s tests -v
```
São 38 testes, cobrindo login, CSRF, produtos, colheitas, estoque por lote, vendas
(incluindo atomicidade e cancelamento), perdas, cálculos financeiros, CSV, persistência
após reinício e pulverização. Os testes usam bancos temporários e não tocam no banco real.

## Estrutura

```
app.py                  Ponto de entrada (python app.py / WSGI)
agrohorti/
  __init__.py           Criação da aplicação, configuração, CSRF, filtros
  models.py             Tabelas do banco
  services.py           Regras que alteram o estoque (colheita, venda, perda, estornos)
  consultas.py          Consultas do painel, estoque e relatórios
  utils.py              Validação de entradas e formatação brasileira
  rotas/                Páginas de cada módulo (auth, produtos, vendas, ...)
templates/              Páginas HTML (Jinja2)
static/                 style.css e app.js
tests/                  Testes automatizados
docs/                   Pitch deck e fluxograma dos cálculos
instance/               Banco de dados e chave secreta (criados ao executar; não versionar)
```

## Backup dos dados

Todos os dados ficam em `instance/agrohorti.db`. Para fazer backup, feche o sistema e copie
esse arquivo. Não apague a pasta `instance/`.

## Limitações conhecidas

- Os dados são compartilhados por todos os usuários (uma propriedade por instalação) e não há níveis de permissão.
- Não há limite de tentativas de login. Em servidor público, use senhas fortes.
- Ícones e fonte vêm de CDN (Font Awesome e Google Fonts). Sem internet, o sistema funciona, mas os ícones não aparecem.
- Mudanças futuras na estrutura do banco exigirão uma ferramenta de migração (ex.: Flask-Migrate). Hoje o sistema só cria tabelas que não existem.
- O servidor `python app.py` é para uso local. Em produção, use um servidor WSGI (ex.: PythonAnywhere).

## Links

- Repositório: https://github.com/Cacudo/Projeto_Agro_Hortali-as_1.0
- Repositório anterior: https://github.com/Cacudo/projeto-software-agro-hortalicas
- Versão online anterior: https://Endrew157.pythonanywhere.com
