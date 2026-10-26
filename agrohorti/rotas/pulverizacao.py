"""Módulo de pulverização herdado da versão anterior do projeto.

Mantém a funcionalidade original (volume de calda = área x dosagem), agora com
dados salvos no banco, validação e edição.
"""
from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from ..extensions import db
from ..models import Pulverizacao
from ..utils import ErroValidacao, data, decimal, formatar_qtd, texto
from . import obter_ou_404

bp = Blueprint("pulverizacao", __name__, url_prefix="/pulverizacao")


def _ler_formulario(form):
    return {
        "talhao": texto(form.get("talhao"), "o nome do talhão", maximo=80),
        "cultura": texto(form.get("cultura"), "a cultura", maximo=80),
        "area_ha": decimal(form.get("area_ha"), "a área", permitir_zero=False),
        "dosagem_l_ha": decimal(form.get("dosagem_l_ha"), "a dosagem", permitir_zero=False),
        "data": data(form.get("data"), "a data da aplicação"),
        "observacoes": texto(form.get("observacoes"), "as observações", obrigatorio=False,
                             maximo=500, multilinha=True),
    }


@bp.route("/", methods=["GET", "POST"])
def index():
    dados = {"data": date.today().isoformat()}
    status = 200
    if request.method == "POST":
        try:
            registro = Pulverizacao(**_ler_formulario(request.form))
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            dados, status = request.form, 400
        else:
            db.session.add(registro)
            db.session.commit()
            flash(f"Aplicação registrada: {formatar_qtd(registro.volume_total, 'L')} de calda para {registro.talhao}.", "sucesso")
            return redirect(url_for("pulverizacao.index"))

    registros = db.session.scalars(
        select(Pulverizacao).order_by(Pulverizacao.data.desc(), Pulverizacao.id.desc())
    ).all()
    return render_template(
        "pulverizacao/index.html",
        registros=registros,
        dados=dados,
        total_talhoes=len({r.talhao.lower() for r in registros}),
        total_area=sum((r.area_ha for r in registros), Decimal("0")),
        total_volume=sum((r.volume_total for r in registros), Decimal("0")),
    ), status


@bp.route("/<int:registro_id>/editar", methods=["GET", "POST"])
def editar(registro_id):
    registro = obter_ou_404(Pulverizacao, registro_id)
    if request.method == "POST":
        try:
            dados = _ler_formulario(request.form)
        except ErroValidacao as erro:
            flash(str(erro), "erro")
            return render_template("pulverizacao/editar.html", registro=registro, dados=request.form), 400
        for campo, valor in dados.items():
            setattr(registro, campo, valor)
        db.session.commit()
        flash("Registro de pulverização atualizado.", "sucesso")
        return redirect(url_for("pulverizacao.index"))
    dados = {
        "talhao": registro.talhao, "cultura": registro.cultura, "area_ha": registro.area_ha,
        "dosagem_l_ha": registro.dosagem_l_ha, "data": registro.data.isoformat(),
        "observacoes": registro.observacoes or "",
    }
    return render_template("pulverizacao/editar.html", registro=registro, dados=dados)


@bp.route("/<int:registro_id>/excluir", methods=["POST"])
def excluir(registro_id):
    registro = obter_ou_404(Pulverizacao, registro_id)
    db.session.delete(registro)
    db.session.commit()
    flash("Registro de pulverização excluído.", "sucesso")
    return redirect(url_for("pulverizacao.index"))
