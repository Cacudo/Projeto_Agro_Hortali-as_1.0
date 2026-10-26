# 🥬 AgroHorti — Gestão de Hortaliças

Aplicação web em Flask para produtores rurais, agricultores familiares e feirantes controlarem
o que foi **colhido**, o que está no **estoque**, o que foi **vendido**, o que **estragou** e qual
foi o **resultado financeiro** das vendas.

## 📌 Funcionalidades

* **Contas de usuário:** cadastro, login e troca de senha. Cada produtor vê apenas os próprios dados.
* **Produtos:** cadastro de hortaliças com unidade (kg, maço, unidade, caixa, dúzia, bandeja), preço de venda,
  validade após a colheita e estoque mínimo. Produtos com histórico são desativados em vez de apagados.
* **Colheitas:** cada colheita registrada entra no estoque.
* **Vendas:** baixa o estoque e calcula o valor no servidor (preço do cadastro ou preço informado na venda).
* **Perdas e descartes:** baixa o estoque, exige o motivo e calcula o prejuízo estimado.
* **Estoque:** saldo por produto, valor estimado e idade da colheita mais antiga ainda em estoque,
  com alertas de validade e de estoque baixo.
* **Cancelamentos:** qualquer registro pode ser cancelado com motivo. Ele continua no histórico,
  mas deixa de contar no estoque e nos totais.
* **Visão geral:** receita, prejuízo e resultado do mês, valor em estoque, alertas e vendas dos últimos 7 dias.
* **Histórico:** todas as movimentações com filtros por tipo, produto, período e situação.
* **Relatórios:** produção, vendas, perdas e resultado por produto em qualquer período, além das perdas por motivo.
* **Exportação CSV** do histórico e dos relatórios (abre direto no Excel/LibreOffice).

## 🧮 Regras de negócio

Seguem o fluxograma em [`Conteiner/conteiner3.html`](Conteiner/conteiner3.html) (PlantUML):

```
Estoque   = Colhido − (Vendido + Perdido)
Prejuízo  = Quantidade perdida × Preço de venda do produto (fixado no momento do registro)
Resultado = Receita das vendas − Prejuízo
```

* Não é possível vender nem registrar perda maior que o estoque disponível.
* Não é possível cancelar uma colheita que já saiu do estoque (cancele antes as vendas/perdas correspondentes).
* Todos os cálculos são feitos no backend. Valores em dinheiro são guardados em centavos.
* Unidades diferentes de kg aceitam apenas quantidades inteiras.

## 🛠️ Tecnologias

* **Backend:** Python 3 / Flask
* **Banco de dados:** SQLite (biblioteca padrão do Python), em `instance/agrohorti.db`
* **Frontend:** HTML5, CSS3, Jinja2 e um pouco de JavaScript puro
* **Hospedagem:** PythonAnywhere

## ▶️ Como executar

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Acesse http://127.0.0.1:5000, crie sua conta e cadastre seus produtos.
O banco de dados e a chave secreta são criados automaticamente na pasta `instance/` (que não vai para o Git).

### Variáveis de ambiente (opcionais)

| Variável | Uso |
|---|---|
| `AGROHORTI_SECRET_KEY` | Chave secreta das sessões. Se não for definida, uma chave é gerada em `instance/secret_key`. |
| `AGROHORTI_DATABASE` | Caminho do arquivo SQLite (padrão: `instance/agrohorti.db`). |
| `AGROHORTI_HTTPS` | Use `1` em produção com HTTPS para enviar o cookie de sessão somente por conexão segura. |
| `FLASK_DEBUG` | Use `1` apenas em desenvolvimento. |

### PythonAnywhere

No arquivo WSGI do PythonAnywhere:

```python
import os, sys
sys.path.insert(0, '/home/SEU_USUARIO/projeto-software-agro-hortalicas')
os.environ['AGROHORTI_HTTPS'] = '1'
from app import app as application
```

## ✅ Testes

```bash
python -m unittest discover -s tests -v
```

## 📁 Estrutura

```
app.py          # criação da aplicação, CSRF, cabeçalhos de segurança, filtros e páginas de erro
auth.py         # cadastro, login, logout e troca de senha
views.py        # páginas e exportação CSV
regras.py       # regras de negócio: estoque, movimentações, cancelamentos e relatórios
database.py     # conexão e criação das tabelas SQLite
templates/      # páginas (base.html é o layout com o menu lateral)
static/         # style.css
tests/          # testes automatizados
Conteiner/      # fluxograma das regras de cálculo (PlantUML)
```

## 🔗 Links do Projeto

* **Repositório GitHub:** https://github.com/Cacudo/projeto-software-agro-hortalicas
* **Aplicação Online:** https://Endrew157.pythonanywhere.com
