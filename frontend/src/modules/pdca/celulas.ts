import { dateToBR } from '@/utils/dates'
import type { Atividade, ChaveColuna } from './types'

// ---------------------------------------------------------------------------
// Como cada coluna vira texto
// ---------------------------------------------------------------------------
//
// Duas funções, e não uma: o que se **lê** e o que se **digita** são diferentes
// de propósito. A data aparece 04/05/2026 e é digitada assim; o peso aparece
// como moeda quando vem do orçamento e como número quando foi informado; a
// célula sem dado diz "sem apuração" na leitura e abre **vazia** na edição —
// digitar por cima de um rótulo seria apagá-lo à mão.

/** O texto de uma célula — exportado porque o CSV precisa exatamente do que a
 *  tela mostra. Duas verdades sobre a mesma coluna (uma na grade, outra no
 *  arquivo) é como se descobre, tarde, que o relatório não bate com o sistema. */
export function valorExibido(
  a: Atividade, chave: ChaveColuna, predecessoras: Map<number, string>,
): { texto: string; esmaecido?: boolean } {
  switch (chave) {
    case 'codigo': return { texto: a.codigo }
    case 'nome': return { texto: a.nome }
    case 'duracao_dias':
      if (a.eh_marco) return { texto: 'marco', esmaecido: true }
      if (a.tem_filhos) return { texto: '—', esmaecido: true }
      return { texto: a.duracao_dias == null ? '—' : `${a.duracao_dias} d` }
    case 'inicio_cedo': return data(a.inicio_cedo)
    case 'termino_cedo': return data(a.termino_cedo)
    case 'inicio_tarde': return data(a.inicio_tarde)
    case 'termino_tarde': return data(a.termino_tarde)
    case 'predecessoras': {
      const texto = predecessoras.get(a.atividade_id) ?? ''
      return texto ? { texto } : { texto: '—', esmaecido: true }
    }
    case 'folga_total':
      if (a.critica) return { texto: 'crítica' }
      return a.folga_total == null ? { texto: '—', esmaecido: true } : { texto: `${a.folga_total} d` }
    case 'folga_livre':
      return a.folga_livre == null ? { texto: '—', esmaecido: true } : { texto: `${a.folga_livre} d` }
    case 'nao_comecar_antes_de': return data(a.nao_comecar_antes_de)
    case 'peso': {
      if (a.peso == null) return { texto: 'sem apuração', esmaecido: true }
      const numero = Number(a.peso)
      return {
        texto: a.peso_origem === 'orcado'
          ? numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
          : numero.toLocaleString('pt-BR', { maximumFractionDigits: 2 }),
      }
    }
    case 'peso_informado':
      if (a.item_orcado) return { texto: 'vale o orçado', esmaecido: true }
      return a.peso_informado == null
        ? { texto: '—', esmaecido: true }
        : { texto: Number(a.peso_informado).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) }
    case 'item_orcado': return ou(a.item_orcado_rotulo, 'sem vínculo')
    case 'etapa': return ou(a.etapa_nome, 'sem etapa')
    case 'local': return ou(a.local_rotulo, 'sem local')
    case 'responsavel': return ou(a.responsavel_nome, 'sem responsável')
    case 'calendario': return ou(a.calendario_nome, 'o do cronograma')
    case 'observacao': return ou(a.observacao, '')
    default: return { texto: '' }
  }
}

export function valorParaEdicao(a: Atividade, chave: ChaveColuna, predecessoras: Map<number, string>): string {
  switch (chave) {
    case 'codigo': return a.codigo
    case 'nome': return a.nome
    case 'duracao_dias': return a.duracao_dias == null ? '' : String(a.duracao_dias)
    case 'nao_comecar_antes_de': return a.nao_comecar_antes_de ? dateToBR(a.nao_comecar_antes_de) : ''
    case 'predecessoras': return predecessoras.get(a.atividade_id) ?? ''
    case 'peso_informado': return a.peso_informado == null ? '' : String(a.peso_informado)
    case 'observacao': return a.observacao ?? ''
    default: return ''
  }
}

const data = (iso: string | null) => (iso ? { texto: dateToBR(iso) } : { texto: '—', esmaecido: true })
const ou = (texto: string | null, rotulo: string) =>
  texto ? { texto } : { texto: rotulo || '—', esmaecido: true }
