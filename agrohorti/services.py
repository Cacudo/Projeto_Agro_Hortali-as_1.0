"""Regras de negócio que alteram o estoque.

Toda operação roda em uma única transação: ou tudo é gravado (registro +
movimentações de estoque), ou nada é gravado. Assim uma venda nunca fica
registrada sem a baixa de estoque correspondente, e vice-versa.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import wraps

from sqlalchemy import func, select

from .extensions import db
from .models import MOTIVOS_PERDA, Colheita, Movimentacao, Perda, Venda, VendaItem
from .utils import CENTAVO, MILESIMO, ErroValidacao, formatar_qtd

ZERO = Decimal("0")


def _dec(valor):
    if valor is None:
        return ZERO
    return Decimal(str(valor)).quantize(MILESIMO)


def transacao(funcao):
    @wraps(funcao)
    def executar(*args, **kwargs):
        try:
            resultado = funcao(*args, **kwargs)
            db.session.commit()
            return resultado
        except Exception:
            db.session.rollback()
            raise

    return executar


def _momento(dia):
    """Converte a data de um evento em data/hora para o histórico de movimentações."""
    agora = datetime.now()
    if dia == agora.date():
        return agora.replace(microsecond=0)
    return datetime.combine(dia, time(12, 0))


# ----------------------------------------------------------------- consultas

def saldo_produto(produto_id):
    total = db.session.scalar(
        select(func.sum(Movimentacao.quantidade)).where(Movimentacao.produto_id == produto_id)
    )
    return _dec(total)


def saldos_por_produto():
    linhas = db.session.execute(
        select(Movimentacao.produto_id, func.sum(Movimentacao.quantidade)).group_by(Movimentacao.produto_id)
    )
    return {produto_id: _dec(total) for produto_id, total in linhas}


def lotes_com_saldo(produto_id=None):
    """Lotes (colheitas) com saldo positivo, na ordem em que devem sair: validade mais próxima primeiro."""
    saldo = func.sum(Movimentacao.quantidade)
    consulta = (
        select(Colheita, saldo)
        .join(Movimentacao, Movimentacao.colheita_id == Colheita.id)
        .group_by(Colheita.id)
        .having(saldo > 0)
        .order_by(Colheita.validade.is_(None), Colheita.validade, Colheita.data, Colheita.id)
    )
    if produto_id is not None:
        consulta = consulta.where(Colheita.produto_id == produto_id)
    return [(colheita, _dec(total)) for colheita, total in db.session.execute(consulta)]


def saldo_lote(colheita_id):
    total = db.session.scalar(
        select(func.sum(Movimentacao.quantidade)).where(Movimentacao.colheita_id == colheita_id)
    )
    return _dec(total)


def _baixar_estoque(produto, quantidade, tipo, quando, colheita=None, venda_item=None, perda=None):
    """Registra saídas de estoque, lote a lote. Nunca deixa saldo negativo."""
    if colheita is not None:
        disponivel = saldo_lote(colheita.id)
        if disponivel < quantidade:
            raise ErroValidacao(
                f"O lote {colheita.lote} de {produto.nome} tem apenas "
                f"{formatar_qtd(disponivel, produto.unidade)} disponível."
            )
        lotes = [(colheita, disponivel)]
    else:
        lotes = lotes_com_saldo(produto.id)
        disponivel = sum((saldo for _, saldo in lotes), ZERO)
        if disponivel < quantidade:
            raise ErroValidacao(
                f"Estoque insuficiente de {produto.nome}: disponível "
                f"{formatar_qtd(disponivel, produto.unidade)}, solicitado "
                f"{formatar_qtd(quantidade, produto.unidade)}."
            )

    restante = quantidade
    for lote, saldo in lotes:
        if restante <= 0:
            break
        usar = min(saldo, restante)
        db.session.add(
            Movimentacao(
                produto_id=produto.id,
                colheita_id=lote.id,
                tipo=tipo,
                quantidade=-usar,
                data=quando,
                venda_item=venda_item,
                perda=perda,
            )
        )
        restante -= usar


def _estornar(movimentacoes, tipo_estorno):
    agora = datetime.now().replace(microsecond=0)
    for mov in movimentacoes:
        db.session.add(
            Movimentacao(
                produto_id=mov.produto_id,
                colheita_id=mov.colheita_id,
                tipo=tipo_estorno,
                quantidade=-mov.quantidade,
                data=agora,
                venda_item_id=mov.venda_item_id,
                perda_id=mov.perda_id,
            )
        )


# ----------------------------------------------------------------- colheitas

@transacao
def registrar_colheita(produto, quantidade, dia, lote=None, observacoes=None, usuario=None):
    if not produto.ativo:
        raise ErroValidacao("Este produto está desativado. Reative-o antes de registrar colheitas.")
    validade = dia + timedelta(days=produto.validade_dias) if produto.validade_dias else None
    colheita = Colheita(
        produto=produto,
        quantidade=quantidade,
        data=dia,
        lote=lote or "",
        validade=validade,
        observacoes=observacoes,
        criado_por_id=usuario.id if usuario else None,
    )
    db.session.add(colheita)
    db.session.flush()
    if not lote:
        colheita.lote = f"L{dia:%Y%m%d}-{colheita.id}"
    db.session.add(
        Movimentacao(
            produto_id=produto.id,
            colheita_id=colheita.id,
            tipo="entrada_colheita",
            quantidade=quantidade,
            data=_momento(dia),
        )
    )
    return colheita


@transacao
def excluir_colheita(colheita):
    """Permite corrigir um lançamento errado, desde que o lote ainda não tenha sido usado."""
    usos = db.session.scalar(
        select(func.count(Movimentacao.id)).where(
            Movimentacao.colheita_id == colheita.id, Movimentacao.tipo != "entrada_colheita"
        )
    )
    if usos:
        raise ErroValidacao(
            f"O lote {colheita.lote} já tem vendas ou perdas registradas e não pode ser excluído. "
            "Para corrigir o estoque, cancele as vendas/perdas envolvidas ou registre uma perda."
        )
    db.session.execute(db.delete(Movimentacao).where(Movimentacao.colheita_id == colheita.id))
    db.session.delete(colheita)


# -------------------------------------------------------------------- perdas

@transacao
def registrar_perda(produto, quantidade, dia, motivo, colheita=None, observacoes=None, usuario=None):
    if motivo not in MOTIVOS_PERDA:
        raise ErroValidacao("Selecione um motivo de perda válido.")
    if motivo == "outros" and not observacoes:
        raise ErroValidacao("Descreva o motivo nas observações quando escolher “Outros motivos”.")
    if colheita is not None:
        if colheita.produto_id != produto.id:
            raise ErroValidacao("O lote selecionado não pertence a este produto.")
        if dia < colheita.data:
            raise ErroValidacao("A data da perda não pode ser anterior à colheita do lote.")
    perda = Perda(
        produto=produto,
        colheita=colheita,
        quantidade=quantidade,
        data=dia,
        motivo=motivo,
        observacoes=observacoes,
        preco_unitario=produto.preco_venda,
        custo_unitario=produto.custo_unitario,
        criado_por_id=usuario.id if usuario else None,
    )
    db.session.add(perda)
    db.session.flush()
    _baixar_estoque(produto, quantidade, "saida_perda", _momento(dia), colheita=colheita, perda=perda)
    return perda


@transacao
def cancelar_perda(perda, motivo):
    if perda.cancelada:
        raise ErroValidacao("Esta perda já foi cancelada.")
    movimentacoes = db.session.scalars(
        select(Movimentacao).where(Movimentacao.perda_id == perda.id, Movimentacao.tipo == "saida_perda")
    ).all()
    _estornar(movimentacoes, "estorno_perda")
    perda.cancelada = True
    perda.cancelada_em = datetime.now().replace(microsecond=0)
    perda.motivo_cancelamento = motivo


# -------------------------------------------------------------------- vendas

@transacao
def registrar_venda(itens, desconto, quando, observacoes=None, usuario=None):
    """`itens`: lista de (produto, quantidade, preco_unitario). Todos os valores são calculados aqui."""
    if not itens:
        raise ErroValidacao("Adicione pelo menos um produto à venda.")
    vistos = set()
    for produto, _, _ in itens:
        if produto.id in vistos:
            raise ErroValidacao(f"{produto.nome} aparece mais de uma vez. Junte as quantidades em uma linha.")
        if not produto.ativo:
            raise ErroValidacao(f"{produto.nome} está desativado e não pode ser vendido.")
        vistos.add(produto.id)

    subtotais = [(quantidade * preco).quantize(CENTAVO) for _, quantidade, preco in itens]
    subtotal = sum(subtotais, Decimal("0.00"))
    if desconto > subtotal:
        raise ErroValidacao("O desconto não pode ser maior que o subtotal da venda.")

    venda = Venda(
        data_hora=quando,
        subtotal=subtotal,
        desconto=desconto,
        total=subtotal - desconto,
        observacoes=observacoes,
        criado_por_id=usuario.id if usuario else None,
    )
    db.session.add(venda)
    for (produto, quantidade, preco), valor in zip(itens, subtotais):
        item = VendaItem(
            venda=venda,
            produto=produto,
            quantidade=quantidade,
            preco_unitario=preco,
            subtotal=valor,
            custo_unitario=produto.custo_unitario,
        )
        db.session.add(item)
        db.session.flush()
        _baixar_estoque(produto, quantidade, "saida_venda", quando, venda_item=item)
    return venda


@transacao
def cancelar_venda(venda, motivo):
    if venda.cancelada:
        raise ErroValidacao("Esta venda já foi cancelada.")
    ids_itens = [item.id for item in venda.itens]
    movimentacoes = db.session.scalars(
        select(Movimentacao).where(
            Movimentacao.venda_item_id.in_(ids_itens), Movimentacao.tipo == "saida_venda"
        )
    ).all()
    _estornar(movimentacoes, "estorno_venda")
    venda.cancelada = True
    venda.cancelada_em = datetime.now().replace(microsecond=0)
    venda.motivo_cancelamento = motivo


def produto_tem_historico(produto_id):
    return bool(
        db.session.scalar(select(func.count(Movimentacao.id)).where(Movimentacao.produto_id == produto_id))
        or db.session.scalar(select(func.count(VendaItem.id)).where(VendaItem.produto_id == produto_id))
    )
