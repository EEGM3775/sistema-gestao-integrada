/**
 * Primitivos-base da Malha v1 — a camada compartilhada descrita em
 * [docs/frontend.md §1.2/§1.3](../../../../docs/frontend.md) e
 * [docs/identidade-visual.md §10](../../../../docs/identidade-visual.md).
 *
 * Regra: nada aqui usa cor fixa. Tudo sai dos tokens de `index.css`, e por isso
 * acompanha tema claro/escuro sem reescrita. Módulos novos consomem daqui em vez
 * de recriar o kit — SCM e SIL têm cópias locais anteriores a este arquivo e
 * migram para cá na vez de cada um.
 */
export { Card } from './Card'
export { Pill } from './Pill'
export type { PillKind } from './Pill'
export { Num } from './Num'
export { KpiTile } from './KpiTile'
export { SectionHead } from './SectionHead'
export { Spinner, Loading, Empty, EmBreve } from './States'
export { Btn } from './Btn'
export { Modal } from './Modal'

/**
 * Entrada numérica — dinheiro, contagem e decimal. Promovidos do `MoneyInput`
 * local do ERP, que pinta cor fixa e some no tema escuro. Estes saem só de
 * token e resolvem os três defeitos do `<input type="number">` controlado:
 * o valor mostrado difere do digitado, o zero à esquerda sobrevive no DOM, e a
 * roda do mouse altera o número sem ninguém pedir.
 */
export { CampoMoeda, CampoInteiro, CampoDecimal, paraNumero, daApi } from './Campos'

/**
 * MAP.1 — a superfície espacial. Fica aqui, e não num kit do módulo Maps,
 * porque obra, fornecedor, almoxarifado e voo caem no MESMO mapa: um mapa por
 * módulo repetiria a dívida dos kits paralelos.
 */
export { Mapa } from './Mapa'
export type { PontoMapa, CamadaGeoJSON, CamadaRaster } from './Mapa'

/**
 * IE.0c — importação e exportação, os dois componentes que **todo módulo**
 * consome ([docs/modulos/funcoesimpexp.md §10](../../../../docs/modulos/funcoesimpexp.md)).
 * Ambos somem sozinhos quando a pessoa não tem acesso total ao recurso: quem
 * decide é o backend, não uma prop de permissão.
 */
export { BotaoExportar } from './impexp/BotaoExportar'
export { WizardImportacao } from './impexp/WizardImportacao'
/**
 * Reabrir um lote que parou esperando gente — a conferência que ficou
 * pendente, o de-para que ninguém respondeu, o erro cuja mensagem só existe
 * dentro do diálogo. Sem isto, fechar a aba no meio de uma importação
 * obrigava a subir a planilha de novo, mesmo com o arquivo já no servidor.
 */
export { RetomarImportacao, podeRetomar } from './impexp/WizardImportacao'
/**
 * IE.3c — o irmão de natureza `arquivo` do wizard: pasta → conferência →
 * decisão. Aparece só onde o recurso declara `natureza: 'arquivo'`, então a
 * tela que o monta não precisa saber qual dos dois é o certo.
 */
export { WizardArquivos } from './impexp/WizardArquivos'
export { useRecursos, useRecurso, useCatalogoImpExp } from './impexp/hooks'
export type {
  LimitesDoPlano, RecursoImpExp, ResumoImportacao, StatusImportacao,
} from './impexp/api'
