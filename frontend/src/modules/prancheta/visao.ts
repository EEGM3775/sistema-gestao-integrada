import { useAuth } from '@/hooks/useAuth'

/**
 * Quem está olhando — e o que a tela deve virar por causa disso.
 *
 * São **duas telas dentro de uma**, e o corte sai das permissões que já existem
 * no backend, não de um campo novo de perfil:
 *
 * - **campo** (`prancheta.documento.view` e nada mais) — quem executa o desenho.
 *   A tela encolhe para uma obra só, sem seletor de outras: no canteiro, ver
 *   prancha de outro empreendimento não é conveniência, é risco de executar o
 *   material errado.
 * - **responsável** (tem `documento.edit` e/ou `revisao.publicar`) — quem governa
 *   o acervo. Alterna entre obras, cadastra, publica e é o **único** que vê o
 *   histórico de alterações.
 *
 * **O que isto é e o que não é:** a visão de campo é uma decisão de *interface*.
 * O gate de verdade é o do servidor (entitlement + permissão + RLS), e ele não
 * distingue obra por usuário porque o backend não tem vínculo usuário↔obra — não
 * há `Obra.responsavel` nem alocação em `rh`. Enquanto esse vínculo não existir,
 * esconder as outras obras evita o erro honesto (abrir a prancha errada), não o
 * acesso mal-intencionado. Está registrado assim em `preferencias.ts` e na
 * planta do módulo para ninguém confundir as duas coisas depois.
 */
export type Visao = 'campo' | 'responsavel'

export interface Papel {
  visao: Visao
  /** Governa o acervo: cadastra documento e envia revisão. */
  podeGerir: boolean
  /** Decide qual desenho vale em campo. */
  podePublicar: boolean
  /** Queima recurso (CPU agora, tradução paga na PRA.4). */
  podeReprocessar: boolean
  /** Histórico de alterações é exclusivo de quem responde pelo empreendimento. */
  podeVerHistorico: boolean
  /** Lê a caixa de apontamentos — separada de ver a prancha, de propósito. */
  podeVerMarcacao: boolean
  /** Aponta, comenta e mede. É o que o `campo` ganhou na PRA.3. */
  podeMarcar: boolean
  /**
   * Encerra ou reabre o apontamento. Verbo separado pelo mesmo motivo de
   * `publicar`: quem aponta não é quem declara que acabou — senão a fila
   * esvaziaria pelo lado errado, antes de o projetista responder.
   */
  podeResolver: boolean
  /**
   * Define a régua da prancha. Fica com quem governa o acervo, e **não** com
   * quem marca: recalibrar muda, de uma vez, o valor de toda medida que
   * qualquer um tirar dali.
   */
  podeCalibrar: boolean
}

export function usePapel(): Papel {
  const { hasPermission } = useAuth()
  const podeGerir = hasPermission('prancheta.documento.edit')
  const podePublicar = hasPermission('prancheta.revisao.publicar')
  // A visão continua saindo do acervo, e não das permissões de marcação: o
  // `campo` ganhou `marcacao.edit` na PRA.3 e nem por isso passou a governar
  // obras. Confundir os dois cortes daria ao tablet do canteiro o seletor de
  // empreendimento que a PRA.2 tirou de propósito.
  const responsavel = podeGerir || podePublicar

  return {
    visao: responsavel ? 'responsavel' : 'campo',
    podeGerir,
    podePublicar,
    podeReprocessar: hasPermission('prancheta.conversao.reprocessar'),
    podeVerHistorico: responsavel,
    podeVerMarcacao: hasPermission('prancheta.marcacao.view'),
    podeMarcar: hasPermission('prancheta.marcacao.edit'),
    podeResolver: hasPermission('prancheta.marcacao.resolver'),
    podeCalibrar: podeGerir,
  }
}
