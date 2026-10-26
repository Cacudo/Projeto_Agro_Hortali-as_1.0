from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import consultas
from ..extensions import db
from ..models import Produto, Venda
from ..services import cancelar_venda, registrar_venda, saldos_por_produto
from ..utils import ErroValidacao, data_hora, decimal, formatar_moeda, quantidade, texto
from . import filtros_periodo, id_arg, obter_ou_404, produtos_ativos, todos_produtos

bp = Blueprint("vendas", __name__, url_prefix="/vendas")

MAXIMO_ITENS = 50


@bp.route("/")
def lista():
    inicio, fim = filtros_periodo(request.args)
    produto_id = id_arg(request.args, "produto_id")
    return render_template(
        "vendas/lista.html",
        vendas=consultas.vendas(inicio, fim, produto_id),
        financeiro=consultas.financeiro(inicio, fim, produto_id),
        produtos=todos_produtos(),
        produto_id=produto_id,
        inicio=inicio,
        fim=fim,
    )


def _ler_itens(form):
    produtos_ids = form.getlist("produto_id")
    quantidades = form.getlist("quantidade")
    precos = form.getlist("preco_unitario")
    if not (len(produtos_ids) == len(quantidades) == len(precos)):
        raise ErroValidacao("Os itens da venda estão incompletos. Recarregue a página e tente novamente.")
    if len(produtos_ids) > MAXIMO_ITENS:
        raise ErroValidacao(f"Uma venda pode ter no máximo {MAXIMO_ITENS} itens.")

    itens = []
    for numero, (pid, qtd, preco) in enumerate(zip(produtos_ids, quantidades, precos), start=1):
        if not (pid or qtd.strip() or preco.strip()):
            continue  # linha em branco
        try:
            produto = db.session.get(Produto, int(pid)) if pid else None
        except ValueError:
            produto = None
        if produto is None:
            raise ErroValidacao(f"Item {numero}: selecione o produto.")
        itens.append((
            produto,
            quantidade(qtd, f"a quantidade de {produto.nome}", produto.fracionavel),
            decimal(preco, f"o preço de {produto.nome}", permitir_zero=False),
        ))
    return itens


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        try:
            venda = registrar_venda(
                _ler_itens(request.form),
                decimal(request.form.get("desconto") or "0", "o desconto"),
                data_hora(request.form.get("data_hora")),
                observacoes=texto(request.form.get("observacoes"), "as observações", obrigatorio=False,
                                  maximo=500, multilinha=True),
                usuario=g.usuario,
            )
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("vendas/form.html", **_contexto_formulario(request.form)), 400
        flash(f"Venda nº {venda.id} registrada. Total: {formatar_moeda(venda.total)}. O estoque foi atualizado.",
              "sucesso")
        return redirect(url_for("vendas.detalhe", venda_id=venda.id))

    dados = {"data_hora": datetime.now().strftime("%Y-%m-%dT%H:%M"), "desconto": "0"}
    return render_template("vendas/form.html", **_contexto_formulario(dados))


def _contexto_formulario(form):
    # Reconstrói as linhas digitadas para não perder o trabalho do usuário em caso de erro.
    if hasattr(form, "getlist"):
        linhas = list(zip(form.getlist("produto_id"), form.getlist("quantidade"), form.getlist("preco_unitario")))
    else:
        linhas = []
    return {
        "produtos": produtos_ativos(),
        "saldos": saldos_por_produto(),
        "dados": form,
        "linhas": linhas or [("", "", "")],
    }


@bp.route("/<int:venda_id>")
def detalhe(venda_id):
    venda = obter_ou_404(Venda, venda_id)
    return render_template("vendas/detalhe.html", venda=venda)


@bp.route("/<int:venda_id>/cancelar", methods=["POST"])
def cancelar(venda_id):
    venda = obter_ou_404(Venda, venda_id)
    try:
        motivo = texto(request.form.get("motivo_cancelamento"), "o motivo do cancelamento", maximo=300)
        cancelar_venda(venda, motivo)
    except ErroValidacao as erro:
        flash(str(erro), "erro")
    else:
        flash(f"Venda nº {venda.id} cancelada. Os produtos voltaram ao estoque.", "sucesso")
    return redirect(url_for("vendas.detalhe", venda_id=venda.id))
