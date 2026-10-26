from datetime import timedelta

from flask import abort
from sqlalchemy import select

from ..consultas import periodo_padrao
from ..extensions import db
from ..models import Produto
from ..utils import data_filtro


def registrar_blueprints(app):
    from . import (
        auth,
        colheitas,
        configuracoes,
        estoque,
        painel,
        perdas,
        produtos,
        pulverizacao,
        relatorios,
        vendas,
    )

    for modulo in (auth, painel, produtos, colheitas, perdas, vendas, estoque, relatorios, pulverizacao, configuracoes):
        app.register_blueprint(modulo.bp)


def filtros_periodo(args, dias=30):
    """Lê ?inicio=&fim= da URL; valores ausentes ou inválidos usam os últimos `dias` dias."""
    padrao_inicio, padrao_fim = periodo_padrao(dias)
    inicio = data_filtro(args.get("inicio")) or padrao_inicio
    fim = data_filtro(args.get("fim")) or padrao_fim
    if inicio > fim:
        inicio, fim = fim, inicio
    # Limita a 10 anos para evitar gráficos e consultas gigantes por engano.
    inicio = max(inicio, fim - timedelta(days=3660))
    return inicio, fim


def id_arg(args, nome):
    try:
        valor = int(args.get(nome, ""))
    except ValueError:
        return None
    return valor if valor > 0 else None


def obter_ou_404(modelo, ident):
    objeto = db.session.get(modelo, ident)
    if objeto is None:
        abort(404)
    return objeto


def produtos_ativos():
    return db.session.scalars(select(Produto).where(Produto.ativo.is_(True)).order_by(Produto.nome)).all()


def todos_produtos():
    return db.session.scalars(select(Produto).order_by(Produto.nome)).all()
