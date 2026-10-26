from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..extensions import db
from ..models import Usuario
from ..utils import ErroValidacao
from . import obter_ou_404
from .auth import criar_usuario, validar_senha

bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")


@bp.route("/")
def index():
    usuarios = db.session.scalars(select(Usuario).order_by(Usuario.nome)).all()
    return render_template("configuracoes.html", usuarios=usuarios, dados={})


@bp.route("/senha", methods=["POST"])
def alterar_senha():
    try:
        if not g.usuario.verificar_senha(request.form.get("senha_atual") or ""):
            raise ErroValidacao("A senha atual está incorreta.")
        validar_senha(request.form.get("senha"), request.form.get("confirmacao"))
    except ErroValidacao as erro:
        flash(str(erro), "erro")
    else:
        g.usuario.definir_senha(request.form.get("senha"))
        db.session.commit()
        flash("Senha alterada com sucesso.", "sucesso")
    return redirect(url_for("configuracoes.index"))


@bp.route("/usuarios", methods=["POST"])
def novo_usuario():
    try:
        usuario = criar_usuario(request.form)
    except ErroValidacao as erro:
        flash(str(erro), "erro")
        usuarios = db.session.scalars(select(Usuario).order_by(Usuario.nome)).all()
        return render_template("configuracoes.html", usuarios=usuarios, dados=request.form), 400
    flash(f"Usuário {usuario.nome} criado. Ele já pode entrar com o e-mail e a senha informados.", "sucesso")
    return redirect(url_for("configuracoes.index"))


@bp.route("/usuarios/<int:usuario_id>/alternar", methods=["POST"])
def alternar_usuario(usuario_id):
    usuario = obter_ou_404(Usuario, usuario_id)
    if usuario.id == g.usuario.id:
        flash("Você não pode desativar o seu próprio acesso.", "erro")
    else:
        usuario.ativo = not usuario.ativo
        db.session.commit()
        flash(f"Acesso de {usuario.nome} {'reativado' if usuario.ativo else 'desativado'}.", "sucesso")
    return redirect(url_for("configuracoes.index"))
