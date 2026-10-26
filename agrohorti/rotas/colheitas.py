from datetime import date

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Colheita, Movimentacao, Produto
from ..services import excluir_colheita, registrar_colheita
from ..utils import ErroValidacao, data, quantidade, texto
from . import filtros_periodo, id_arg, obter_ou_404, produtos_ativos, todos_produtos

bp = Blueprint("colheitas", __name__, url_prefix="/colheitas")


@bp.route("/")
def lista():
    inicio, fim = filtros_periodo(request.args)
    produto_id = id_arg(request.args, "produto_id")
    consulta = (
        select(Colheita)
        .where(Colheita.data >= inicio, Colheita.data <= fim)
        .options(joinedload(Colheita.produto))
        .order_by(Colheita.data.desc(), Colheita.id.desc())
    )
    if produto_id:
        consulta = consulta.where(Colheita.produto_id == produto_id)
    pagina = db.paginate(consulta, per_page=current_app.config["ITENS_POR_PAGINA"], error_out=False)

    ids = [c.id for c in pagina.items]
    saldos = dict(
        db.session.execute(
            select(Movimentacao.colheita_id, func.sum(Movimentacao.quantidade))
            .where(Movimentacao.colheita_id.in_(ids))
            .group_by(Movimentacao.colheita_id)
        ).all()
    ) if ids else {}

    return render_template(
        "colheitas/lista.html",
        pagina=pagina,
        saldos=saldos,
        produtos=todos_produtos(),
        produto_id=produto_id,
        inicio=inicio,
        fim=fim,
    )


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    produtos = produtos_ativos()
    if request.method == "POST":
        try:
            produto = db.session.get(Produto, id_arg(request.form, "produto_id") or 0)
            if produto is None or not produto.ativo:
                raise ErroValidacao("Selecione um produto ativo.")
            colheita = registrar_colheita(
                produto,
                quantidade(request.form.get("quantidade"), "a quantidade colhida", produto.fracionavel),
                data(request.form.get("data"), "a data da colheita"),
                lote=texto(request.form.get("lote"), "o lote", obrigatorio=False, maximo=40),
                observacoes=texto(request.form.get("observacoes"), "as observações", obrigatorio=False,
                                  maximo=500, multilinha=True),
                usuario=g.usuario,
            )
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("colheitas/form.html", produtos=produtos, dados=request.form), 400
        flash(
            f"Colheita registrada: lote {colheita.lote} de {produto.nome}. O estoque foi atualizado.",
            "sucesso",
        )
        if request.form.get("continuar"):
            return redirect(url_for("colheitas.nova"))
        return redirect(url_for("colheitas.lista"))

    dados = {"data": date.today().isoformat(), "produto_id": request.args.get("produto_id", "")}
    return render_template("colheitas/form.html", produtos=produtos, dados=dados)


@bp.route("/<int:colheita_id>/excluir", methods=["POST"])
def excluir(colheita_id):
    colheita = obter_ou_404(Colheita, colheita_id)
    lote = colheita.lote
    try:
        excluir_colheita(colheita)
    except ErroValidacao as erro:
        flash(str(erro), "erro")
    else:
        flash(f"Colheita do lote {lote} excluída e removida do estoque.", "sucesso")
    return redirect(url_for("colheitas.lista"))
