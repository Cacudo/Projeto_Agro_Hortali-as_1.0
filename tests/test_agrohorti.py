"""Testes das regras de negócio e das rotas do AgroHorti.

Executar na pasta do projeto:  python -m unittest discover -s tests -v
"""
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from agrohorti import consultas, create_app
from agrohorti.extensions import db
from agrohorti.models import Colheita, Movimentacao, Perda, Produto, Pulverizacao, Usuario, Venda
from agrohorti.services import saldo_produto
from agrohorti.utils import ErroValidacao, decimal, formatar_moeda, formatar_qtd

HOJE = date.today()


class BaseTeste(unittest.TestCase):
    csrf = False

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.banco = "sqlite:///" + str(Path(self.pasta) / "teste.db")
        self.app = self.criar_app()
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        usuario = Usuario(nome="Maria", email="maria@exemplo.com")
        usuario.definir_senha("senha-segura")
        db.session.add(usuario)
        db.session.commit()
        self.entrar()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        with self.app.app_context():
            db.engine.dispose()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def criar_app(self):
        return create_app({
            "TESTING": True,
            "SECRET_KEY": "chave-de-teste",
            "SQLALCHEMY_DATABASE_URI": self.banco,
            "CSRF_ATIVO": self.csrf,
        })

    def entrar(self, email="maria@exemplo.com", senha="senha-segura"):
        return self.client.post("/login", data={"email": email, "senha": senha})

    # ---- atalhos
    def produto(self, nome="Alface", unidade="maço", preco="3.00", custo="1.00", minimo="5", validade="3"):
        resposta = self.client.post("/produtos/novo", data={
            "nome": nome, "categoria": "Folhosas", "unidade": unidade, "preco_venda": preco,
            "custo_unitario": custo, "estoque_minimo": minimo, "validade_dias": validade,
        })
        self.assertEqual(resposta.status_code, 302, resposta.get_data(as_text=True)[:500])
        return db.session.scalar(select(Produto).where(Produto.nome == nome))

    def colher(self, produto, quantidade, dia=None, lote=""):
        return self.client.post("/colheitas/nova", data={
            "produto_id": produto.id, "quantidade": str(quantidade),
            "data": (dia or HOJE).isoformat(), "lote": lote,
        })

    def vender(self, itens, desconto="0", quando=None):
        dados = {
            "produto_id": [str(p.id) for p, _, _ in itens],
            "quantidade": [str(q) for _, q, _ in itens],
            "preco_unitario": [str(v) for _, _, v in itens],
            "desconto": desconto,
            "data_hora": (quando or datetime.now()).strftime("%Y-%m-%dT%H:%M"),
        }
        return self.client.post("/vendas/nova", data=dados)

    def perder(self, produto, quantidade, motivo="deterioracao", colheita=None, obs="", dia=None):
        return self.client.post("/perdas/nova", data={
            "produto_id": produto.id, "quantidade": str(quantidade), "motivo": motivo,
            "colheita_id": colheita.id if colheita else "", "observacoes": obs,
            "data": (dia or HOJE).isoformat(),
        })

    def saldo(self, produto):
        db.session.expire_all()
        return saldo_produto(produto.id)


class TestAutenticacao(BaseTeste):
    def test_rotas_privadas_exigem_login(self):
        self.client.post("/logout")
        for url in ("/", "/produtos/", "/vendas/nova", "/relatorios/", "/estoque/", "/pulverizacao/"):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302, url)
            self.assertIn("/login", resposta.headers["Location"])

    def test_login_com_senha_errada_e_recusado(self):
        self.client.post("/logout")
        resposta = self.entrar(senha="errada")
        self.assertEqual(resposta.status_code, 401)
        self.assertIn("E-mail ou senha incorretos", resposta.get_data(as_text=True))
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_senha_guardada_com_hash(self):
        usuario = db.session.scalar(select(Usuario))
        self.assertNotIn("senha-segura", usuario.senha_hash)
        self.assertTrue(usuario.verificar_senha("senha-segura"))

    def test_redirecionamento_externo_bloqueado(self):
        self.client.post("/logout")
        resposta = self.client.post("/login?next=//site-malicioso.com",
                                    data={"email": "maria@exemplo.com", "senha": "senha-segura"})
        self.assertEqual(resposta.headers["Location"], "/")

    def test_primeiro_acesso_so_funciona_sem_usuarios(self):
        self.client.post("/logout")
        resposta = self.client.post("/primeiro-acesso", data={
            "nome": "Intruso", "email": "x@x.com", "senha": "12345678", "confirmacao": "12345678"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(db.session.scalar(select(func.count(Usuario.id))), 1)

    def test_usuario_desativado_perde_acesso(self):
        self.client.post("/configuracoes/usuarios", data={
            "nome": "João", "email": "joao@exemplo.com", "senha": "outra-senha", "confirmacao": "outra-senha"})
        joao = db.session.scalar(select(Usuario).where(Usuario.email == "joao@exemplo.com"))
        self.client.post(f"/configuracoes/usuarios/{joao.id}/alternar")
        self.client.post("/logout")
        self.assertEqual(self.entrar("joao@exemplo.com", "outra-senha").status_code, 401)


class TestPrimeiroAcesso(unittest.TestCase):
    def test_fluxo_sem_usuarios(self):
        pasta = tempfile.mkdtemp()
        app = create_app({"TESTING": True, "SECRET_KEY": "x", "CSRF_ATIVO": False,
                          "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(Path(pasta) / "a.db")})
        client = app.test_client()
        self.assertIn("/primeiro-acesso", client.get("/").headers["Location"])
        curta = client.post("/primeiro-acesso", data={"nome": "Ana", "email": "ana@x.com",
                                                      "senha": "123", "confirmacao": "123"})
        self.assertEqual(curta.status_code, 400)
        ok = client.post("/primeiro-acesso", data={"nome": "Ana", "email": "ana@x.com",
                                                   "senha": "12345678", "confirmacao": "12345678"})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(client.get("/").status_code, 200)
        with app.app_context():
            db.engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


class TestCsrf(BaseTeste):
    csrf = True

    def entrar(self, email="maria@exemplo.com", senha="senha-segura"):
        self.client.get("/login")
        with self.client.session_transaction() as sessao:
            token = sessao["_csrf"]
        return self.client.post("/login", data={"email": email, "senha": senha, "csrf_token": token})

    def test_post_sem_token_e_rejeitado(self):
        resposta = self.client.post("/produtos/novo", data={"nome": "Couve"})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(db.session.scalar(select(func.count(Produto.id))), 0)

    def test_post_com_token_funciona(self):
        self.client.get("/produtos/novo")
        with self.client.session_transaction() as sessao:
            token = sessao["_csrf"]
        resposta = self.client.post("/produtos/novo", data={
            "csrf_token": token, "nome": "Couve", "categoria": "Folhosas", "unidade": "maço", "preco_venda": "2.5"})
        self.assertEqual(resposta.status_code, 302)


class TestProdutos(BaseTeste):
    def test_cadastro_e_duplicidade(self):
        self.produto("Alface")
        for nome in ("alface", " ALFACE ", "Álface"):
            resposta = self.client.post("/produtos/novo", data={
                "nome": nome, "categoria": "Folhosas", "unidade": "maço", "preco_venda": "3"})
            self.assertEqual(resposta.status_code, 400, nome)
        self.assertEqual(db.session.scalar(select(func.count(Produto.id))), 1)

    def test_valores_invalidos_rejeitados(self):
        base = {"nome": "Tomate", "categoria": "Frutos", "unidade": "kg", "preco_venda": "8"}
        casos = [
            {"preco_venda": "-1"}, {"preco_venda": "0"}, {"preco_venda": "abc"}, {"custo_unitario": "-2"},
            {"estoque_minimo": "-1"}, {"categoria": "Inventada"}, {"unidade": "tonelada"}, {"nome": "  "},
            {"validade_dias": "0"}, {"preco_venda": "NaN"},
        ]
        for caso in casos:
            resposta = self.client.post("/produtos/novo", data={**base, **caso})
            self.assertEqual(resposta.status_code, 400, caso)
        self.assertEqual(db.session.scalar(select(func.count(Produto.id))), 0)

    def test_aceita_virgula_decimal(self):
        self.assertEqual(decimal("1.234,56", "x"), Decimal("1234.56"))
        self.assertEqual(decimal("3,5", "x"), Decimal("3.50"))

    def test_busca_e_filtro(self):
        self.produto("Alface")
        self.produto("Cenoura", unidade="kg")
        self.client.get("/produtos/")  # consome as mensagens de sucesso, que citam os nomes
        html = self.client.get("/produtos/?q=alf").get_data(as_text=True)
        self.assertIn("Alface", html)
        self.assertNotIn("Cenoura", html)

    def test_exclusao_so_sem_historico(self):
        livre = self.produto("Coentro")
        self.client.post(f"/produtos/{livre.id}/excluir")
        self.assertIsNone(db.session.get(Produto, livre.id))

        usado = self.produto("Couve")
        self.colher(usado, 5)
        self.client.post(f"/produtos/{usado.id}/excluir")
        self.assertIsNotNone(db.session.get(Produto, usado.id))

    def test_desativar_exige_estoque_zerado(self):
        p = self.produto("Couve")
        self.colher(p, 5)
        self.client.post(f"/produtos/{p.id}/desativar")
        db.session.refresh(p)
        self.assertTrue(p.ativo)
        self.perder(p, 5)
        self.client.post(f"/produtos/{p.id}/desativar")
        db.session.refresh(p)
        self.assertFalse(p.ativo)
        # Produto desativado não pode receber colheita.
        self.assertEqual(self.colher(p, 1).status_code, 400)

    def test_unidade_bloqueada_com_historico(self):
        p = self.produto("Couve")
        self.colher(p, 5)
        resposta = self.client.post(f"/produtos/{p.id}/editar", data={
            "nome": "Couve", "categoria": "Folhosas", "unidade": "kg", "preco_venda": "3"})
        self.assertEqual(resposta.status_code, 400)
        db.session.refresh(p)
        self.assertEqual(p.unidade, "maço")


class TestColheitasEstoque(BaseTeste):
    def test_colheita_entra_no_estoque(self):
        p = self.produto()
        self.assertEqual(self.colher(p, 10).status_code, 302)
        self.colher(p, 5)
        self.assertEqual(self.saldo(p), Decimal("15"))
        colheita = db.session.scalar(select(Colheita).order_by(Colheita.id))
        self.assertTrue(colheita.lote.startswith("L"))
        self.assertEqual(colheita.validade, HOJE + timedelta(days=3))

    def test_validacoes_da_colheita(self):
        p = self.produto()
        self.assertEqual(self.colher(p, 0).status_code, 400)
        self.assertEqual(self.colher(p, -3).status_code, 400)
        self.assertEqual(self.colher(p, 2.5).status_code, 400)  # maço não aceita fração
        self.assertEqual(self.colher(p, 1, dia=HOJE + timedelta(days=1)).status_code, 400)
        kg = self.produto("Tomate", unidade="kg")
        self.assertEqual(self.colher(kg, 2.5).status_code, 302)
        self.assertEqual(self.saldo(p), 0)

    def test_excluir_colheita_somente_sem_uso(self):
        p = self.produto()
        self.colher(p, 10)
        c1 = db.session.scalar(select(Colheita))
        self.client.post(f"/colheitas/{c1.id}/excluir")
        self.assertEqual(self.saldo(p), 0)
        self.assertIsNone(db.session.get(Colheita, c1.id))

        self.colher(p, 10)
        c2 = db.session.scalar(select(Colheita))
        self.vender([(p, 2, "3")])
        self.client.post(f"/colheitas/{c2.id}/excluir")
        self.assertIsNotNone(db.session.get(Colheita, c2.id))
        self.assertEqual(self.saldo(p), Decimal("8"))


class TestVendas(BaseTeste):
    def test_venda_baixa_estoque_e_calcula_no_servidor(self):
        alface = self.produto("Alface", preco="3.00")
        tomate = self.produto("Tomate", unidade="kg", preco="8.00", custo="4.00")
        self.colher(alface, 20)
        self.colher(tomate, 10)
        resposta = self.vender([(alface, 4, "3.00"), (tomate, "1.5", "8.00")], desconto="2.00")
        self.assertEqual(resposta.status_code, 302)
        venda = db.session.scalar(select(Venda))
        self.assertEqual(venda.subtotal, Decimal("24.00"))
        self.assertEqual(venda.total, Decimal("22.00"))
        self.assertEqual(len(venda.itens), 2)
        self.assertEqual(self.saldo(alface), Decimal("16"))
        self.assertEqual(self.saldo(tomate), Decimal("8.5"))
        self.assertEqual(self.client.get(f"/vendas/{venda.id}").status_code, 200)

    def test_venda_maior_que_estoque_e_atomica(self):
        alface = self.produto("Alface")
        couve = self.produto("Couve")
        self.colher(alface, 10)
        self.colher(couve, 2)
        resposta = self.vender([(alface, 5, "3"), (couve, 3, "3")])
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Estoque insuficiente de Couve", resposta.get_data(as_text=True))
        # Nada foi gravado: nem a venda, nem a baixa do primeiro item.
        self.assertEqual(db.session.scalar(select(func.count(Venda.id))), 0)
        self.assertEqual(self.saldo(alface), Decimal("10"))
        self.assertEqual(self.saldo(couve), Decimal("2"))

    def test_validacoes_da_venda(self):
        p = self.produto()
        self.colher(p, 10)
        self.assertEqual(self.vender([]).status_code, 400)
        self.assertEqual(self.vender([(p, 1, "3"), (p, 1, "3")]).status_code, 400)  # duplicado
        self.assertEqual(self.vender([(p, 1, "3")], desconto="5").status_code, 400)  # desconto > subtotal
        self.assertEqual(self.vender([(p, 1, "3")], desconto="-1").status_code, 400)
        self.assertEqual(self.vender([(p, 0, "3")]).status_code, 400)
        self.assertEqual(self.vender([(p, 1, "-3")]).status_code, 400)
        self.assertEqual(self.vender([(p, 1, "3")], quando=datetime.now() + timedelta(days=1)).status_code, 400)
        self.assertEqual(db.session.scalar(select(func.count(Venda.id))), 0)
        self.assertEqual(self.saldo(p), Decimal("10"))

    def test_baixa_pelo_lote_mais_antigo(self):
        p = self.produto()
        self.colher(p, 5, dia=HOJE - timedelta(days=2), lote="ANTIGO")
        self.colher(p, 5, lote="NOVO")
        self.vender([(p, 7, "3")])
        lotes = {c.lote: c for c in db.session.scalars(select(Colheita))}
        saldo_antigo = db.session.scalar(select(func.sum(Movimentacao.quantidade))
                                         .where(Movimentacao.colheita_id == lotes["ANTIGO"].id))
        saldo_novo = db.session.scalar(select(func.sum(Movimentacao.quantidade))
                                       .where(Movimentacao.colheita_id == lotes["NOVO"].id))
        self.assertEqual(Decimal(saldo_antigo), 0)
        self.assertEqual(Decimal(saldo_novo), 3)

    def test_cancelamento_devolve_estoque_e_preserva_historico(self):
        p = self.produto()
        self.colher(p, 10)
        self.vender([(p, 4, "3")])
        venda = db.session.scalar(select(Venda))
        self.assertEqual(self.client.post(f"/vendas/{venda.id}/cancelar", data={}).status_code, 302)
        self.assertEqual(self.saldo(p), Decimal("6"))  # sem motivo, não cancela
        self.client.post(f"/vendas/{venda.id}/cancelar", data={"motivo_cancelamento": "duplicada"})
        self.assertEqual(self.saldo(p), Decimal("10"))
        db.session.refresh(venda)
        self.assertTrue(venda.cancelada)
        self.client.post(f"/vendas/{venda.id}/cancelar", data={"motivo_cancelamento": "de novo"})
        self.assertEqual(self.saldo(p), Decimal("10"))  # não estorna duas vezes
        fin = consultas.financeiro(HOJE, HOJE)
        self.assertEqual(fin["faturamento_liquido"], 0)


class TestPerdas(BaseTeste):
    def test_perda_baixa_estoque(self):
        p = self.produto()
        self.colher(p, 10)
        self.assertEqual(self.perder(p, 3).status_code, 302)
        self.assertEqual(self.saldo(p), Decimal("7"))
        self.assertEqual(self.perder(p, 8).status_code, 400)  # maior que o disponível
        self.assertEqual(self.saldo(p), Decimal("7"))

    def test_perda_em_lote_especifico(self):
        p = self.produto()
        self.colher(p, 5, dia=HOJE - timedelta(days=1), lote="A")
        self.colher(p, 5, lote="B")
        lote_b = db.session.scalar(select(Colheita).where(Colheita.lote == "B"))
        self.assertEqual(self.perder(p, 6, colheita=lote_b).status_code, 400)  # lote B só tem 5
        self.assertEqual(self.perder(p, 5, colheita=lote_b).status_code, 302)
        self.assertEqual(self.perder(p, 1, colheita=lote_b).status_code, 400)
        self.assertEqual(self.saldo(p), Decimal("5"))
        # Lote de outro produto é recusado.
        outro = self.produto("Couve")
        self.colher(outro, 5)
        self.assertEqual(self.perder(outro, 1, colheita=db.session.scalar(
            select(Colheita).where(Colheita.lote == "A"))).status_code, 400)

    def test_motivos(self):
        p = self.produto()
        self.colher(p, 10)
        self.assertEqual(self.perder(p, 1, motivo="inexistente").status_code, 400)
        self.assertEqual(self.perder(p, 1, motivo="outros").status_code, 400)  # exige observação
        self.assertEqual(self.perder(p, 1, motivo="outros", obs="granizo").status_code, 302)

    def test_cancelar_perda(self):
        p = self.produto()
        self.colher(p, 10)
        self.perder(p, 4)
        perda = db.session.scalar(select(Perda))
        self.client.post(f"/perdas/{perda.id}/cancelar", data={"motivo_cancelamento": "erro"})
        self.assertEqual(self.saldo(p), Decimal("10"))
        db.session.refresh(perda)
        self.assertTrue(perda.cancelada)


class TestRelatorios(BaseTeste):
    def preparar(self):
        alface = self.produto("Alface", preco="3.00", custo="1.00")
        tomate = self.produto("Tomate", unidade="kg", preco="8.00", custo="4.00")
        self.colher(alface, 20)
        self.colher(tomate, 10)
        self.vender([(alface, 10, "3.00"), (tomate, 2, "8.00")], desconto="6.00")  # subtotal 46, total 40
        self.perder(alface, 2, motivo="deterioracao")
        self.perder(tomate, 1, motivo="transporte")
        return alface, tomate

    def test_financeiro(self):
        self.preparar()
        fin = consultas.financeiro(HOJE, HOJE)
        self.assertEqual(fin["faturamento_bruto"], Decimal("46.00"))
        self.assertEqual(fin["descontos"], Decimal("6.00"))
        self.assertEqual(fin["faturamento_liquido"], Decimal("40.00"))
        self.assertEqual(fin["custo_vendidos"], Decimal("18.00"))   # 10x1 + 2x4
        self.assertEqual(fin["margem_bruta"], Decimal("22.00"))
        self.assertEqual(fin["perdas_custo"], Decimal("6.00"))      # 2x1 + 1x4
        self.assertEqual(fin["perdas_valor_venda"], Decimal("14.00"))  # 2x3 + 1x8
        self.assertEqual(fin["resultado_estimado"], Decimal("16.00"))

    def test_sem_custo_nao_estima_margem(self):
        p = self.produto("Cebolinha", custo="")
        self.colher(p, 5)
        self.vender([(p, 1, "2")])
        fin = consultas.financeiro(HOJE, HOJE)
        self.assertIsNone(fin["margem_bruta"])
        self.assertIsNone(fin["resultado_estimado"])

    def test_resumo_por_produto_e_motivos(self):
        alface, _ = self.preparar()
        linhas = {l["produto"].nome: l for l in consultas.resumo_por_produto(HOJE, HOJE)}
        self.assertEqual(linhas["Alface"]["colhido"], Decimal("20"))
        self.assertEqual(linhas["Alface"]["vendido"], Decimal("10"))
        self.assertEqual(linhas["Alface"]["perdido"], Decimal("2"))
        self.assertEqual(linhas["Alface"]["indice_perda"], Decimal("16.7"))
        # Rateio do desconto: 30 e 16 de 46, total 40.
        self.assertEqual(linhas["Alface"]["faturamento"] + linhas["Tomate"]["faturamento"], Decimal("40.00"))
        motivos = {m["motivo"]: m for m in consultas.motivos_perda(HOJE, HOJE)}
        self.assertEqual(motivos["transporte"]["valor_venda"], Decimal("8.00"))

    def test_paginas_e_csv(self):
        self.preparar()
        for url in ("/", "/relatorios/", "/estoque/", "/vendas/", "/perdas/", "/colheitas/", "/produtos/",
                    "/vendas/nova", "/colheitas/nova", "/perdas/nova", "/produtos/novo", "/configuracoes/",
                    "/pulverizacao/", "/?inicio=2020-01-01&fim=2030-01-01", "/relatorios/?inicio=lixo"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("R$ 40,00", html)
        for tipo in ("produtos", "colheitas", "vendas", "perdas", "motivos", "movimentacoes"):
            resposta = self.client.get(f"/relatorios/exportar/{tipo}.csv")
            self.assertEqual(resposta.status_code, 200, tipo)
            self.assertTrue(resposta.get_data(as_text=True).startswith("﻿"))
        self.assertEqual(self.client.get("/relatorios/exportar/qualquer.csv").status_code, 404)

    def test_csv_neutraliza_formulas(self):
        p = self.produto("=HYPERLINK(1)")
        self.colher(p, 1)
        texto = self.client.get("/relatorios/exportar/colheitas.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK(1)", texto)

    def test_painel_vazio(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Comece por aqui", html)
        self.assertIn("R$ 0,00", html)

    def test_alerta_estoque_baixo_e_validade(self):
        p = self.produto("Coentro", minimo="5", validade="1")
        self.colher(p, 3, dia=HOJE - timedelta(days=3))
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("mínimo", html)
        self.assertIn("vencido", html)


class TestPulverizacao(BaseTeste):
    def test_registro_e_calculo(self):
        resposta = self.client.post("/pulverizacao/", data={
            "talhao": "Talhão Norte", "cultura": "Alface", "area_ha": "2,5", "dosagem_l_ha": "4", "data": HOJE.isoformat()})
        self.assertEqual(resposta.status_code, 302)
        registro = db.session.scalar(select(Pulverizacao))
        self.assertEqual(registro.volume_total, Decimal("10.00"))
        self.client.post(f"/pulverizacao/{registro.id}/editar", data={
            "talhao": "Talhão Norte", "cultura": "Alface", "area_ha": "3", "dosagem_l_ha": "4", "data": HOJE.isoformat()})
        db.session.refresh(registro)
        self.assertEqual(registro.volume_total, Decimal("12.00"))
        self.assertEqual(self.client.post("/pulverizacao/", data={
            "talhao": "X", "cultura": "Y", "area_ha": "-1", "dosagem_l_ha": "4", "data": HOJE.isoformat()}).status_code, 400)
        self.client.post(f"/pulverizacao/{registro.id}/excluir")
        self.assertIsNone(db.session.get(Pulverizacao, registro.id))
        # Exclusão por GET (como na versão antiga) não é permitida.
        self.assertEqual(self.client.get("/pulverizacao/1/excluir").status_code, 405)


class TestPersistencia(BaseTeste):
    def test_dados_sobrevivem_ao_reinicio(self):
        p = self.produto()
        self.colher(p, 12)
        self.vender([(p, 2, "3")])
        db.session.remove()
        self.ctx.pop()
        with self.app.app_context():
            db.engine.dispose()

        novo_app = self.criar_app()  # simula fechar e abrir o sistema
        with novo_app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(Venda.id))), 1)
            produto = db.session.scalar(select(Produto))
            self.assertEqual(saldo_produto(produto.id), Decimal("10"))
            db.engine.dispose()
        self.ctx = self.app.app_context()
        self.ctx.push()


class TestFormatacao(unittest.TestCase):
    def test_formatos_brasileiros(self):
        self.assertEqual(formatar_moeda(Decimal("1234.5")), "R$ 1.234,50")
        self.assertEqual(formatar_qtd(Decimal("2.500"), "kg"), "2,5 kg")
        self.assertEqual(formatar_qtd(Decimal("10"), "maço"), "10 maço")
        for valor in ("1e400", "-1e400", "999999999"):
            with self.assertRaises(ErroValidacao):
                decimal(valor, "valor")


if __name__ == "__main__":
    unittest.main()
