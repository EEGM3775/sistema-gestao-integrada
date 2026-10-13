/** O caminho do contrato de medição — as paradas e onde ele está.
 *  Usado pelo mapa (`TrilhaDoContrato`) e pela página, que abre na próxima. */
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type { LinhaDeContrato } from './types'

export type Parada = 'planilha' | 'vigente' | 'medir' | 'aprovacao' | 'pago'
export type Desvio = 'aditivos' | 'retencao'

type Estado = 'feito' | 'agora' | 'depois'

export interface ParadaDoMapa {
  chave: Parada
  rotulo: string
  diz: string
  estado: Estado
}

/** As paradas do contrato, e onde ele está — **derivado do saldo**, sem
 *  pergunta nenhuma ao usuário. A primeira parada não feita é a próxima. */
export function paradasDoContrato(c: LinhaDeContrato): ParadaDoMapa[] {
  const s = c.saldo
  const reais = (v: string) => formatBRL(apiDecimalToCents(v))
  const temPlanilha = s.itens > 0 || (c.regime !== 'unitario' && apiDecimalToCents(s.valor_contratado) > 0)
  const vigente = c.status !== 'rascunho'
  const emRascunho = apiDecimalToCents(s.medido_rascunho) > 0
  const emEscada = apiDecimalToCents(s.medido_em_aprovacao) > 0
  const aprovado = apiDecimalToCents(s.medido_aprovado)
  const contratado = apiDecimalToCents(s.valor_contratado)
  const pct = contratado > 0 ? Math.min(100, Math.round((aprovado / contratado) * 100)) : 0

  const feitos: Record<Parada, boolean> = {
    planilha: temPlanilha,
    vigente,
    medir: s.medicoes > 0 && !emRascunho,
    aprovacao: aprovado > 0 && !emEscada,
    pago: contratado > 0 && aprovado >= contratado,
  }
  const ordem: Parada[] = ['planilha', 'vigente', 'medir', 'aprovacao', 'pago']
  const proxima = ordem.find((p) => !feitos[p])
  const estado = (p: Parada): Estado => (feitos[p] ? 'feito' : p === proxima ? 'agora' : 'depois')

  return [
    { chave: 'planilha', rotulo: 'Contrato', diz: s.itens > 0 ? `${s.itens} ${s.itens === 1 ? 'item' : 'itens'} · ${reais(s.valor_contratado)}` : 'o que foi combinado', estado: estado('planilha') },
    { chave: 'vigente', rotulo: 'Vigente', diz: vigente ? c.status_rotulo.toLowerCase() : 'em rascunho', estado: estado('vigente') },
    { chave: 'medir', rotulo: 'Medir', diz: emRascunho ? `boletim aberto · ${reais(s.medido_rascunho)}` : s.medicoes > 0 ? `${s.medicoes} ${s.medicoes === 1 ? 'boletim' : 'boletins'}` : 'o período do mês', estado: estado('medir') },
    { chave: 'aprovacao', rotulo: 'Aprovação', diz: emEscada ? `${reais(s.medido_em_aprovacao)} no atesto` : aprovado > 0 ? `${reais(s.medido_aprovado)} aprovados` : 'quem atesta', estado: estado('aprovacao') },
    { chave: 'pago', rotulo: 'Executado', diz: `${pct}% · saldo ${reais(s.saldo)}`, estado: estado('pago') },
  ]
}

/** A parada que a tela abre quando o endereço não diz qual. */
export function paradaInicial(c: LinhaDeContrato): Parada {
  const agora = paradasDoContrato(c).find((n) => n.estado === 'agora')
  return agora?.chave ?? 'medir'
}
