import type { ChaveColuna, ColunaGrade } from './types'

// ---------------------------------------------------------------------------
// O catálogo de colunas
// ---------------------------------------------------------------------------
//
// Todas as colunas que a grade sabe desenhar moram aqui, e o usuário escolhe
// quais aparecem. É o que separa esta grade de uma tabela: quem monta a rede
// quer EAP, duração e predecessoras; quem confere prazo quer as datas tarde e a
// folga; quem amarra custo quer o item orçado. São três planilhas diferentes
// sobre os mesmos dados, e nenhuma delas cabe na outra.

export const CATALOGO_COLUNAS: ColunaGrade[] = [
  { chave: 'codigo', rotulo: 'EAP', largura: 104, alinhamento: 'left', editavel: true },
  { chave: 'nome', rotulo: 'Atividade', largura: 268, alinhamento: 'left', editavel: true },
  { chave: 'duracao_dias', rotulo: 'Duração', curto: 'Dur.', largura: 64, alinhamento: 'right', editavel: true },
  { chave: 'inicio_cedo', rotulo: 'Início', largura: 88, alinhamento: 'center', editavel: false, derivada: true },
  { chave: 'termino_cedo', rotulo: 'Término', largura: 88, alinhamento: 'center', editavel: false, derivada: true },
  { chave: 'predecessoras', rotulo: 'Predecessoras', curto: 'Predec.', largura: 156, alinhamento: 'left', editavel: true },
  { chave: 'folga_total', rotulo: 'Folga total', curto: 'Folga', largura: 70, alinhamento: 'right', editavel: false, derivada: true },
  { chave: 'folga_livre', rotulo: 'Folga livre', curto: 'F. livre', largura: 70, alinhamento: 'right', editavel: false, derivada: true },
  { chave: 'inicio_tarde', rotulo: 'Início tarde', curto: 'Ini. tarde', largura: 88, alinhamento: 'center', editavel: false, derivada: true },
  { chave: 'termino_tarde', rotulo: 'Término tarde', curto: 'Tér. tarde', largura: 88, alinhamento: 'center', editavel: false, derivada: true },
  { chave: 'nao_comecar_antes_de', rotulo: 'Não antes de', curto: 'Não antes', largura: 104, alinhamento: 'center', editavel: true },
  { chave: 'peso', rotulo: 'Peso efetivo', curto: 'Peso', largura: 110, alinhamento: 'right', editavel: false },
  { chave: 'peso_informado', rotulo: 'Peso informado', curto: 'Peso inf.', largura: 104, alinhamento: 'right', editavel: true },
  { chave: 'item_orcado', rotulo: 'Item orçado', largura: 190, alinhamento: 'left', editavel: false },
  { chave: 'etapa', rotulo: 'Etapa da obra', curto: 'Etapa', largura: 150, alinhamento: 'left', editavel: false },
  { chave: 'local', rotulo: 'Local', largura: 150, alinhamento: 'left', editavel: false },
  { chave: 'responsavel', rotulo: 'Responsável', largura: 150, alinhamento: 'left', editavel: false },
  { chave: 'calendario', rotulo: 'Calendário', largura: 130, alinhamento: 'left', editavel: false },
  { chave: 'observacao', rotulo: 'Observação', largura: 220, alinhamento: 'left', editavel: true },
]

/** A planilha que abre: a de quem monta a rede. As colunas de conferência e de
 *  vínculo entram quando quem confere ou quem amarra custo liga a dele. */
export const COLUNAS_PADRAO: ChaveColuna[] = [
  'codigo', 'nome', 'duracao_dias', 'inicio_cedo', 'termino_cedo', 'predecessoras',
  'folga_total', 'peso',
]
