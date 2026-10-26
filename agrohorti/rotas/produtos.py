from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from ..extensions import db
from ..models import CATEGORIAS, UNIDADES, Produto
from ..services import produto_tem_historico, saldo_produto, saldos_por_produto
from ..utils import MILESIMO, ErroValidacao, decimal, inteiro, normalizar_nome, texto
from . import obter_ou_404

bp = Blueprint("produtos", __name__, url_prefix="/produtos")


def _ler_formulario(form, produto=None):
    nome = texto(form.get("nome"), "o nome", maximo=80)
    normalizado = normalizar_nome(nome)
    consulta = select(Produto).where(Produto.nome_normalizado == normalizado)
    if produto is not None:
        consulta = consulta.where(Produto.id != produto.id)
    existente = db.session.scalar(consulta)
    if existente:
        situacao = "" if existente.ativo else " (desativado — reative-o na lista de produtos)"
        raise ErroValidacao(f"Já existe um produto chamado “{existente.nome}”{situacao}.")

    categoria = form.get("categoria")
    if categoria not in CATEGORIAS:
        raise ErroValidacao("Selecione uma categoria válida.")
    unidade = form.get("unidade")
    if unidade not in UNIDADES:
        raise ErroValidacao("Selecione uma unidade de medida válida.")
    if produto is not None and unidade != produto.unidade and produto_tem_historico(produto.id):
        raise ErroValidacao(
            "A unidade não pode ser alterada porque o produto já tem colheitas, vendas ou perdas. "
            "Isso tornaria o histórico incorreto."
        )

    return {
        "nome": nome,
        "nome_normalizado": normalizado,
        "categoria": categoria,
        "unidade": unidade,
        "preco_venda": decimal(form.get("preco_venda"), "o preço de venda", permitir_zero=False),
        "custo_unitario": decimal(form.get("custo_unitario"), "o custo unitário", obrigatorio=False),
        "estoque_minimo": decimal(form.get("estoque_minimo") or "0", "o estoque mínimo", casas=MILESIMO),
        "validade_dias": inteiro(form.get("validade_dias"), "o prazo de conservação", obrigatorio=False),
        "conservacao": texto(form.get("conservacao"), "as informações de conservação", obrigatorio=False,
                             maximo=500, multilinha=True),
    }


@bp.route("/")
def lista():
    busca = (request.args.get("q") or "").strip()
    categoria = request.args.get("categoria") or ""
    situacao = request.args.get("situacao") or "ativos"

    consulta = select(Produto).order_by(Produto.nome)
    if busca:
        consulta = consulta.where(Produto.nome_normalizado.contains(normalizar_nome(busca)))
    if categoria in CATEGORIAS:
        consulta = consulta.where(Produto.categoria == categoria)
    if situacao == "ativos":
        consulta = consulta.where(Produto.ativo.is_(True))
    elif situacao == "inativos":
        consulta = consulta.where(Produto.ativo.is_(False))

    return render_template(
        "produtos/lista.html",
        produtos=db.session.scalars(consulta).all(),
        saldos=saldos_por_produto(),
        busca=busca,
        categoria=categoria,
        situacao=situacao,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    if request.method == "POST":
        try:
            dados = _ler_formulario(request.form)
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("produtos/form.html", produto=None, dados=request.form), 400
        produto = Produto(**dados)
        db.session.add(produto)
        db.session.commit()
        flash(f"Produto “{produto.nome}” cadastrado.", "sucesso")
        return redirect(url_for("produtos.lista"))
    return render_template("produtos/form.html", produto=None, dados={"estoque_minimo": "0"})


@bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
def editar(produto_id):
    produto = obter_ou_404(Produto, produto_id)
    if request.method == "POST":
        try:
            dados = _ler_formulario(request.form, produto)
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("produtos/form.html", produto=produto, dados=request.form), 400
        for campo, valor in dados.items():
            setattr(produto, campo, valor)
        db.session.commit()
        flash(f"Produto “{produto.nome}” atualizado. Vendas e perdas antigas mantêm os valores da época.", "sucesso")
        return redirect(url_for("produtos.lista"))

    dados = {
        "nome": produto.nome,
        "categoria": produto.categoria,
        "unidade": produto.unidade,
        "preco_venda": produto.preco_venda,
        "custo_unitario": produto.custo_unitario if produto.custo_unitario is not None else "",
        "estoque_minimo": produto.estoque_minimo.normalize() if produto.estoque_minimo else "0",
        "validade_dias": produto.validade_dias or "",
        "conservacao": produto.conservacao or "",
    }
    return render_template(
        "produtos/form.html", produto=produto, dados=dados, tem_historico=produto_tem_historico(produto.id)
    )


@bp.route("/<int:produto_id>/excluir", methods=["POST"])
def excluir(produto_id):
    produto = obter_ou_404(Produto, produto_id)
    if produto_tem_historico(produto.id):
        flash(
            f"“{produto.nome}” tem histórico de movimentações e não pode ser excluído. "
            "Use “Desativar” para retirá-lo das listas sem perder o histórico.",
            "erro",
        )
        return redirect(url_for("produtos.lista"))
    db.session.delete(produto)
    db.session.commit()
    flash(f"Produto “{produto.nome}” excluído.", "sucesso")
    return redirect(url_for("produtos.lista"))


@bp.route("/<int:produto_id>/desativar", methods=["POST"])
def desativar(produto_id):
    produto = obter_ou_404(Produto, produto_id)
    saldo = saldo_produto(produto.id)
    if saldo > 0:
        flash(
            f"“{produto.nome}” ainda tem estoque. Registre a venda ou a perda do saldo antes de desativá-lo.",
            "erro",
        )
    else:
        produto.ativo = False
        db.session.commit()
        flash(f"Produto “{produto.nome}” desativado. O histórico foi preservado.", "sucesso")
    return redirect(url_for("produtos.lista"))


@bp.route("/<int:produto_id>/reativar", methods=["POST"])
def reativar(produto_id):
    produto = obter_ou_404(Produto, produto_id)
    produto.ativo = True
    db.session.commit()
    flash(f"Produto “{produto.nome}” reativado.", "sucesso")
    return redirect(url_for("produtos.lista", situacao="ativos"))
