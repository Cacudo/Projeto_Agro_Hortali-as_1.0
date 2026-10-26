from flask import Blueprint, current_app, render_template, request

from .. import consultas
from ..extensions import db
from ..models import TIPOS_MOVIMENTACAO
from ..services import lotes_com_saldo
from ..utils import data_filtro
from . import id_arg, todos_produtos

bp = Blueprint("estoque", __name__, url_prefix="/estoque")


@bp.route("/")
def index():
    produto_id = id_arg(request.args, "produto_id")
    tipo = request.args.get("tipo") if request.args.get("tipo") in TIPOS_MOVIMENTACAO else None
    inicio = data_filtro(request.args.get("inicio"))
    fim = data_filtro(request.args.get("fim"))
    if inicio and fim and inicio > fim:
        inicio, fim = fim, inicio

    historico = db.paginate(
        consultas.movimentacoes(inicio, fim, produto_id, tipo),
        per_page=current_app.config["ITENS_POR_PAGINA"],
        error_out=False,
    )
    situacao = consultas.situacao_estoque()
    return render_template(
        "estoque.html",
        situacao=situacao,
        lotes=lotes_com_saldo(produto_id),
        alertas_validade={a["colheita"].id: a for a in consultas.alertas_validade()},
        historico=historico,
        produtos=todos_produtos(),
        produto_id=produto_id,
        tipo=tipo or "",
        inicio=inicio,
        fim=fim,
        contagem={s: sum(1 for l in situacao if l["status"] == s) for s in ("ok", "baixo", "zerado")},
    )
