/** O vocabulário da qualidade e da segurança — rótulo, tom e regra de tela
 *  que mais de um componente usa. Fica fora dos componentes para o fast refresh
 *  do Vite continuar funcionando (arquivo de componente só exporta componente). */
import type {
  GravidadeNc, ResultadoItem, StatusNc, StatusOcorrencia, TipoOcorrencia, TipoRestricao,
} from './types'

/** As restrições que se destravam **comprando** — o espelho do
 *  `TIPOS_QUE_VIRAM_COMPRA` do servidor. Material vira compra de insumo;
 *  equipamento (locação) e mão de obra (empreitada), contratação de serviço. */
export const TIPOS_QUE_VIRAM_COMPRA: ReadonlySet<TipoRestricao> = new Set<TipoRestricao>([
  'material', 'equipamento', 'mao_de_obra',
])

export const GRAVIDADES: { valor: GravidadeNc; rotulo: string; explica: string; tom: 'slate' | 'accent' | 'danger' }[] = [
  { valor: 'menor', rotulo: 'Menor', explica: 'corrige-se na frente', tom: 'slate' },
  { valor: 'maior', rotulo: 'Maior', explica: 'o serviço não é aceito assim', tom: 'accent' },
  { valor: 'critica', rotulo: 'Crítica', explica: 'para o serviço', tom: 'danger' },
]

export const TOM_DA_GRAVIDADE: Record<GravidadeNc, 'slate' | 'accent' | 'danger'> = {
  menor: 'slate',
  maior: 'accent',
  critica: 'danger',
}

export const TOM_DO_STATUS_DA_NC: Record<StatusNc, 'danger' | 'accent' | 'good' | 'slate'> = {
  aberta: 'danger',
  em_tratamento: 'accent',
  encerrada: 'good',
  cancelada: 'slate',
}

export const RESPOSTAS: { valor: ResultadoItem; rotulo: string; tom: 'good' | 'danger' | 'slate' | 'accent' }[] = [
  { valor: 'conforme', rotulo: 'Conforme', tom: 'good' },
  { valor: 'nao_conforme', rotulo: 'Não conforme', tom: 'danger' },
  { valor: 'nao_aplicavel', rotulo: 'Não se aplica', tom: 'slate' },
  { valor: 'pendente', rotulo: 'Pendente', tom: 'accent' },
]

export const TOM_DA_RESPOSTA: Record<ResultadoItem, 'good' | 'danger' | 'slate' | 'accent'> = {
  conforme: 'good',
  nao_conforme: 'danger',
  nao_aplicavel: 'slate',
  pendente: 'accent',
}

/** Desvio precisa dizer o quê — e é o servidor que recusa, com o número do
 *  item; aqui a tela só não deixa o botão parecer que basta. */
export const exigeObservacao = (r: ResultadoItem) => r === 'nao_conforme' || r === 'nao_aplicavel'

export const TIPOS_DE_OCORRENCIA: {
  valor: TipoOcorrencia; rotulo: string; explica: string; vitima: boolean
  tom: 'slate' | 'accent' | 'danger'
}[] = [
  { valor: 'quase_acidente', rotulo: 'Quase-acidente', explica: 'ninguém se machucou, nada quebrou', vitima: false, tom: 'slate' },
  { valor: 'incidente', rotulo: 'Incidente', explica: 'dano material, sem ferido', vitima: false, tom: 'accent' },
  { valor: 'acidente_tipico', rotulo: 'Acidente', explica: 'alguém se feriu no trabalho', vitima: true, tom: 'danger' },
  { valor: 'acidente_trajeto', rotulo: 'Acidente de trajeto', explica: 'no caminho de casa ou para casa', vitima: true, tom: 'danger' },
  { valor: 'doenca_ocupacional', rotulo: 'Doença ocupacional', explica: 'causada pelo trabalho', vitima: true, tom: 'danger' },
]

export const TOM_DO_STATUS_DA_OCORRENCIA: Record<StatusOcorrencia, 'danger' | 'accent' | 'good' | 'slate'> = {
  aberta: 'danger',
  em_investigacao: 'accent',
  encerrada: 'good',
  cancelada: 'slate',
}
