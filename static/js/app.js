(() => {
  "use strict";

  const LOJA = JSON.parse(document.getElementById("loja-config").textContent);
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
  const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const brl = (valor) => moeda.format(valor);

  let situacao = LOJA.situacao;
  let carrinho = { modo: "encomenda", itens: [], quantidade_total: 0, subtotal: { valor: 0, texto: brl(0) }, tem_algodao: false };

  async function api(metodo, url, corpo) {
    const resposta = await fetch(url, {
      method: metodo,
      headers: corpo ? { "Content-Type": "application/json" } : undefined,
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw Object.assign(new Error(dados.erro || "Algo deu errado. Tente novamente."), { dados });
    return dados;
  }

  // --- Toast -------------------------------------------------------------
  const toast = $("[data-toast]");
  let toastTimer;
  function avisar(texto, erro = false) {
    toast.textContent = texto;
    toast.classList.toggle("toast--erro", erro);
    toast.classList.add("visivel");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("visivel"), erro ? 4200 : 2600);
  }

  // --- Quantidade --------------------------------------------------------
  function limitar(valor, maximo = 999, minimo = 1) {
    const n = Math.round(Number(valor));
    return Number.isFinite(n) ? Math.min(maximo, Math.max(minimo, n)) : minimo;
  }

  function ligarQuantidade(caixa, aoMudar) {
    const input = $("input", caixa);
    const definir = (valor) => { input.value = limitar(valor, Number(input.max) || 999, Number(input.min)); aoMudar(Number(input.value)); };
    $("[data-menos]", caixa).addEventListener("click", () => definir(Number(input.value) - 1));
    $("[data-mais]", caixa).addEventListener("click", () => definir(Number(input.value) + 1));
    input.addEventListener("change", () => definir(input.value));
  }

  // --- Adicionar ao carrinho ---------------------------------------------
  async function adicionarAoCarrinho(corpo) {
    try {
      carrinho = await api("POST", "/api/carrinho", corpo);
    } catch (erro) {
      if (!(erro.dados && erro.dados.conflito)) throw erro;
      if (!window.confirm(`${erro.message}\n\nEsvaziar o carrinho e continuar?`)) return false;
      await api("DELETE", "/api/carrinho");
      carrinho = await api("POST", "/api/carrinho", corpo);
    }
    renderizarCarrinho();
    const botaoCarrinho = $("[data-abrir-carrinho]");
    botaoCarrinho.classList.remove("pulo");
    void botaoCarrinho.offsetWidth;
    botaoCarrinho.classList.add("pulo");
    avisar("Adicionado ao carrinho!");
    return true;
  }

  async function aoAdicionar(botao, corpo) {
    if (corpo.quantidade < 1) {
      avisar("Escolha a quantidade antes de adicionar.", true);
      return;
    }
    botao.disabled = true;
    try {
      await adicionarAoCarrinho(corpo);
    } catch (erro) {
      avisar(erro.message, true);
    } finally {
      botao.disabled = false;
    }
  }

  // --- Cartões de produto (encomenda) ------------------------------------
  const entradasCor = $$("input[name=cor]");

  // Uma cor pinta direto; uma mescla ganha um degradê próprio, criado uma vez por combinação.
  function tintaDoAlgodao(ids) {
    if (ids.includes("colorido")) return "url(#arcoiris)";
    const cores = ids.map((id) => entradasCor.find((entrada) => entrada.value === id).dataset.hex);
    if (cores.length === 1) return cores[0];
    const idDegrade = `mescla-${ids.join("-")}`;
    if (!document.getElementById(idDegrade)) {
      const svgNs = "http://www.w3.org/2000/svg";
      const degrade = document.createElementNS(svgNs, "linearGradient");
      Object.entries({ id: idDegrade, gradientUnits: "userSpaceOnUse", x1: 10, y1: 10, x2: 110, y2: 100 })
        .forEach(([nome, valor]) => degrade.setAttribute(nome, valor));
      cores.forEach((cor, indice) => {
        const parada = document.createElementNS(svgNs, "stop");
        parada.setAttribute("offset", indice / (cores.length - 1));
        parada.setAttribute("stop-color", cor);
        degrade.append(parada);
      });
      $(".svg-defs defs").append(degrade);
    }
    return `url(#${idDegrade})`;
  }

  $$(".produto-form").forEach((form) => {
    const subtotal = $("[data-subtotal]", form);
    const quantidade = $("input[name=quantidade]", form);
    const atualizar = () => {
      const preco = Number($("input[name=opcao]:checked", form).dataset.preco);
      subtotal.textContent = brl(preco * limitar(quantidade.value, 999, 0));
    };

    ligarQuantidade($("[data-qtd]", form), atualizar);
    quantidade.addEventListener("input", atualizar);
    $$("input[name=opcao]", form).forEach((radio) => radio.addEventListener("change", atualizar));

    if (form.dataset.produto === "algodao") {
      const arte = $("[data-arte-algodao]");
      const nomeCor = $("[data-cor-nome]", form);
      const separadas = entradasCor.filter((entrada) => entrada.value !== "colorido");
      const colorido = entradasCor.find((entrada) => entrada.value === "colorido");
      entradasCor.forEach((entrada) => entrada.addEventListener("change", () => {
        if (entrada === colorido) {
          if (colorido.checked) separadas.forEach((cor) => { cor.checked = false; });
        } else {
          colorido.checked = false;
          if (separadas.every((cor) => cor.checked)) {
            colorido.checked = true;
            separadas.forEach((cor) => { cor.checked = false; });
          }
        }
        const marcadas = entradasCor.filter((cor) => cor.checked);
        nomeCor.textContent = marcadas.length ? marcadas.map((cor) => cor.dataset.nome).join(", ") : "Escolha pelo menos uma";
        if (marcadas.length) arte.style.setProperty("--candy", tintaDoAlgodao(marcadas.map((cor) => cor.value)));
      }));
    }

    form.addEventListener("submit", (evento) => {
      evento.preventDefault();
      aoAdicionar($("button[type=submit]", form), {
        modo: form.dataset.modo || "encomenda",
        produto: form.dataset.produto,
        opcao: $("input[name=opcao]:checked", form).value,
        cor: $$("input[name=cor]:checked", form).map((cor) => cor.value),
        sabor: form.elements.sabor ? form.elements.sabor.value : null,
        quantidade: limitar(quantidade.value, 999, 0),
      });
    });

    atualizar();
  });

  // --- Abas Encomenda / Pick-up ------------------------------------------
  function mostrarAba(nome) {
    $$("[data-aba]").forEach((aba) => aba.setAttribute("aria-selected", String(aba.dataset.aba === nome)));
    $$("[data-painel]").forEach((painel) => { painel.hidden = painel.dataset.painel !== nome; });
    if (nome === "pickup") carregarEstufa();
  }

  $$("[data-aba]").forEach((aba) => aba.addEventListener("click", () => mostrarAba(aba.dataset.aba)));
  $$("[data-ir-pickup]").forEach((link) => link.addEventListener("click", (evento) => {
    evento.preventDefault();
    mostrarAba("pickup");
    $("#salgados").scrollIntoView({ behavior: "smooth" });
  }));

  // --- Estufa (pick-up) --------------------------------------------------
  const estufaLista = $("[data-estufa-lista]");
  const estufaStatus = $("[data-estufa-status]");
  const CATEGORIAS = { assado: "Assados", frito: "Fritos" };

  async function carregarEstufa() {
    try {
      const { itens } = await api("GET", "/api/estufa");
      renderizarEstufa(itens);
    } catch {
      estufaStatus.textContent = "Não foi possível ver a estufa agora. Tente atualizar.";
    }
  }

  function renderizarEstufa(itens) {
    const total = itens.reduce((soma, item) => soma + item.disponivel, 0);
    estufaStatus.textContent = total
      ? `${total} salgado(s) na estufa agora.`
      : "A estufa está vazia agora. Volte daqui a pouco ou faça uma encomenda.";

    const grupos = Object.entries(CATEGORIAS).map(([categoria, titulo]) => {
      const doGrupo = itens.filter((item) => item.categoria === categoria);
      if (!doGrupo.length) return null;
      const bloco = document.createElement("div");
      bloco.innerHTML = `<h3 class="grupo-titulo"></h3><ul class="estufa"></ul>`;
      $("h3", bloco).textContent = titulo;
      $("ul", bloco).append(...doGrupo.map(criarItemEstufa));
      return bloco;
    }).filter(Boolean);
    estufaLista.replaceChildren(...grupos);
  }

  function criarItemEstufa(item) {
    const li = document.createElement("li");
    li.className = "estufa-item";
    li.innerHTML = `
      <div class="estufa-info">
        <strong></strong>
        <span class="estufa-detalhe"></span>
        <span class="estufa-qtd"></span>
      </div>
      <span class="estufa-preco"></span>
      <div class="qtd qtd--sm" data-qtd>
        <button type="button" data-menos aria-label="Diminuir quantidade">−</button>
        <input type="number" value="0" min="0" inputmode="numeric" aria-label="Quantidade">
        <button type="button" data-mais aria-label="Aumentar quantidade">+</button>
      </div>
      <button type="button" class="btn btn-primario btn-sm">Adicionar</button>`;
    $("strong", li).textContent = item.nome;
    $(".estufa-detalhe", li).textContent = [item.tamanho, item.sabor_nome].filter(Boolean).join(" · ");
    $(".estufa-qtd", li).textContent = `${item.disponivel} na estufa`;
    const precoEl = $(".estufa-preco", li);
    precoEl.textContent = item.preco.texto;
    if (item.preco.valor < item.preco_normal.valor) {
      const antigo = document.createElement("s");
      antigo.textContent = item.preco_normal.texto;
      precoEl.prepend(antigo);
    }
    $(".btn", li).disabled = !situacao.aceita_pickup;
    const quantidade = $("input", li);
    quantidade.max = item.disponivel;
    ligarQuantidade($("[data-qtd]", li), () => {});
    $(".btn", li).addEventListener("click", (evento) => aoAdicionar(evento.currentTarget, {
      modo: "pickup",
      produto: item.produto,
      opcao: item.opcao,
      sabor: item.sabor,
      quantidade: limitar(quantidade.value, item.disponivel, 0),
    }));
    return li;
  }

  $("[data-atualizar-estufa]").addEventListener("click", carregarEstufa);

  // --- Gaveta ------------------------------------------------------------
  const gaveta = $("[data-gaveta]");
  const fundo = $("[data-fundo]");
  const titulo = $("[data-gaveta-titulo]");
  const voltar = $("[data-voltar]");
  const TITULOS = { itens: "Seu carrinho", checkout: "Dados do pedido", enviar: "Quase lá!" };

  function mostrarEtapa(nome) {
    $$("[data-etapa]", gaveta).forEach((etapa) => { etapa.hidden = etapa.dataset.etapa !== nome; });
    titulo.textContent = TITULOS[nome];
    voltar.hidden = nome === "itens";
    voltar.dataset.destino = nome === "enviar" ? "checkout" : "itens";
  }

  function abrirGaveta(etapa = "itens") {
    mostrarEtapa(etapa);
    fundo.hidden = false;
    gaveta.classList.add("aberta");
    gaveta.setAttribute("aria-hidden", "false");
    document.body.classList.add("travado");
    $("[data-fechar]", gaveta).focus();
  }

  function fecharGaveta() {
    gaveta.classList.remove("aberta");
    gaveta.setAttribute("aria-hidden", "true");
    fundo.hidden = true;
    document.body.classList.remove("travado");
  }

  $("[data-abrir-carrinho]").addEventListener("click", () => abrirGaveta());
  fundo.addEventListener("click", fecharGaveta);
  $$("[data-fechar]", gaveta).forEach((botao) => botao.addEventListener("click", fecharGaveta));
  voltar.addEventListener("click", () => mostrarEtapa(voltar.dataset.destino));
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && gaveta.classList.contains("aberta")) fecharGaveta();
  });

  // --- Itens do carrinho -------------------------------------------------
  const lista = $("[data-itens]");
  const ARTES = {
    algodao: $(".produto-arte--algodao svg"),
    maca: $(".produto-arte--maca svg"),
    salgado: $("[data-arte-salgado] svg"),
  };

  function renderizarCarrinho() {
    const badge = $("[data-badge]");
    badge.hidden = carrinho.quantidade_total === 0;
    badge.textContent = carrinho.quantidade_total;

    const vazio = carrinho.itens.length === 0;
    $("[data-vazio]").hidden = !vazio;
    $("[data-rodape-itens]").hidden = vazio;
    $("[data-carrinho-subtotal]").textContent = carrinho.subtotal.texto;
    const modoPedido = $("[data-modo-pedido]");
    modoPedido.hidden = vazio;
    modoPedido.className = `modo-pedido modo-pedido--${carrinho.modo}`;
    modoPedido.textContent = carrinho.modo === "pickup"
      ? "Pick-up · retire hoje no balcão, preço de balcão"
      : "Encomenda · retire no local na data combinada";

    lista.replaceChildren(...carrinho.itens.map(criarItem));
    atualizarCheckout();
  }

  function criarItem(item) {
    const li = document.createElement("li");
    li.className = "item";

    const arte = document.createElement("div");
    arte.className = "item-arte";
    const ehDoce = item.categoria === "doce";
    arte.append((ehDoce ? ARTES[item.produto] : ARTES.salgado).cloneNode(true));
    if (item.produto === "algodao") {
      arte.style.setProperty("--candy", tintaDoAlgodao(item.cor_id.split("+")));
    }

    const info = document.createElement("div");
    const detalhe = [item.opcao, item.variacao].filter(Boolean).join(" · ");
    info.innerHTML = `
      <div class="item-nome"></div>
      <div class="item-detalhe"></div>
      <div class="item-acoes">
        <div class="qtd qtd--sm" data-qtd>
          <button type="button" data-menos aria-label="Diminuir quantidade">−</button>
          <input type="number" min="1" inputmode="numeric" aria-label="Quantidade">
          <button type="button" data-mais aria-label="Aumentar quantidade">+</button>
        </div>
        <button type="button" class="item-remover">Remover</button>
      </div>`;
    $(".item-nome", info).textContent = item.nome;
    $(".item-detalhe", info).textContent = `${detalhe} · ${item.preco_unitario.texto} cada`;
    const quantidade = $("input", info);
    quantidade.max = Math.max(item.maximo, 1);
    quantidade.value = item.quantidade;

    ligarQuantidade($("[data-qtd]", info), (valor) => alterarItem("PATCH", item.indice, { quantidade: valor }));
    $(".item-remover", info).addEventListener("click", () => alterarItem("DELETE", item.indice));

    const preco = document.createElement("div");
    preco.className = "item-preco";
    preco.textContent = item.subtotal.texto;

    li.append(arte, info, preco);
    return li;
  }

  async function alterarItem(metodo, indice, corpo) {
    try {
      carrinho = await api(metodo, `/api/carrinho/${indice}`, corpo);
    } catch (erro) {
      avisar(erro.message, true);
    }
    renderizarCarrinho();
  }

  // --- Checkout ----------------------------------------------------------
  const formPedido = $("[data-etapa=checkout]");
  const campoSinal = $("#sinal");
  let sinalEditado = false;
  let dadosRevisados = null;

  const ehPickup = () => carrinho.modo === "pickup";

  function totais() {
    const esteira = !ehPickup() && carrinho.tem_algodao && formPedido.modo_entrega.value === "esteira" ? LOJA.esteira : 0;
    const total = Math.round((carrinho.subtotal.valor + esteira) * 100) / 100;
    return { esteira, total, minimo: Math.min(LOJA.sinalMinimo, total) };
  }

  function atualizarCheckout() {
    const pickup = ehPickup();
    $$("[data-so-encomenda]", formPedido).forEach((el) => { el.hidden = pickup; });
    $$("[data-so-pickup]", formPedido).forEach((el) => { el.hidden = !pickup; });
    $("[data-so-algodao]").hidden = pickup || !carrinho.tem_algodao;

    const antecipado = formPedido.momento_pagamento.value === "antecipado";
    $("[data-pagamento-forma]").hidden = pickup && antecipado;
    $("[data-dica-antecipado]").hidden = !(pickup && antecipado);
    $("[data-pagamento-legenda]").textContent = pickup ? "Forma de pagamento na retirada" : "Método de pagamento";
    formPedido.observacoes.placeholder = pickup
      ? "Algum recado? Ex.: vou de carro, chego em 10 minutos…"
      : "Tema da festa, algum recado…";

    const { esteira, total, minimo } = totais();
    $("[data-dica-esteira]").hidden = esteira === 0;
    $("[data-r-esteira-linha]").hidden = esteira === 0;
    $("[data-r-esteira]").textContent = brl(esteira);
    $("[data-r-subtotal]").textContent = carrinho.subtotal.texto;
    $("[data-r-total]").textContent = brl(total);

    campoSinal.min = minimo.toFixed(2);
    campoSinal.max = total.toFixed(2);
    // Depois que o cliente mexe no sinal, o valor é dele: o site só avisa, nunca reescreve enquanto ele digita.
    if (!sinalEditado) campoSinal.value = minimo.toFixed(2);
    $("[data-dica-sinal]").textContent = `Mínimo ${brl(minimo)} · máximo ${brl(total)}`;
    $("[data-r-restante]").textContent = brl(Math.max(0, total - Number(campoSinal.value || 0)));
    if (sinalEditado) conferirSinal(total, minimo);
  }

  function conferirSinal(total, minimo) {
    const digitado = campoSinal.value === "" ? null : Number(campoSinal.value);
    let erro = "";
    if (digitado === null) erro = "Informe o valor do sinal.";
    else if (digitado < minimo) erro = `O sinal deve ser de ${brl(minimo)} ou mais. Digite um valor maior.`;
    else if (digitado > total) erro = `O sinal não pode passar do total (${brl(total)}).`;
    $('[data-erro="sinal"]', formPedido).textContent = erro;
    campoSinal.closest(".campo").classList.toggle("invalido", Boolean(erro));
  }

  campoSinal.addEventListener("input", () => { sinalEditado = true; atualizarCheckout(); });
  formPedido.addEventListener("input", (evento) => {
    if (evento.target === campoSinal) return;
    const caixa = evento.target.closest(".campo");
    if (caixa) caixa.classList.remove("invalido");
    const nome = evento.target.name === "horario" ? "data" : evento.target.name;
    const erro = $(`[data-erro="${nome}"]`, formPedido);
    if (erro) erro.textContent = "";
  });
  $$("input[name=modo_entrega], input[name=momento_pagamento]", formPedido)
    .forEach((radio) => radio.addEventListener("change", atualizarCheckout));

  const telefone = $("#telefone");
  telefone.addEventListener("input", () => {
    const d = telefone.value.replace(/\D/g, "").slice(0, 11);
    let texto = d;
    if (d.length > 2) texto = `(${d.slice(0, 2)}) ${d.slice(2)}`;
    if (d.length > 6) texto = `(${d.slice(0, 2)}) ${d.slice(2, d.length === 11 ? 7 : 6)}-${d.slice(d.length === 11 ? 7 : 6)}`;
    telefone.value = texto;
  });

  const iso = (data) => new Date(data.getTime() - data.getTimezoneOffset() * 60000).toISOString();
  $("#data").min = iso(new Date()).slice(0, 10);

  $("[data-ir-checkout]").addEventListener("click", () => {
    const retirada = $("#horario_retirada");
    retirada.min = situacao.retirada_min || "";
    retirada.max = situacao.retirada_max || "";
    if (ehPickup() && !retirada.value) retirada.value = situacao.retirada_padrao || "";
    atualizarCheckout();
    mostrarEtapa("checkout");
    $("#nome").focus();
  });

  function limparErros() {
    $$("[data-erro]", formPedido).forEach((el) => { el.textContent = ""; });
    $$(".invalido", formPedido).forEach((el) => el.classList.remove("invalido"));
  }

  function mostrarErros(erros) {
    Object.entries(erros).forEach(([campo, texto]) => {
      const alvo = $(`[data-erro="${campo}"]`, formPedido);
      if (alvo) alvo.textContent = texto;
      const entrada = formPedido.elements[campo];
      if (entrada instanceof Element) entrada.closest(".campo").classList.add("invalido");
      if (campo === "data") $("#horario").closest(".campo").classList.add("invalido");
    });
    const primeiro = $(".invalido input, .invalido textarea", formPedido);
    if (primeiro) primeiro.focus();
  }

  formPedido.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    limparErros();
    const dados = Object.fromEntries(new FormData(formPedido));
    const botao = $("button[type=submit]", formPedido);
    botao.disabled = true;
    try {
      const pedido = await api("POST", "/api/pedido", dados);
      dadosRevisados = dados;
      $("[data-mensagem]").textContent = pedido.mensagem.replace(/\*/g, "");
      $("[data-erro-envio]").textContent = "";
      $("[data-enviar-intro]").textContent = pedido.modo === "pickup"
        ? "Confira seu pedido. Ao enviar, seus salgados ficam reservados na estufa e o WhatsApp abre com a mensagem e o código da reserva."
        : "Confira seu pedido. Ao tocar no botão, o WhatsApp abre com a mensagem pronta.";
      mostrarEtapa("enviar");
    } catch (erro) {
      if (erro.dados && erro.dados.erros) mostrarErros(erro.dados.erros);
      else avisar(erro.message, true);
    } finally {
      botao.disabled = false;
    }
  });

  $("[data-enviar-whats]").addEventListener("click", async (evento) => {
    const botao = evento.currentTarget;
    // A janela abre já no clique para o navegador não bloquear; o endereço chega depois da reserva.
    const janela = window.open("", "_blank");
    botao.disabled = true;
    try {
      const pedido = await api("POST", "/api/pedido/enviar", dadosRevisados);
      if (janela) {
        janela.opener = null;
        janela.location.href = pedido.whatsapp;
      } else {
        window.location.href = pedido.whatsapp;
      }
      carrinho = await api("GET", "/api/carrinho");
      formPedido.reset();
      sinalEditado = false;
      dadosRevisados = null;
      renderizarCarrinho();
      fecharGaveta();
      if (pedido.modo === "pickup") {
        carregarEstufa();
        avisar(`Reserva ${pedido.codigo} feita! Confirme no WhatsApp.`);
      } else {
        avisar("Pedido enviado! Agora é só confirmar no WhatsApp.");
      }
    } catch (erro) {
      if (janela) janela.close();
      const erros = erro.dados && erro.dados.erros;
      $("[data-erro-envio]").textContent = erros ? Object.values(erros).join(" ") : erro.message;
      if (ehPickup()) {
        carrinho = await api("GET", "/api/carrinho").catch(() => carrinho);
        renderizarCarrinho();
        carregarEstufa();
      }
    } finally {
      botao.disabled = false;
    }
  });

  // --- Horário e promoção ------------------------------------------------
  function aplicarSituacao(nova) {
    const mudou = nova.promocao !== situacao.promocao || nova.aceita_pickup !== situacao.aceita_pickup;
    situacao = nova;
    const faixa = $("[data-faixa-loja]");
    faixa.className = `faixa-loja faixa-loja--${nova.tipo}`;
    faixa.textContent = nova.mensagem;
    if (mudou) {
      carregarEstufa();
      api("GET", "/api/carrinho").then((dados) => { carrinho = dados; renderizarCarrinho(); }).catch(() => {});
    }
  }

  setInterval(() => { api("GET", "/api/loja").then(aplicarSituacao).catch(() => {}); }, 60000);

  // --- Início ------------------------------------------------------------
  api("GET", "/api/carrinho")
    .then((dados) => { carrinho = dados; renderizarCarrinho(); })
    .catch(() => renderizarCarrinho());
  if (location.hash === "#pickup") mostrarAba("pickup");
})();
