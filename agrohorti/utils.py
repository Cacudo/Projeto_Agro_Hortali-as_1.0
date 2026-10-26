"""Conversão e validação de dados de formulário e formatação para exibição."""
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")
MILESIMO = Decimal("0.001")
LIMITE_VALOR = Decimal("1000000")


class ErroValidacao(ValueError):
    """Dado informado pelo usuário é inválido. A mensagem é exibida na tela."""


def normalizar_nome(nome):
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def texto(valor, campo, obrigatorio=True, maximo=200, multilinha=False):
    valor = (valor or "").strip() if multilinha else " ".join((valor or "").split())
    if obrigatorio and not valor:
        raise ErroValidacao(f"Informe {campo}.")
    if len(valor) > maximo:
        raise ErroValidacao(f"{campo.capitalize()} deve ter no máximo {maximo} caracteres.")
    return valor or None


def decimal(valor, campo, obrigatorio=True, casas=CENTAVO, minimo=Decimal("0"), permitir_zero=True):
    bruto = (valor or "").strip().replace(" ", "")
    if not bruto:
        if obrigatorio:
            raise ErroValidacao(f"Informe {campo}.")
        return None
    # Aceita "1.234,56", "1234,56" e "1234.56".
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(bruto)
    except InvalidOperation:
        raise ErroValidacao(f"{campo.capitalize()} deve ser um número.") from None
    if not numero.is_finite():
        raise ErroValidacao(f"{campo.capitalize()} deve ser um número.")
    if abs(numero) >= LIMITE_VALOR:
        raise ErroValidacao(f"{campo.capitalize()} é grande demais.")
    numero = numero.quantize(casas, rounding=ROUND_HALF_UP)
    if numero < minimo:
        raise ErroValidacao(f"{campo.capitalize()} não pode ser negativo.")
    if not permitir_zero and numero == 0:
        raise ErroValidacao(f"{campo.capitalize()} deve ser maior que zero.")
    return numero


def quantidade(valor, campo="a quantidade", fracionavel=True):
    numero = decimal(valor, campo, casas=MILESIMO, permitir_zero=False)
    if not fracionavel and numero != numero.to_integral_value():
        raise ErroValidacao(f"{campo.capitalize()} deve ser um número inteiro para esta unidade.")
    return numero


def inteiro(valor, campo, obrigatorio=True, minimo=1):
    bruto = (valor or "").strip()
    if not bruto:
        if obrigatorio:
            raise ErroValidacao(f"Informe {campo}.")
        return None
    try:
        numero = int(bruto)
    except ValueError:
        raise ErroValidacao(f"{campo.capitalize()} deve ser um número inteiro.") from None
    if numero < minimo or numero > 3650:
        raise ErroValidacao(f"{campo.capitalize()} deve estar entre {minimo} e 3650.")
    return numero


def data(valor, campo="a data", permitir_futuro=False):
    try:
        resultado = date.fromisoformat((valor or "").strip())
    except ValueError:
        raise ErroValidacao(f"Informe {campo} em formato válido.") from None
    if not permitir_futuro and resultado > date.today():
        raise ErroValidacao(f"{campo.capitalize()} não pode estar no futuro.")
    if resultado.year < 2000:
        raise ErroValidacao(f"{campo.capitalize()} é inválida.")
    return resultado


def data_hora(valor, campo="a data e hora"):
    try:
        resultado = datetime.fromisoformat((valor or "").strip())
    except ValueError:
        raise ErroValidacao(f"Informe {campo} em formato válido.") from None
    if resultado.tzinfo is not None:
        resultado = resultado.replace(tzinfo=None)
    if resultado > datetime.now().replace(second=59, microsecond=999999):
        raise ErroValidacao(f"{campo.capitalize()} não pode estar no futuro.")
    if resultado.year < 2000:
        raise ErroValidacao(f"{campo.capitalize()} é inválida.")
    return resultado


def data_filtro(valor):
    """Datas de filtros de relatório: valor inválido é simplesmente ignorado."""
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- formatação

def _milhar(numero, casas):
    formatado = f"{numero:,.{casas}f}"
    return formatado.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_moeda(valor):
    if valor is None:
        return "—"
    return "R$ " + _milhar(Decimal(valor), 2)


def formatar_qtd(valor, unidade=None):
    if valor is None:
        return "—"
    numero = Decimal(valor).quantize(MILESIMO)
    casas = 0 if numero == numero.to_integral_value() else 3
    texto_numero = _milhar(numero, casas)
    if casas:
        texto_numero = texto_numero.rstrip("0")
    return f"{texto_numero} {unidade}" if unidade else texto_numero


def formatar_data(valor):
    if valor is None:
        return "—"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    return valor.strftime("%d/%m/%Y")


def formatar_percentual(valor):
    if valor is None:
        return "—"
    return _milhar(Decimal(valor), 1) + "%"
