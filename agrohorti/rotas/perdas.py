from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import consultas
from ..extensions import db
from ..models import MOTIVOS_PERDA, Colheita, Perda, Produto
from ..services import cancelar_perda, lotes_com_saldo, registrar_perda, saldos_por_produto
from ..utils import ErroValidacao, data, quantidade, texto
from . import filtros_periodo, id_arg, obter_ou_404, produtos_ativos, todos_produtos

bp = Blueprint("perdas", __name__, url_prefix="/perdas")


@bp.route("/")
def lista():
    inicio, fim = filtros_periodo(request.args)
    produto_id = id_arg(request.args, "produto_id")
    motivo = request.args.get("motivo") or ""
    registros = consultas.perdas(inicio, fim, produto_id, incluir_canceladas=True)
    if motivo in MOTIVOS_PERDA:
        registros = [p for p in registros if p.motivo == motivo]
    return render_template(
        "perdas/lista.html",
        perdas=registros,
        motivos=consultas.motivos_perda(inicio, fim, produto_id),
        financeiro=consultas.financeiro(inicio, fim, produto_id),
        produtos=todos_produtos(),
        produto_id=produto_id,
        motivo=motivo,
        inicio=inicio,
        fim=fim,
    )


def _contexto_formulario(dados):
    return {
        "produtos": produtos_ativos(),
        "saldos": saldos_por_produto(),
        "lotes": lotes_com_saldo(),
        "dados": dados,
    }


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        try:
            produto = db.session.get(Produto, id_arg(request.form, "produto_id") or 0)
            if produto is None or not produto.ativo:
                raise ErroValidacao("Selecione um produto ativo.")
            colheita = None
            colheita_id = id_arg(request.form, "colheita_id")
            if colheita_id:
                colheita = db.session.get(Colheita, colheita_id)
                if colheita is None:
                    raise ErroValidacao("Lote não encontrado.")
            perda = registrar_perda(
                produto,
                quantidade(request.form.get("quantidade"), "a quantidade perdida", produto.fracionavel),
                data(request.form.get("data"), "a data da perda"),
                request.form.get("motivo"),
                colheita=colheita,
                observacoes=texto(request.form.get("observacoes"), "as observações", obrigatorio=False,
                                  maximo=500, multilinha=True),
                usuario=g.usuario,
            )
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("perdas/form.html", **_contexto_formulario(request.form)), 400
        flash(f"Perda de {produto.nome} registrada ({perda.motivo_rotulo}). O estoque foi atualizado.", "sucesso")
        return redirect(url_for("perdas.lista"))

    dados = {
        "data": date.today().isoformat(),
        "produto_id": request.args.get("produto_id", ""),
        "colheita_id": request.args.get("colheita_id", ""),
    }
    return render_template("perdas/form.html", **_contexto_formulario(dados))


@bp.route("/<int:perda_id>/cancelar", methods=["POST"])
def cancelar(perda_id):
    perda = obter_ou_404(Perda, perda_id)
    try:
        motivo = texto(request.form.get("motivo_cancelamento"), "o motivo do cancelamento", maximo=300)
        cancelar_perda(perda, motivo)
    except ErroValidacao as erro:
        flash(str(erro), "erro")
    else:
        flash("Perda cancelada. A quantidade voltou ao estoque e o registro foi mantido no histórico.", "sucesso")
    return redirect(url_for("perdas.lista"))
