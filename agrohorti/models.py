"""Modelos do banco de dados do AgroHorti.

Regra central: o saldo de estoque NÃO é guardado em nenhuma coluna. Ele é
sempre calculado a partir da tabela `movimentacoes` (livro-razão), que recebe
uma linha para cada entrada (colheita) e cada saída (venda, perda) ou estorno.
Assim existe uma única fonte de verdade sobre a quantidade disponível.
"""
from datetime import datetime
from decimal import Decimal

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

QTD = db.Numeric(12, 3)
DINHEIRO = db.Numeric(12, 2)

CATEGORIAS = [
    "Folhosas",
    "Temperos e ervas",
    "Frutos",
    "Legumes",
    "Raízes e tubérculos",
    "Outros",
]

# unidade -> (rótulo, aceita quantidades fracionadas?)
UNIDADES = {
    "kg": ("Quilograma (kg)", True),
    "maço": ("Maço", False),
    "unidade": ("Unidade", False),
    "pé": ("Pé", False),
    "dúzia": ("Dúzia", False),
    "bandeja": ("Bandeja", False),
    "caixa": ("Caixa", False),
}

MOTIVOS_PERDA = {
    "deterioracao": "Deterioração",
    "apodrecimento": "Apodrecimento",
    "transporte": "Danos durante o transporte",
    "armazenamento": "Problemas de armazenamento",
    "excesso": "Excesso de produção",
    "outros": "Outros motivos",
}

TIPOS_MOVIMENTACAO = {
    "entrada_colheita": "Entrada (colheita)",
    "saida_venda": "Saída (venda)",
    "saida_perda": "Saída (perda)",
    "estorno_venda": "Estorno de venda",
    "estorno_perda": "Estorno de perda",
}


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Produto(db.Model):
    __tablename__ = "produtos"
    __table_args__ = (
        db.CheckConstraint("preco_venda >= 0", name="ck_produto_preco"),
        db.CheckConstraint("custo_unitario IS NULL OR custo_unitario >= 0", name="ck_produto_custo"),
        db.CheckConstraint("estoque_minimo >= 0", name="ck_produto_minimo"),
        db.CheckConstraint("validade_dias IS NULL OR validade_dias > 0", name="ck_produto_validade"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    # Nome em minúsculas e sem acentos: impede "Alface" e "alface" duplicados.
    nome_normalizado = db.Column(db.String(80), nullable=False, unique=True)
    categoria = db.Column(db.String(40), nullable=False)
    unidade = db.Column(db.String(20), nullable=False)
    preco_venda = db.Column(DINHEIRO, nullable=False)
    custo_unitario = db.Column(DINHEIRO, nullable=True)
    estoque_minimo = db.Column(QTD, nullable=False, default=0)
    conservacao = db.Column(db.Text, nullable=True)
    validade_dias = db.Column(db.Integer, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def fracionavel(self):
        return UNIDADES.get(self.unidade, ("", True))[1]


class Colheita(db.Model):
    """Cada colheita forma um lote de estoque."""

    __tablename__ = "colheitas"
    __table_args__ = (db.CheckConstraint("quantidade > 0", name="ck_colheita_qtd"),)

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    quantidade = db.Column(QTD, nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    lote = db.Column(db.String(40), nullable=False)
    validade = db.Column(db.Date, nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    produto = db.relationship("Produto")


class Venda(db.Model):
    __tablename__ = "vendas"
    __table_args__ = (
        db.CheckConstraint("desconto >= 0", name="ck_venda_desconto"),
        db.CheckConstraint("total >= 0", name="ck_venda_total"),
    )

    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, nullable=False, index=True)
    subtotal = db.Column(DINHEIRO, nullable=False)
    desconto = db.Column(DINHEIRO, nullable=False, default=0)
    total = db.Column(DINHEIRO, nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    cancelada = db.Column(db.Boolean, nullable=False, default=False)
    cancelada_em = db.Column(db.DateTime, nullable=True)
    motivo_cancelamento = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    itens = db.relationship("VendaItem", back_populates="venda", order_by="VendaItem.id")


class VendaItem(db.Model):
    __tablename__ = "venda_itens"
    __table_args__ = (
        db.CheckConstraint("quantidade > 0", name="ck_item_qtd"),
        db.CheckConstraint("preco_unitario >= 0", name="ck_item_preco"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey("vendas.id"), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    quantidade = db.Column(QTD, nullable=False)
    preco_unitario = db.Column(DINHEIRO, nullable=False)
    subtotal = db.Column(DINHEIRO, nullable=False)
    # Custo copiado do produto no momento da venda (histórico não muda se o custo mudar).
    custo_unitario = db.Column(DINHEIRO, nullable=True)

    venda = db.relationship("Venda", back_populates="itens")
    produto = db.relationship("Produto")


class Perda(db.Model):
    __tablename__ = "perdas"
    __table_args__ = (db.CheckConstraint("quantidade > 0", name="ck_perda_qtd"),)

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    # Lote informado pelo usuário (opcional). Sem lote, a baixa segue a ordem de validade.
    colheita_id = db.Column(db.Integer, db.ForeignKey("colheitas.id"), nullable=True)
    quantidade = db.Column(QTD, nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    motivo = db.Column(db.String(20), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    # Valores copiados do produto no momento do registro, usados nas estimativas.
    preco_unitario = db.Column(DINHEIRO, nullable=False)
    custo_unitario = db.Column(DINHEIRO, nullable=True)
    cancelada = db.Column(db.Boolean, nullable=False, default=False)
    cancelada_em = db.Column(db.DateTime, nullable=True)
    motivo_cancelamento = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    produto = db.relationship("Produto")
    colheita = db.relationship("Colheita")

    @property
    def motivo_rotulo(self):
        return MOTIVOS_PERDA.get(self.motivo, self.motivo)


class Movimentacao(db.Model):
    """Livro-razão do estoque: quantidade positiva = entrada, negativa = saída."""

    __tablename__ = "movimentacoes"

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    colheita_id = db.Column(db.Integer, db.ForeignKey("colheitas.id"), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    quantidade = db.Column(QTD, nullable=False)
    data = db.Column(db.DateTime, nullable=False, index=True)
    venda_item_id = db.Column(db.Integer, db.ForeignKey("venda_itens.id"), nullable=True)
    perda_id = db.Column(db.Integer, db.ForeignKey("perdas.id"), nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    produto = db.relationship("Produto")
    colheita = db.relationship("Colheita")
    venda_item = db.relationship("VendaItem")
    perda = db.relationship("Perda")

    @property
    def tipo_rotulo(self):
        return TIPOS_MOVIMENTACAO.get(self.tipo, self.tipo)


class Pulverizacao(db.Model):
    """Módulo herdado da versão anterior: cálculo do volume de calda por talhão."""

    __tablename__ = "pulverizacoes"
    __table_args__ = (
        db.CheckConstraint("area_ha > 0", name="ck_pulv_area"),
        db.CheckConstraint("dosagem_l_ha > 0", name="ck_pulv_dosagem"),
    )

    id = db.Column(db.Integer, primary_key=True)
    talhao = db.Column(db.String(80), nullable=False)
    cultura = db.Column(db.String(80), nullable=False)
    area_ha = db.Column(db.Numeric(10, 2), nullable=False)
    dosagem_l_ha = db.Column(db.Numeric(10, 2), nullable=False)
    data = db.Column(db.Date, nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def volume_total(self):
        # Calculado sempre a partir dos dados, para nunca divergir deles.
        return (Decimal(self.area_ha) * Decimal(self.dosagem_l_ha)).quantize(Decimal("0.01"))
