/**
 * As medidas que a grade e a linha do tempo **precisam** compartilhar.
 *
 * Não é organização: é correção. As duas metades do Gantt desenham a mesma
 * linha em painéis diferentes, e um pixel de diferença na altura da linha faz a
 * barra descolar do nome dela conforme se rola — o defeito clássico de split
 * view, e o mais difícil de perceber no meio da tela cheia.
 */
export const ALTURA_LINHA = 30
export const ALTURA_BARRA = 15
export const ALTURA_CABECALHO = 46
/** Linhas desenhadas além da janela visível, para a rolagem não mostrar vazio
 *  antes de o React alcançar. */
export const FOLGA_VIRTUAL = 8
