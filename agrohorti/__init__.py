import hmac
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, abort, render_template, request, session

from .extensions import db
from .models import CATEGORIAS, MOTIVOS_PERDA, TIPOS_MOVIMENTACAO, UNIDADES
from .utils import formatar_data, formatar_moeda, formatar_percentual, formatar_qtd


def _chave_secreta(pasta_instancia):
    """Usa AGROHORTI_SECRET_KEY; sem ela, gera uma chave aleatória e a guarda em instance/.

    A chave nunca fica no código-fonte e continua a mesma após reiniciar o servidor.
    """
    chave = os.environ.get("AGROHORTI_SECRET_KEY")
    if chave:
        return chave
    arquivo = Path(pasta_instancia) / "secret_key"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8").strip()
    chave = secrets.token_hex(32)
    arquivo.write_text(chave, encoding="utf-8")
    return chave


def create_app(config=None):
    raiz = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_path=str(raiz / "instance"),
        template_folder=str(raiz / "templates"),
        static_folder=str(raiz / "static"),
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    banco_padrao = "sqlite:///" + str(Path(app.instance_path) / "agrohorti.db")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get("AGROHORTI_DATABASE_URL", banco_padrao),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        CSRF_ATIVO=True,
        ITENS_POR_PAGINA=25,
    )
    if config:
        app.config.update(config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _chave_secreta(app.instance_path)

    db.init_app(app)

    from .rotas import registrar_blueprints

    registrar_blueprints(app)
    _configurar_csrf(app)
    _configurar_templates(app)
    _configurar_erros(app)

    with app.app_context():
        # Cria as tabelas que ainda não existem. Nunca apaga tabelas nem dados.
        db.create_all()

    return app


def _configurar_csrf(app):
    def gerar_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.before_request
    def verificar_csrf():
        if request.method != "POST" or not app.config["CSRF_ATIVO"]:
            return
        esperado = session.get("_csrf", "")
        recebido = request.form.get("csrf_token", "")
        if not esperado or not hmac.compare_digest(esperado, recebido):
            abort(400, description="Formulário expirado ou inválido. Recarregue a página e tente novamente.")

    app.jinja_env.globals["csrf_token"] = gerar_token


def _configurar_templates(app):
    app.jinja_env.filters.update(
        moeda=formatar_moeda,
        qtd=formatar_qtd,
        data_br=formatar_data,
        percentual=formatar_percentual,
    )
    app.jinja_env.globals.update(
        CATEGORIAS=CATEGORIAS,
        UNIDADES=UNIDADES,
        MOTIVOS_PERDA=MOTIVOS_PERDA,
        TIPOS_MOVIMENTACAO=TIPOS_MOVIMENTACAO,
    )

    @app.context_processor
    def datas():
        return {"hoje": date.today(), "agora": datetime.now()}


def _configurar_erros(app):
    @app.errorhandler(400)
    def requisicao_invalida(erro):
        return render_template("erro.html", codigo=400, mensagem=erro.description), 400

    @app.errorhandler(404)
    def nao_encontrado(erro):
        return render_template("erro.html", codigo=404, mensagem="Página ou registro não encontrado."), 404

    @app.errorhandler(500)
    def erro_interno(erro):
        db.session.rollback()
        return render_template(
            "erro.html", codigo=500, mensagem="Ocorreu um erro inesperado. Nenhum dado parcial foi gravado."
        ), 500
