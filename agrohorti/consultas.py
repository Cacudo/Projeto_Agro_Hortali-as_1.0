"""Consultas somente-leitura usadas pelo dashboard, estoque e relatórios.

Conceitos financeiros (todos calculados a partir dos registros reais):
- Faturamento bruto: soma dos itens vendidos (quantidade x preço praticado).
- Faturamento líquido: faturamento bruto menos descontos.
- Custo estimado dos vendidos: quantidade x custo unitário cadastrado no momento da venda.
- Perdas: avaliadas pelo custo (prejuízo estimado) e pelo preço de venda
  (receita que deixou de ser obtida). As duas medidas são diferentes.
- Resultado estimado: só é exibido quando todos os itens têm custo cadastrado
  e não inclui despesas gerais (frete, embalagem, taxas, mão de obra etc.).
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import MOTIVOS_PERDA, Colheita, Movimentacao, Perda, Produto, Venda, VendaItem
from .services import lotes_com_saldo, saldos_por_produto
from .utils import CENTAVO

ZERO = Decimal("0")
DIAS_ALERTA_VALIDADE = 2


def periodo_padrao(dias=30):
    fim = date.today()
    return fim - timedelta(days=dias - 1), fim


def _limites(inicio, fim):
    return datetime.combine(inicio, time.min), datetime.combine(fim + timedelta(days=1), time.min)


def valor_liquido_item(item):
    """Valor do item após o desconto da venda, rateado proporcionalmente ao subtotal."""
    venda = item.venda
    if not venda.subtotal:
        return Decimal("0.00")
    return (item.subtotal * venda.total / venda.subtotal).quantize(CENTAVO)


# ---------------------------------------------------------- listas filtradas

def itens_vendidos(inicio, fim, produto_id=None):
    a, b = _limites(inicio, fim)
    consulta = (
        select(VendaItem)
        .join(Venda)
        .where(Venda.cancelada.is_(False), Venda.data_hora >= a, Venda.data_hora < b)
        .options(joinedload(VendaItem.venda), joinedload(VendaItem.produto))
        .order_by(Venda.data_hora.desc(), VendaItem.id)
    )
    if produto_id:
        consulta = consulta.where(VendaItem.produto_id == produto_id)
    return db.session.scalars(consulta).unique().all()


def vendas(inicio, fim, produto_id=None, incluir_canceladas=True):
    a, b = _limites(inicio, fim)
    consulta = (
        select(Venda)
        .where(Venda.data_hora >= a, Venda.data_hora < b)
        .options(joinedload(Venda.itens).joinedload(VendaItem.produto))
        .order_by(Venda.data_hora.desc(), Venda.id.desc())
    )
    if produto_id:
        consulta = consulta.where(Venda.itens.any(VendaItem.produto_id == produto_id))
    if not incluir_canceladas:
        consulta = consulta.where(Venda.cancelada.is_(False))
    return db.session.scalars(consulta).unique().all()


def colheitas(inicio, fim, produto_id=None):
    consulta = (
        select(Colheita)
        .where(Colheita.data >= inicio, Colheita.data <= fim)
        .options(joinedload(Colheita.produto))
        .order_by(Colheita.data.desc(), Colheita.id.desc())
    )
    if produto_id:
        consulta = consulta.where(Colheita.produto_id == produto_id)
    return db.session.scalars(consulta).all()


def perdas(inicio, fim, produto_id=None, incluir_canceladas=False):
    consulta = (
        select(Perda)
        .where(Perda.data >= inicio, Perda.data <= fim)
        .options(joinedload(Perda.produto), joinedload(Perda.colheita))
        .order_by(Perda.data.desc(), Perda.id.desc())
    )
    if produto_id:
        consulta = consulta.where(Perda.produto_id == produto_id)
    if not incluir_canceladas:
        consulta = consulta.where(Perda.cancelada.is_(False))
    return db.session.scalars(consulta).all()


def movimentacoes(inicio=None, fim=None, produto_id=None, tipo=None):
    consulta = (
        select(Movimentacao)
        .options(joinedload(Movimentacao.produto), joinedload(Movimentacao.colheita))
        .order_by(Movimentacao.data.desc(), Movimentacao.id.desc())
    )
    if inicio and fim:
        a, b = _limites(inicio, fim)
        consulta = consulta.where(Movimentacao.data >= a, Movimentacao.data < b)
    if produto_id:
        consulta = consulta.where(Movimentacao.produto_id == produto_id)
    if tipo:
        consulta = consulta.where(Movimentacao.tipo == tipo)
    return consulta


# ---------------------------------------------------------------- agregados

def financeiro(inicio, fim, produto_id=None):
    itens = itens_vendidos(inicio, fim, produto_id)
    bruto = sum((i.subtotal for i in itens), Decimal("0.00"))
    liquido = sum((valor_liquido_item(i) for i in itens), Decimal("0.00"))
    if not produto_id:
        # Sem filtro de produto, usa o total exato das vendas (evita centavos de arredondamento do rateio).
        vendas_validas = {i.venda for i in itens}
        liquido = sum((v.total for v in vendas_validas), Decimal("0.00"))
    numero_vendas = len({i.venda_id for i in itens})

    com_custo = [i for i in itens if i.custo_unitario is not None]
    custo_vendidos = sum(((i.quantidade * i.custo_unitario).quantize(CENTAVO) for i in com_custo), Decimal("0.00"))
    custo_vendidos_completo = len(com_custo) == len(itens)

    lista_perdas = perdas(inicio, fim, produto_id)
    perdas_com_custo = [p for p in lista_perdas if p.custo_unitario is not None]
    perdas_custo = sum(((p.quantidade * p.custo_unitario).quantize(CENTAVO) for p in perdas_com_custo), Decimal("0.00"))
    perdas_custo_completo = len(perdas_com_custo) == len(lista_perdas)
    perdas_valor_venda = sum(((p.quantidade * p.preco_unitario).quantize(CENTAVO) for p in lista_perdas), Decimal("0.00"))

    margem = liquido - custo_vendidos if custo_vendidos_completo else None
    resultado = margem - perdas_custo if margem is not None and perdas_custo_completo else None

    return {
        "faturamento_bruto": bruto,
        "descontos": bruto - liquido,
        "faturamento_liquido": liquido,
        "numero_vendas": numero_vendas,
        "ticket_medio": (liquido / numero_vendas).quantize(CENTAVO) if numero_vendas else None,
        "custo_vendidos": custo_vendidos,
        "custo_vendidos_completo": custo_vendidos_completo,
        "itens_sem_custo": len(itens) - len(com_custo),
        "margem_bruta": margem,
        "perdas_registros": len(lista_perdas),
        "perdas_custo": perdas_custo,
        "perdas_custo_completo": perdas_custo_completo,
        "perdas_sem_custo": len(lista_perdas) - len(perdas_com_custo),
        "perdas_valor_venda": perdas_valor_venda,
        "resultado_estimado": resultado,
    }


def resumo_por_produto(inicio, fim, produto_id=None):
    """Colhido, vendido, perdido e valores por produto no período (unidades nunca se misturam)."""
    linhas = defaultdict(lambda: {
        "colhido": ZERO, "vendido": ZERO, "perdido": ZERO,
        "faturamento": Decimal("0.00"), "perdas_valor_venda": Decimal("0.00"),
        "perdas_custo": Decimal("0.00"), "perdas_sem_custo": 0, "ocorrencias_perda": 0,
    })
    produtos = {}
    for c in colheitas(inicio, fim, produto_id):
        produtos[c.produto_id] = c.produto
        linhas[c.produto_id]["colhido"] += c.quantidade
    for i in itens_vendidos(inicio, fim, produto_id):
        produtos[i.produto_id] = i.produto
        linhas[i.produto_id]["vendido"] += i.quantidade
        linhas[i.produto_id]["faturamento"] += valor_liquido_item(i)
    for p in perdas(inicio, fim, produto_id):
        produtos[p.produto_id] = p.produto
        linha = linhas[p.produto_id]
        linha["perdido"] += p.quantidade
        linha["ocorrencias_perda"] += 1
        linha["perdas_valor_venda"] += (p.quantidade * p.preco_unitario).quantize(CENTAVO)
        if p.custo_unitario is None:
            linha["perdas_sem_custo"] += 1
        else:
            linha["perdas_custo"] += (p.quantidade * p.custo_unitario).quantize(CENTAVO)

    resultado = []
    for pid, linha in linhas.items():
        saidas = linha["vendido"] + linha["perdido"]
        linha["produto"] = produtos[pid]
        # Índice de perda: parte de tudo que saiu do estoque que foi perdida.
        linha["indice_perda"] = (linha["perdido"] * 100 / saidas).quantize(Decimal("0.1")) if saidas else None
        resultado.append(linha)
    resultado.sort(key=lambda l: l["produto"].nome.lower())
    return resultado


def motivos_perda(inicio, fim, produto_id=None):
    grupos = {}
    for p in perdas(inicio, fim, produto_id):
        g = grupos.setdefault(p.motivo, {
            "motivo": p.motivo, "rotulo": MOTIVOS_PERDA.get(p.motivo, p.motivo),
            "ocorrencias": 0, "valor_venda": Decimal("0.00"), "produtos": set(),
        })
        g["ocorrencias"] += 1
        g["valor_venda"] += (p.quantidade * p.preco_unitario).quantize(CENTAVO)
        g["produtos"].add(p.produto.nome)
    resultado = sorted(grupos.values(), key=lambda g: (-g["ocorrencias"], -g["valor_venda"]))
    for g in resultado:
        g["produtos"] = ", ".join(sorted(g["produtos"]))
    return resultado


def faturamento_diario(inicio, fim):
    totais = defaultdict(lambda: Decimal("0.00"))
    for venda in vendas(inicio, fim, incluir_canceladas=False):
        totais[venda.data_hora.date()] += venda.total
    dias = (fim - inicio).days + 1
    serie = [(inicio + timedelta(days=n), totais[inicio + timedelta(days=n)]) for n in range(dias)]
    maior = max((v for _, v in serie), default=ZERO)
    return [
        {"dia": dia, "valor": valor, "percentual": int(valor * 100 / maior) if maior else 0}
        for dia, valor in serie
    ]


# ------------------------------------------------------------------- estoque

def situacao_estoque(incluir_inativos=False):
    saldos = saldos_por_produto()
    consulta = select(Produto).order_by(Produto.nome)
    if not incluir_inativos:
        consulta = consulta.where(Produto.ativo.is_(True))
    linhas = []
    for produto in db.session.scalars(consulta):
        saldo = saldos.get(produto.id, ZERO)
        if saldo <= 0:
            status = "zerado"
        elif produto.estoque_minimo and saldo <= produto.estoque_minimo:
            status = "baixo"
        else:
            status = "ok"
        linhas.append({"produto": produto, "saldo": saldo, "status": status})
    return linhas


def alertas_validade():
    limite = date.today() + timedelta(days=DIAS_ALERTA_VALIDADE)
    alertas = []
    for colheita, saldo in lotes_com_saldo():
        if colheita.validade and colheita.validade <= limite and colheita.produto.ativo:
            alertas.append({
                "colheita": colheita,
                "saldo": saldo,
                "vencido": colheita.validade < date.today(),
                "dias": (colheita.validade - date.today()).days,
            })
    return alertas
