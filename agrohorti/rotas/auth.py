import re

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import func, select

from ..extensions import db
from ..models import Usuario
from ..utils import ErroValidacao, texto

bp = Blueprint("auth", __name__)

ENDPOINTS_PUBLICOS = {"auth.login", "auth.primeiro_acesso", "static"}
EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MINIMA = 8


def existe_usuario():
    return bool(db.session.scalar(select(func.count(Usuario.id))))


def validar_senha(senha, confirmacao):
    if len(senha or "") < SENHA_MINIMA:
        raise ErroValidacao(f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres.")
    if senha != confirmacao:
        raise ErroValidacao("A confirmação não confere com a senha.")


def criar_usuario(form):
    nome = texto(form.get("nome"), "o nome", maximo=80)
    email = texto(form.get("email"), "o e-mail", maximo=120).lower()
    if not EMAIL_VALIDO.match(email):
        raise ErroValidacao("Informe um e-mail válido.")
    if db.session.scalar(select(Usuario).where(Usuario.email == email)):
        raise ErroValidacao("Já existe um usuário com este e-mail.")
    validar_senha(form.get("senha"), form.get("confirmacao"))
    usuario = Usuario(nome=nome, email=email)
    usuario.definir_senha(form.get("senha"))
    db.session.add(usuario)
    db.session.commit()
    return usuario


def _destino_seguro(destino):
    # Só aceita caminhos internos, evitando redirecionamento para sites externos.
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return url_for("painel.index")


@bp.before_app_request
def exigir_login():
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id:
        usuario = db.session.get(Usuario, usuario_id)
        if usuario and usuario.ativo:
            g.usuario = usuario
        else:
            session.clear()

    if request.endpoint in ENDPOINTS_PUBLICOS or request.endpoint is None or g.usuario:
        return None
    if not existe_usuario():
        return redirect(url_for("auth.primeiro_acesso"))
    proximo = request.full_path.rstrip("?") if request.method == "GET" else None
    return redirect(url_for("auth.login", next=proximo))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not existe_usuario():
        return redirect(url_for("auth.primeiro_acesso"))
    if g.usuario:
        return redirect(url_for("painel.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        usuario = db.session.scalar(select(Usuario).where(Usuario.email == email))
        if usuario and usuario.ativo and usuario.verificar_senha(senha):
            session.clear()
            session["usuario_id"] = usuario.id
            session.permanent = True
            return redirect(_destino_seguro(request.args.get("next")))
        # Mensagem única: não revela se o e-mail existe.
        flash("E-mail ou senha incorretos.", "erro")
        return render_template("auth/login.html", email=email), 401

    return render_template("auth/login.html", email="")


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    """Cadastro do primeiro usuário. Depois disso, novos usuários são criados em Configurações."""
    if existe_usuario():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        try:
            usuario = criar_usuario(request.form)
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("auth/primeiro_acesso.html", dados=request.form), 400
        session.clear()
        session["usuario_id"] = usuario.id
        session.permanent = True
        flash(f"Bem-vindo(a), {usuario.nome}! Comece cadastrando seus produtos.", "sucesso")
        return redirect(url_for("produtos.lista"))
    return render_template("auth/primeiro_acesso.html", dados={})


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("auth.login"))
