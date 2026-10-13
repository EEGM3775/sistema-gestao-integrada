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
  // *Decisão do dono, 10/10/2026:* o Controle absorve o Hoje e a Semana e
  // recebe o custo e o material da obra — o que se olha todo dia e toda
  // semana para saber se a obra está andando e gastando como o plano manda.
  { codigo: 'controle', rotulo: 'Controle', cadencia: 'diária e semanal', permissao: 'pdca.cronograma.view', noAr: true },
  { codigo: 'plano', rotulo: 'Plano', cadencia: 'por evento', permissao: 'pdca.cronograma.view', noAr: true },
  { codigo: 'medicao', rotulo: 'Medição', cadencia: 'mensal', permissao: 'pdca.medicao.view', noAr: true },
  { codigo: 'qualidade', rotulo: 'Qualidade', cadencia: 'contínua', permissao: 'pdca.verificacao.view', noAr: true },
  { codigo: 'seguranca', rotulo: 'Segurança', cadencia: 'diária', permissao: 'pdca.ocorrencia.view', noAr: true },
]

/** Onde a pessoa cai: um dos seis postos ou a segunda superfície. */
export type Porta = CodigoPosto | 'campo'

/** **O papel escolhe a porta, e nunca esconde o resto** (§3.3 da planta).
 *
 *  A chave é o nome da persona de fábrica (`TEMPLATES_PAPEL` da IAM), que é o
 *  nome com que o papel nasce no tenant. Papel renomeado ou montado à mão não
 *  casa com nada e cai em `HOJE` — a fila de decisão, que é a porta de quem
 *  não tem uma só.
 *
 *  **A ordem é a precedência** de quem acumula papéis. Primeiro quem assina
 *  (fiscal, diretoria): a fila do `HOJE` já traz tudo o que espera por eles.
 *  Depois a ordem de consequência da §4.5 — o prazo legal da CAT antes do
 *  dinheiro da medição, o dinheiro antes do compromisso da semana, o
 *  compromisso antes do retrabalho —, o plano, que se mexe por evento, e por
 *  último o campo: quem tem um papel de escritório está abrindo o escritório. */
const PORTA_DO_PAPEL: [string, Porta][] = [
  ['fiscal_de_obra', 'controle'],
  ['diretoria', 'controle'],
  ['tecnico_seguranca', 'seguranca'],
  ['gestor_contratos', 'medicao'],
  ['engenharia', 'controle'],
  ['tecnico_qualidade', 'qualidade'],
  ['planejador', 'plano'],
  ['campo', 'campo'],
]

/** A porta de quem tem estes papéis. **A permissão vence o nome**: papel
 *  recomposto sem o verbo do posto não manda ninguém para um cadeado, passa
 *  para o próximo papel da pessoa. */
export function portaDoPapel(
  papeis: readonly string[],
  pode: (permissao: string) => boolean,
): Porta {
  for (const [papel, porta] of PORTA_DO_PAPEL) {
    if (!papeis.includes(papel)) continue
    if (porta === 'campo') return porta
    const posto = POSTOS.find((p) => p.codigo === porta)
    if (posto && pode(posto.permissao)) return porta
  }
  return 'controle'
}

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
      return `${raiz}/controle?aba=semana`
    case 'restricao':
      return `${raiz}/controle?aba=semana`
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
  programacao: 'controle',
  restricao: 'controle',
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
