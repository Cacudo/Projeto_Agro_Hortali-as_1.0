from flask import Blueprint, redirect, render_template, request, url_for

from .. import consultas
from ..extensions import db
from . import filtros_periodo

bp = Blueprint("painel", __name__)


@bp.route("/")
def index():
    inicio, fim = filtros_periodo(request.args)
    situacao = consultas.situacao_estoque()
    por_produto = consultas.resumo_por_produto(inicio, fim)
    maiores_perdas = sorted(
        (l for l in por_produto if l["perdido"] > 0), key=lambda l: l["perdas_valor_venda"], reverse=True
    )[:5]
    mais_vendidos = sorted(
        (l for l in por_produto if l["vendido"] > 0), key=lambda l: l["faturamento"], reverse=True
    )[:5]

    atalhos = []
    for dias in (7, 30, 90):
        ini, fim_atalho = consultas.periodo_padrao(dias)
        atalhos.append((dias, ini, (inicio, fim) == (ini, fim_atalho)))

    return render_template(
        "dashboard.html",
        inicio=inicio,
        fim=fim,
        atalhos=atalhos,
        financeiro=consultas.financeiro(inicio, fim),
        total_produtos=len(situacao),
        estoque_baixo=[l for l in situacao if l["status"] == "baixo"],
        sem_estoque=[l for l in situacao if l["status"] == "zerado"],
        com_estoque=sum(1 for l in situacao if l["saldo"] > 0),
        alertas_validade=consultas.alertas_validade(),
        por_produto=por_produto,
        maiores_perdas=maiores_perdas,
        mais_vendidos=mais_vendidos,
        grafico=consultas.faturamento_diario(inicio, fim) if (fim - inicio).days <= 92 else None,
        recentes=db.session.scalars(consultas.movimentacoes().limit(8)).all(),
    )


@bp.route("/visao-geral")
def visao_geral():
    # Endereço da versão anterior, mantido para não quebrar favoritos.
    return redirect(url_for("painel.index"))
