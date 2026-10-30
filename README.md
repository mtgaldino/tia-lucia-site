# Tia Lúcia: Salgados e Doces

Site em Python (Flask) com carrinho de compras e dois tipos de pedido, ambos finalizados pelo WhatsApp:

- **Encomenda**: salgados, algodão doce e maçã do amor para festas e eventos, com data, horário e sinal.
- **Pick-up**: salgados que estão na estufa agora, com preço de balcão, para retirar no mesmo dia.

## Tecnologias e destaques

Python, Flask, SQLite, Jinja, JavaScript e CSS sem frameworks, e pytest.

- Preços sempre recalculados no servidor, com `Decimal`, sem confiar no que vem do navegador.
- Reservas atômicas no SQLite (`BEGIN IMMEDIATE`), para dois clientes nunca levarem a mesma unidade.
- Regras de horário e promoção no fuso de São Paulo, testadas com relógio controlado.
- Painel protegido por senha para a loja cuidar da estufa e das reservas.

## Rodar

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Site: http://localhost:5000 · Painel da loja: http://localhost:5000/painel

## Configuração (variáveis de ambiente)

| Variável          | Para quê                                                        |
|-------------------|-----------------------------------------------------------------|
| `WHATSAPP_NUMERO` | Número que recebe os pedidos, só dígitos: DDI + DDD + número (padrão: `5521985209765`) |
| `NOME_LOJA`       | Nome exibido no site e no pedido                                |
| `PAINEL_SENHA`    | Senha do painel. Sem ela, uma senha é gerada uma vez e salva em `dados/senha_painel.txt` |
| `SECRET_KEY`      | Chave da sessão. **Defina em produção**, senão carrinho e login do painel somem a cada reinício |
| `PASTA_DADOS`     | Onde fica o banco `loja.db` (padrão: `dados/`)                  |
| `PORT`            | Porta do servidor (padrão: 5000)                                |

## Painel da loja (`/painel`)

- **Estufa**: informe quantas unidades de cada salgado (por sabor e tamanho) estão na estufa. Só aparece no
  pick-up o que tiver quantidade acima de zero.
- **Reservas de pick-up**: cada pedido enviado pelo site já desconta da estufa e aparece aqui com um código
  (o mesmo da mensagem do WhatsApp). Marque **Retirado** quando o cliente buscar, ou **Cancelar e devolver**
  se ele não vier, e as unidades voltam para a estufa.

## Regras implementadas

**Salgados**: grande R$ 7,00 no balcão (pick-up) e R$ 4,00 na encomenda; pequeno R$ 2,50 nos dois.
Sabores (frango, queijo c/ presunto, calabresa, carne, queijo minas) valem para joelho, pastel de forno, empada e empadão.
O Hambúrguer é vendido só no balcão/pick-up (`so_balcao` em `catalogo.py`); o Hambúrguer de forno também tem encomenda.

**Pick-up**: só salgados; retirada no mesmo dia; pagamento antecipado (só PIX, o cliente manda o comprovante
no WhatsApp) ou na retirada (PIX, cartão ou dinheiro). O site não deixa pedir mais do que há na estufa, e a
reserva é feita de forma atômica no envio, então dois clientes nunca levam a mesma unidade.

**Encomenda**: sem quantidade mínima; data e horário da entrega; sinal mínimo de R$ 20,00 (ou o total, se
menor). O pedido só é finalizado com todos os campos válidos; só as observações são opcionais.

**Algodão doce**: o cliente pode mesclar cores (uma ou mais); Colorido leva todas. Com algodão no pedido: caixa ou esteira (+ R$ 20,00, devolvido após a devolução da esteira).

Um carrinho é de encomenda **ou** de pick-up. Se o cliente misturar, o site pergunta se quer esvaziar.

**Retirada**: a loja não faz entrega. Encomenda e pick-up são retirados no local, dentro do horário de funcionamento (segunda a sexta 8:30-18:30, sábado 8:30-17h).

**Promoção**: segunda a sexta a partir das 16h e sábado a partir das 15h, o salgado grande de R$ 7,00 sai por R$ 5,50, só no balcão/pick-up. O empadão (R$ 11,00 em qualquer modo) e o Hambúrguer ficam fora; o Hambúrguer de forno entra. Vale o horário em que o pedido é feito, no fuso de São Paulo; o site atualiza sozinho a cada minuto.

## Onde mudar o quê

- `catalogo.py`: produtos, sabores, tamanhos, preços, esteira e sinal mínimo.
- `pedido.py`: regras do carrinho, validação e texto da mensagem do WhatsApp.
- `horario.py`: funcionamento e horário da promoção.
- `estufa.py`: estoque da estufa e reservas (SQLite).
- `app.py`: rotas do site, da API e do painel.
- `templates/`, `static/`: páginas, visual e interações.

## Testes

```bash
.venv\Scripts\python -m pytest
```
