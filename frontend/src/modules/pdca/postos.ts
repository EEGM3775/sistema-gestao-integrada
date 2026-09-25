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
  { codigo: 'medicao', rotulo: 'Medição', cadencia: 'mensal', permissao: 'pdca.medicao.view', noAr: true },
  { codigo: 'qualidade', rotulo: 'Qualidade', cadencia: 'contínua', permissao: 'pdca.verificacao.view', noAr: true },
  { codigo: 'seguranca', rotulo: 'Segurança', cadencia: 'diária', permissao: 'pdca.ocorrencia.view', noAr: true },
]

/** **O endereço do documento, e não só do posto.**
 *
 *  A mesma NC é linha na fila do dia, resultado da paleta e pino na ficha; em
 *  todos eles, clicar abre **ela**, e não a porta do posto onde a pessoa teria
 *  de procurá-la de novo. O recorte mora na query string porque é assim que
 *  cada posto já lê o documento aberto — um link colado abre no mesmo lugar.
 *
 *  `extra` traz o que a linha sabe e o documento precisa: a ação do plano se
 *  abre na NC dela, e o boletim, dentro do contrato. */
export function enderecoDoDocumento(
  obraId: number,
  tipo: string,
  id: number,
  extra: { nc?: unknown; contrato?: unknown } = {},
): string {
  const raiz = `/app/pdca/o/${obraId}`
  switch (tipo) {
    case 'nc':
      return `${raiz}/qualidade?nc=${id}`
    case 'plano_acao':
      return typeof extra.nc === 'number'
        ? `${raiz}/qualidade?nc=${extra.nc}`
        : `${raiz}/qualidade`
    case 'verificacao':
      return `${raiz}/qualidade?ficha=${id}`
    case 'ocorrencia':
      return `${raiz}/seguranca?ocorrencia=${id}`
    case 'contrato':
      return `${raiz}/medicao?contrato=${id}`
    case 'medicao':
      return typeof extra.contrato === 'number'
        ? `${raiz}/medicao?contrato=${extra.contrato}&boletim=${id}`
        : `${raiz}/medicao`
    case 'programacao':
      return `${raiz}/semana`
    case 'restricao':
      return `${raiz}/semana`
    default:
      return raiz
  }
}

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
