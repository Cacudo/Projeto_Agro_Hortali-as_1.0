import csv
import io
from decimal import Decimal

from flask import Blueprint, Response, abort, render_template, request

from .. import consultas
from ..extensions import db
from ..models import Produto
from . import filtros_periodo, id_arg, todos_produtos

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


@bp.route("/")
def index():
    inicio, fim = filtros_periodo(request.args)
    produto_id = id_arg(request.args, "produto_id")
    por_produto = consultas.resumo_por_produto(inicio, fim, produto_id)
    return render_template(
        "relatorios.html",
        inicio=inicio,
        fim=fim,
        produto_id=produto_id,
        produto=db.session.get(Produto, produto_id) if produto_id else None,
        produtos=todos_produtos(),
        financeiro=consultas.financeiro(inicio, fim, produto_id),
        por_produto=por_produto,
        mais_vendidos=sorted((l for l in por_produto if l["vendido"] > 0),
                             key=lambda l: l["faturamento"], reverse=True),
        maiores_perdas=sorted((l for l in por_produto if l["perdido"] > 0),
                              key=lambda l: l["perdas_valor_venda"], reverse=True),
        motivos=consultas.motivos_perda(inicio, fim, produto_id),
    )


# --------------------------------------------------------------------- CSV

def _numero(valor, casas=2):
    if valor is None:
        return ""
    return f"{Decimal(valor):.{casas}f}".replace(".", ",")


def _seguro(valor):
    """Evita que textos digitados sejam interpretados como fórmula ao abrir o CSV no Excel."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _dados_csv(tipo, inicio, fim, produto_id):
    if tipo == "colheitas":
        cabecalho = ["Data", "Produto", "Lote", "Quantidade", "Unidade", "Validade", "Observações"]
        linhas = [
            [c.data.isoformat(), c.produto.nome, c.lote, _numero(c.quantidade, 3), c.produto.unidade,
             c.validade.isoformat() if c.validade else "", c.observacoes or ""]
            for c in consultas.colheitas(inicio, fim, produto_id)
        ]
    elif tipo == "vendas":
        cabecalho = ["Venda", "Data e hora", "Produto", "Quantidade", "Unidade", "Preço unitário",
                     "Subtotal", "Valor líquido (desconto rateado)", "Custo unitário"]
        linhas = [
            [i.venda_id, i.venda.data_hora.strftime("%Y-%m-%d %H:%M"), i.produto.nome, _numero(i.quantidade, 3),
             i.produto.unidade, _numero(i.preco_unitario), _numero(i.subtotal),
             _numero(consultas.valor_liquido_item(i)), _numero(i.custo_unitario)]
            for i in consultas.itens_vendidos(inicio, fim, produto_id)
        ]
    elif tipo == "perdas":
        cabecalho = ["Data", "Produto", "Lote", "Quantidade", "Unidade", "Motivo", "Valor a preço de venda",
                     "Custo estimado", "Observações"]
        linhas = [
            [p.data.isoformat(), p.produto.nome, p.colheita.lote if p.colheita else "(automático)",
             _numero(p.quantidade, 3), p.produto.unidade, p.motivo_rotulo,
             _numero(p.quantidade * p.preco_unitario),
             _numero(p.quantidade * p.custo_unitario) if p.custo_unitario is not None else "",
             p.observacoes or ""]
            for p in consultas.perdas(inicio, fim, produto_id)
        ]
    elif tipo == "movimentacoes":
        cabecalho = ["Data e hora", "Produto", "Lote", "Tipo", "Quantidade", "Unidade"]
        linhas = [
            [m.data.strftime("%Y-%m-%d %H:%M"), m.produto.nome, m.colheita.lote, m.tipo_rotulo,
             _numero(m.quantidade, 3), m.produto.unidade]
            for m in db.session.scalars(consultas.movimentacoes(inicio, fim, produto_id))
        ]
    elif tipo == "produtos":
        cabecalho = ["Produto", "Unidade", "Colhido", "Vendido", "Perdido", "Índice de perda (%)",
                     "Faturamento líquido", "Perdas a preço de venda", "Perdas a custo"]
        linhas = [
            [l["produto"].nome, l["produto"].unidade, _numero(l["colhido"], 3), _numero(l["vendido"], 3),
             _numero(l["perdido"], 3), _numero(l["indice_perda"], 1), _numero(l["faturamento"]),
             _numero(l["perdas_valor_venda"]),
             _numero(l["perdas_custo"]) if not l["perdas_sem_custo"] else "incompleto"]
            for l in consultas.resumo_por_produto(inicio, fim, produto_id)
        ]
    elif tipo == "motivos":
        cabecalho = ["Motivo", "Ocorrências", "Valor a preço de venda", "Produtos"]
        linhas = [
            [m["rotulo"], m["ocorrencias"], _numero(m["valor_venda"]), m["produtos"]]
            for m in consultas.motivos_perda(inicio, fim, produto_id)
        ]
    else:
        abort(404)
    return cabecalho, linhas


@bp.route("/exportar/<tipo>.csv")
def exportar(tipo):
    inicio, fim = filtros_periodo(request.args)
    produto_id = id_arg(request.args, "produto_id")
    cabecalho, linhas = _dados_csv(tipo, inicio, fim, produto_id)

    saida = io.StringIO()
    # Ponto e vírgula + BOM: o Excel em português abre o arquivo com colunas e acentos corretos.
    saida.write("﻿")
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([_seguro(valor) for valor in linha])

    nome = f"agrohorti-{tipo}-{inicio.isoformat()}-a-{fim.isoformat()}.csv"
    return Response(
        saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
