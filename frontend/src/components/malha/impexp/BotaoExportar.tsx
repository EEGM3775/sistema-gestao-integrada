import { useState } from 'react'
import { Download, FileSpreadsheet, FileText } from 'lucide-react'

import { Btn } from '../Btn'
import { Modal } from '../Modal'
import { Pill } from '../Pill'
import { Spinner } from '../States'
import { baixarExportacao, exportar } from './api'
import type { ResumoExportacao } from './api'
import { useExportacaoEmCurso, useRecurso } from './hooks'

const ICONE: Record<string, typeof FileText> = {
  xlsx: FileSpreadsheet, csv: FileSpreadsheet, pdf: FileText,
}
const NOME_FORMATO: Record<string, string> = {
  xlsx: 'Excel', csv: 'CSV', pdf: 'PDF',
}

interface Props {
  /** Id do recurso declarado no backend, ex.: `orcamento.banco_preco`. */
  recurso: string
  /**
   * O recorte da tela (R7) — os mesmos filtros que a pessoa está vendo. Vai
   * inteiro como query param, e o backend separa o que é destino do que é
   * filtro pelo `contexto_requerido` da declaração.
   */
  recorte?: Record<string, string | number | undefined>
  rotulo?: string
  tam?: 'sm' | 'md'
}

/**
 * IE.0c — o botão Exportar, igual em todo módulo.
 *
 * **Some quando a pessoa não tem acesso total ao recurso** (§3/R11), em vez de
 * aparecer e dar 403 no clique. Não há prop de permissão: quem decide é o
 * backend, em `/api/impexp/recursos/` — repetir a regra aqui criaria um segundo
 * lugar para ela divergir, e o lugar que divergisse seria o que o usuário vê.
 */
export function BotaoExportar({ recurso, recorte = {}, rotulo = 'Exportar', tam = 'sm' }: Props) {
  const { recurso: declaracao } = useRecurso(recurso)
  const [aberto, setAberto] = useState(false)
  const [ocupado, setOcupado] = useState('')
  const [erro, setErro] = useState('')
  const [lote, setLote] = useState<ResumoExportacao | null>(null)

  const { data: acompanhado } = useExportacaoEmCurso(lote?.exportacao_id)
  const emCurso = acompanhado ?? lote

  if (!declaracao?.exporta) return null

  async function escolher(formato: string) {
    setErro('')
    setOcupado(formato)
    try {
      const saida = await exportar(recurso, { ...recorte, formato })
      if (saida.tipo === 'job') setLote(saida.lote)
      else setAberto(false)
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não foi possível gerar o arquivo agora.')
    } finally {
      setOcupado('')
    }
  }

  return (
    <>
      <Btn tam={tam} onClick={() => { setAberto(true); setLote(null); setErro('') }}>
        <Download size={13} />{rotulo}
      </Btn>

      {aberto && (
        <Modal
          titulo={`Exportar · ${declaracao.rotulo}`}
          onClose={() => setAberto(false)}
          rodape={<Btn tam="sm" onClick={() => setAberto(false)}>Fechar</Btn>}
        >
          {erro && (
            <div style={{
              marginBottom: 13, padding: '9px 12px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
            }}>{erro}</div>
          )}

          {emCurso ? (
            <EmGeracao lote={emCurso} nome={declaracao.rotulo} />
          ) : (
            <>
              <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
                Recorte da tela
              </p>
              <div style={{ display: 'grid', gap: 8 }}>
                {declaracao.formatos_saida.map(formato => {
                  const Icone = ICONE[formato] ?? FileText
                  return (
                    <button
                      key={formato}
                      onClick={() => escolher(formato)}
                      disabled={!!ocupado}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 11, width: '100%',
                        padding: '11px 13px', textAlign: 'left', cursor: ocupado ? 'wait' : 'pointer',
                        background: 'var(--surface-2)', border: '1px solid var(--line)',
                        borderRadius: 'var(--r-sm)', color: 'var(--ink)',
                        opacity: ocupado && ocupado !== formato ? 0.5 : 1,
                      }}
                    >
                      {ocupado === formato
                        ? <Spinner size={17} />
                        : <Icone size={17} style={{ color: 'var(--ink-3)' }} />}
                      <span style={{ flex: 1, fontSize: 13, fontWeight: 650 }}>
                        {NOME_FORMATO[formato] ?? formato.toUpperCase()}
                      </span>
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  )
}

/** R10 — acima do corte de volume o arquivo vira job, e a tela acompanha. */
function EmGeracao({ lote, nome }: { lote: ResumoExportacao; nome: string }) {
  if (lote.status === 'erro') {
    return (
      <div style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>
        Não foi possível gerar: {lote.mensagem}
      </div>
    )
  }
  if (lote.status === 'gerando') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, fontSize: 12.5, color: 'var(--ink-2)' }}>
        <Spinner size={17} />
        <span>
          Este recorte é grande, então está sendo gerado em segundo plano.
          <span style={{ display: 'block', color: 'var(--ink-3)', marginTop: 2 }}>
            Pode deixar esta janela aberta — o download aparece aqui quando ficar pronto.
          </span>
        </span>
      </div>
    )
  }
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
        <Pill kind="good">pronto</Pill>
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          {lote.linhas.toLocaleString('pt-BR')} linha(s) em {lote.formato.toUpperCase()}
        </span>
      </div>
      <Btn
        variant="primary"
        onClick={() => baixarExportacao(lote.exportacao_id, `${nome}.${lote.formato}`)}
      >
        <Download size={14} />Baixar arquivo
      </Btn>
      <p style={{ margin: '11px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
        O link vale por tempo limitado. Depois disso é só gerar de novo — e a nova saída já
        reflete o dado de agora.
      </p>
    </div>
  )
}
