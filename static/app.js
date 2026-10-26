// Comportamentos de interface do AgroHorti. Todos os cálculos aqui são apenas
// prévias: os valores oficiais são sempre validados e calculados no servidor.
(function () {
    "use strict";

    const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
    const numero = (valor) => {
        const n = parseFloat(String(valor || "").replace(",", "."));
        return Number.isFinite(n) ? n : 0;
    };

    // Menu lateral no celular
    const corpo = document.body;
    const botaoMenu = document.querySelector("[data-menu-toggle]");
    function alternarMenu(aberto) {
        corpo.classList.toggle("menu-aberto", aberto);
        if (botaoMenu) botaoMenu.setAttribute("aria-expanded", String(aberto));
    }
    if (botaoMenu) botaoMenu.addEventListener("click", () => alternarMenu(!corpo.classList.contains("menu-aberto")));
    document.querySelectorAll("[data-menu-close]").forEach((el) => el.addEventListener("click", () => alternarMenu(false)));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") alternarMenu(false); });

    // Fechar mensagens
    document.querySelectorAll("[data-dismiss]").forEach((botao) =>
        botao.addEventListener("click", () => botao.closest(".flash").remove())
    );

    // Confirmação de ações importantes (exclusões, cancelamentos)
    document.addEventListener("submit", (e) => {
        const mensagem = e.target.getAttribute("data-confirm");
        if (mensagem && !window.confirm(mensagem)) e.preventDefault();
    });

    // Evita envio duplo (ex.: toque duplo no celular registrando duas vendas)
    document.addEventListener("submit", (e) => {
        if (e.defaultPrevented || e.target.method.toLowerCase() !== "post") return;
        setTimeout(() => e.target.querySelectorAll("button[type=submit], button:not([type])").forEach((b) => { b.disabled = true; }), 0);
    });

    // Mostrar unidade e saldo do produto escolhido; filtrar lotes pelo produto
    document.querySelectorAll("select[data-unidade-alvo]").forEach((select) => {
        const alvoUnidade = document.querySelector(select.dataset.unidadeAlvo);
        const alvoSaldo = select.dataset.saldoAlvo ? document.querySelector(select.dataset.saldoAlvo) : null;
        const lotes = select.dataset.filtraLotes ? document.querySelector(select.dataset.filtraLotes) : null;

        function atualizar() {
            const opcao = select.selectedOptions[0];
            const unidade = opcao ? opcao.dataset.unidade : "";
            if (alvoUnidade) alvoUnidade.textContent = unidade ? "(" + unidade + ")" : "";
            if (alvoSaldo) alvoSaldo.textContent = opcao && opcao.dataset.saldo ? "Disponível em estoque: " + opcao.dataset.saldo : "";
            if (lotes) {
                lotes.querySelectorAll("option[data-produto]").forEach((o) => {
                    const visivel = o.dataset.produto === select.value;
                    o.hidden = !visivel;
                    o.disabled = !visivel;
                });
                const escolhido = lotes.selectedOptions[0];
                if (escolhido && escolhido.disabled) lotes.value = "";
            }
        }
        select.addEventListener("change", atualizar);
        atualizar();
    });

    // Formulário de venda com vários itens
    const formVenda = document.getElementById("form-venda");
    if (formVenda) {
        const lista = document.getElementById("itens-venda");
        const modelo = lista.querySelector("[data-item]").cloneNode(true);
        const desconto = document.getElementById("desconto");

        function recalcular() {
            let subtotal = 0;
            lista.querySelectorAll("[data-item]").forEach((item) => {
                const qtd = numero(item.querySelector("[name=quantidade]").value);
                const preco = numero(item.querySelector("[name=preco_unitario]").value);
                const valor = Math.round(qtd * preco * 100) / 100;
                subtotal += valor;
                item.querySelector("[data-subtotal]").textContent = moeda.format(valor);
            });
            const desc = numero(desconto.value);
            document.getElementById("resumo-subtotal").textContent = moeda.format(subtotal);
            document.getElementById("resumo-desconto").textContent = moeda.format(desc);
            document.getElementById("resumo-total").textContent = moeda.format(Math.max(subtotal - desc, 0));
        }

        function prepararItem(item) {
            const select = item.querySelector("[data-produto-venda]");
            const preco = item.querySelector("[name=preco_unitario]");
            const qtd = item.querySelector("[name=quantidade]");
            const rotulo = item.querySelector("[data-unidade-item]");
            function aoTrocarProduto(preencherPreco) {
                const opcao = select.selectedOptions[0];
                rotulo.textContent = opcao && opcao.dataset.unidade ? "(" + opcao.dataset.unidade + ")" : "";
                if (opcao && opcao.dataset.saldo) qtd.max = opcao.dataset.saldo;
                if (preencherPreco && opcao && opcao.dataset.preco) preco.value = opcao.dataset.preco;
                recalcular();
            }
            select.addEventListener("change", () => aoTrocarProduto(true));
            item.querySelector("[data-remover-item]").addEventListener("click", () => {
                if (lista.querySelectorAll("[data-item]").length > 1) {
                    item.remove();
                } else {
                    select.value = ""; qtd.value = ""; preco.value = "";
                }
                recalcular();
            });
            aoTrocarProduto(false);
        }

        lista.querySelectorAll("[data-item]").forEach(prepararItem);
        document.getElementById("adicionar-item").addEventListener("click", () => {
            const novo = modelo.cloneNode(true);
            novo.querySelectorAll("input").forEach((i) => { i.value = ""; });
            novo.querySelector("select").value = "";
            lista.appendChild(novo);
            prepararItem(novo);
            novo.querySelector("select").focus();
        });
        formVenda.addEventListener("input", recalcular);
        recalcular();
    }

    // Prévia do volume de calda (pulverização)
    document.querySelectorAll("form[data-calda]").forEach((form) => {
        const area = form.querySelector("[data-calda-area]");
        const dosagem = form.querySelector("[data-calda-dosagem]");
        const saida = form.querySelector("[data-calda-resultado]");
        function calcular() {
            const volume = numero(area.value) * numero(dosagem.value);
            saida.textContent = volume > 0 ? volume.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " L" : "—";
        }
        form.addEventListener("input", calcular);
        calcular();
    });

    // Busca rápida em tabelas
    document.querySelectorAll("[data-filtro-tabela]").forEach((campo) => {
        const tabela = document.querySelector(campo.dataset.filtroTabela);
        if (!tabela) return;
        campo.addEventListener("input", () => {
            const termo = campo.value.trim().toLowerCase();
            tabela.querySelectorAll("tbody tr").forEach((linha) => {
                linha.style.display = linha.textContent.toLowerCase().includes(termo) ? "" : "none";
            });
        });
    });
})();
