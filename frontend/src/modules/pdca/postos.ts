import type { CodigoPosto, Consequencia, OrigemDaFila } from './types'

export interface Posto {
  codigo: CodigoPosto
  rotulo: string
  cadencia: string
  /** Quem não tem a permissão vê o cadeado com o motivo — o caminho existe
   *  para ele, e o administrador pode liberar. */
  permissao: string
  /** Posto desenhado e ainda não construído. Aparece no rail porque a estrutura
   *  é a mesma desde o primeiro dia; a página diz o que ele fará. */
  noAr: boolean
}

/** Os seis postos, **na ordem da cadência** — do que se olha todo dia ao que se
 *  mexe uma vez por mês. O rail não cresce por fatia: capacidade nova entra num
 *  posto existente, e só uma cadência nova justificaria um sétimo. */
export const POSTOS: Posto[] = [
  { codigo: 'hoje', rotulo: 'Hoje', cadencia: 'todo dia', permissao: 'pdca.cronograma.view', noAr: true },
  { codigo: 'semana', rotulo: 'Semana', cadencia: 'semanal', permissao: 'pdca.programacao.view', noAr: true },
  { codigo: 'plano', rotulo: 'Plano', cadencia: 'por evento', permissao: 'pdca.cronograma.view', noAr: true },
  { codigo: 'medicao', rotulo: 'Medição', cadencia: 'mensal', permissao: 'pdca.medicao.view', noAr: false },
  { codigo: 'qualidade', rotulo: 'Qualidade', cadencia: 'contínua', permissao: 'pdca.verificacao.view', noAr: false },
  { codigo: 'seguranca', rotulo: 'Segurança', cadencia: 'diária', permissao: 'pdca.ocorrencia.view', noAr: false },
]

/** De que assunto a linha veio → **em que posto ela se resolve**.
 *
 *  O servidor manda a origem (domínio) e não a rota, porque navegação é da
 *  tela: se ele mandasse `/app/pdca/o/:id/qualidade`, renomear um posto viraria
 *  mudança de API. */
export const POSTO_DA_ORIGEM: Record<OrigemDaFila, CodigoPosto> = {
  seguranca: 'seguranca',
  medicao: 'medicao',
  programacao: 'semana',
  restricao: 'semana',
  qualidade: 'qualidade',
}

/** Os degraus de consequência, na ordem em que doem — prazo legal primeiro,
 *  retrabalho por último. É a ordem que o servidor já devolve; isto aqui é só
 *  o rótulo e a cor de cada degrau. */
export const DEGRAUS: {
  codigo: Consequencia
  rotulo: string
  explica: string
  pill: 'danger' | 'accent' | 'info' | 'slate'
}[] = [
  {
    codigo: 'prazo_legal', rotulo: 'Prazo legal', pill: 'danger',
    explica: 'Tem prazo em lei e multa — não se recupera depois.',
  },
  {
    codigo: 'seguranca', rotulo: 'Segurança', pill: 'danger',
    explica: 'Pode estar escondendo uma comunicação devida.',
  },
  {
    codigo: 'dinheiro', rotulo: 'Dinheiro', pill: 'accent',
    explica: 'O pagamento do empreiteiro depende desta decisão.',
  },
  {
    codigo: 'compromisso', rotulo: 'Compromisso assumido', pill: 'info',
    explica: 'A equipe assumiu e a semana precisa fechar.',
  },
  {
    codigo: 'retrabalho', rotulo: 'Retrabalho', pill: 'slate',
    explica: 'Custa serviço refeito se ficar parado.',
  },
]
