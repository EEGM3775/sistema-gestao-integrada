"""Cobrança registrada direto no banco — remessa, retorno e o boleto (item 52).

O Asaas emite o boleto por nós. O CNAB é o outro caminho, o dos bancos: a
empresa tem uma **carteira de cobrança** no banco, o SGI numera os boletos
(nosso número), calcula o código de barras, gera o arquivo de **remessa** que o
banco registra e lê o arquivo de **retorno** com o que foi pago.

- `codigo_barras` — o padrão FEBRABAN comum a todos os bancos: os 44 dígitos,
  a linha digitável e o fator de vencimento.
- `bancos` — o que muda de banco para banco: o nosso número, o dígito dele e o
  "campo livre" do código de barras.
- `remessa240` / `remessa400` — o arquivo que vai ao banco.
- `retorno` — o arquivo que volta, e a baixa pelo mesmo `dar_baixa` do Asaas.
- `emissao` — a ponte com o lote de cobrança.
- `pdf` — o boleto impresso.

**Homologação.** Cada banco confere os primeiros arquivos de uma carteira nova
antes de liberá-la ("teste de remessa"). O que está aqui segue o layout
FEBRABAN 240 e os manuais de CNAB 400 de Bradesco e Itaú; as particularidades
de cada contrato (versão de layout, campos de uso do banco) aparecem nesse
teste, e são ajustadas na classe do banco em `bancos.py`.
"""
