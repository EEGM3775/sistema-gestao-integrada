/**
 * Comparação de texto que não exige acento — a metade de tela da mesma decisão.
 *
 * O par deste arquivo é [`backend/nucleo/busca.py`](../../../backend/nucleo/busca.py),
 * que faz o mesmo no Postgres com a extensão `unaccent`. Os dois existem porque
 * a busca do produto tem de achar `Fundação` quando a pessoa digita `fundacao`:
 * quem digita rápido digita sem acento, e no celular do canteiro ninguém vai
 * caçar o `ç`. Sem isto, a conclusão de quem procura é que o dado não existe.
 *
 * **Os dois lados precisam da mesma régua.** Uma busca que o servidor resolve
 * sem acento e a tela refiltra com acento devolve menos do que veio — e o
 * sintoma é o pior possível: a lista pisca com o resultado certo e some.
 */

/**
 * Minúsculas e sem acento, para comparar.
 *
 * `NFD` separa a letra do sinal (`ç` → `c` + cedilha) e a faixa
 * `̀-ͯ` é o bloco de diacríticos combinantes do Unicode, que sai
 * inteiro. Serve para português e para o resto do alfabeto latino — `ü`, `ñ` e
 * `å` caem junto, sem lista de exceção para manter.
 *
 * **Não normaliza o `ß` nem o `ø`**, que não são letra+sinal e sobrevivem à
 * decomposição. É limite declarado, não descuido: tratá-los pediria uma tabela
 * de substituição, e nenhum deles aparece em nome de disciplina, obra ou insumo
 * de projeto brasileiro.
 */
export function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/**
 * `alvo` contém `termo`, ignorando acento e caixa.
 *
 * Termo vazio casa com tudo — é o estado da caixa de busca em repouso, e
 * devolver `false` aqui esvaziaria a lista antes de alguém digitar.
 */
export function contemSemAcento(alvo: string, termo: string): boolean {
  if (!termo) return true
  return normalizar(alvo).includes(normalizar(termo))
}
