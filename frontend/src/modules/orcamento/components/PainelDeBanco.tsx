import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Database, PanelRightClose, Search } from 'lucide-react'
import { CAPS, inp, Loading, mono, Select } from '../ui'
import { num } from '../lib'
import * as api from '../api/orcamentoApi'
import { orcKeys } from '../api/queryKeys'
import { useBasesResumo } from '../hooks'
import SeletorDeBase from './SeletorDeBase'
import type { InsumoReferencia } from '../types'

/** O banco de preço **ao lado** da planilha — ORC.10f.
 *
 *  **O que isto muda em relação ao modal.** A janela de inserir continua sendo
 *  o caminho de quem monta um bloco de uma vez: ela tem cesta, paginação e as
 *  três origens. O que ela não faz é o gesto do Arquimedes — a árvore do banco
 *  aberta do lado, permanente, de onde se arrasta um serviço para o ponto exato
 *  da planilha. Buscar, achar, arrastar e ver o total mexer sem nenhum diálogo
 *  no meio é o que faz orçar parecer montar, e não preencher formulário.
 *
 *  **Por que os dois convivem.** Marcar quarenta itens arrastando um a um seria
 *  pior que o modal; inserir um item no meio de um capítulo pelo modal obriga a
 *  inserir no fim e depois mover. São gestos diferentes, e cada um é o melhor no
 *  seu caso — o painel não substitui a janela, fica ao lado dela.
 *
 *  **De onde vem o preço.** Da publicação aberta **aqui**, que é a mesma regra
 *  da ORC.10a: o que se pesca vem com o preço do lugar de onde foi pescado.
 */
export default function PainelDeBanco({ baseDoOrcamento, onArrastar, onSoltarFora, onFechar }: {
  /** Abre na publicação do orçamento — é a mais provável, não a mais recente. */
  baseDoOrcamento: number | null
  /** Começou a arrastar: a página guarda o que está no ar para a grade saber. */
  onArrastar: (referencia: InsumoReferencia | null) => void
  /** Soltou em lugar nenhum — a página limpa o estado de arrasto. */
  onSoltarFora: () => void
  onFechar: () => void
}) {
  const { data: bases } = useBasesResumo()
  const [baseId, setBaseId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState<'' | 'insumo' | 'composicao'>('composicao')

  useEffect(() => {
    if (baseId !== '' || !bases || bases.length === 0) return
    const doOrcamento = bases.find(b => b.base_id === baseDoOrcamento)
    setBaseId(doOrcamento?.base_id ?? bases[0].base_id)
  }, [bases, baseId, baseDoOrcamento])

  const params = useMemo(() => ({
    base: baseId || undefined,
    search: busca || undefined,
    tipo: tipo || undefined,
    // Mesmo desempate do modal: descrição não é única, e sem critério estável
    // duas páginas do mesmo resultado repetem uma linha e engolem outra.
    ordering: 'descricao,codigo',
    page_size: 40,
  }), [baseId, busca, tipo])

  const referencias = useQuery({
    queryKey: orcKeys.referencias.list(params),
    queryFn: () => api.referencias.listar(params),
    enabled: baseId !== '',
    placeholderData: keepPreviousData,
  })

  return (
    <aside style={{
      flex: '0 0 318px', minWidth: 318, display: 'flex', flexDirection: 'column', minHeight: 0,
      borderLeft: '1px solid var(--line)', background: 'var(--surface-2)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '8px 10px',
        borderBottom: '1px solid var(--line)', flex: 'none',
      }}>
        <Database size={13} style={{ color: 'var(--ink-3)' }} />
        <span style={{ ...CAPS, flex: 1 }}>Banco de preço</span>
        <button
          onClick={onFechar}
          title="Fechar o painel"
          aria-label="Fechar o painel do banco de preço"
          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 2, display: 'flex' }}
        ><PanelRightClose size={14} /></button>
      </div>

      <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 7, flex: 'none' }}>
        <SeletorDeBase bases={bases ?? []} valor={baseId} onChange={setBaseId} style={{ width: '100%' }} />
        <Select
          value={tipo}
          onChange={e => setTipo(e.target.value as '' | 'insumo' | 'composicao')}
          style={{ width: '100%', maxWidth: 'none', fontSize: 12 }}
        >
          <option value="composicao">Só composições (serviços)</option>
          <option value="insumo">Só insumos</option>
          <option value="">Insumos e composições</option>
        </Select>
        <div style={{ position: 'relative' }}>
          <Search size={13} style={{ position: 'absolute', left: 9, top: 8, color: 'var(--ink-3)' }} />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Código ou descrição"
            style={{ ...inp, paddingLeft: 28, fontSize: 12 }}
          />
        </div>
      </div>

      <div style={{
        padding: '0 10px 6px', fontSize: 11, color: 'var(--ink-3)', flex: 'none', lineHeight: 1.4,
      }}>
        Arraste um item para a planilha. Solte <b>no meio</b> de uma etapa para entrar dentro dela,
        ou <b>na borda</b> de uma linha para entrar acima ou abaixo.
      </div>

      <div
        className="orc-grade"
        style={{ flex: 1, minHeight: 0, overflowY: 'auto', overscrollBehavior: 'contain' }}
      >
        {baseId === '' ? (
          <div style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)', textAlign: 'center' }}>
            Escolha uma publicação acima.
          </div>
        ) : referencias.isLoading ? <Loading /> : (referencias.data?.results.length ?? 0) === 0 ? (
          <div style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)', textAlign: 'center' }}>
            Nada encontrado nesta publicação.
          </div>
        ) : referencias.data?.results.map(r => (
          <div
            key={r.referencia_id}
            draggable
            onDragStart={e => {
              onArrastar(r)
              e.dataTransfer.effectAllowed = 'copy'
              e.dataTransfer.setData('text/plain', r.codigo)
            }}
            onDragEnd={onSoltarFora}
            title={`${r.codigo} — ${r.descricao}`}
            style={{
              padding: '6px 10px', borderBottom: '1px solid var(--line-2)',
              cursor: 'grab', fontSize: 11.5, background: 'var(--surface)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <span style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)', flex: 'none' }}>{r.codigo}</span>
              <span style={{
                ...CAPS, fontSize: 8.5, padding: '1px 4px', borderRadius: 3, flex: 'none',
                background: r.tipo === 'composicao' ? 'var(--accent-soft)' : 'var(--inset)',
                color: r.tipo === 'composicao' ? 'var(--accent-ink)' : 'var(--ink-3)',
              }}>{r.tipo === 'composicao' ? 'serviço' : 'insumo'}</span>
              <span style={{ flex: 1 }} />
              <span style={{ ...mono, fontSize: 11, color: 'var(--ink-2)', flex: 'none' }}>
                {num(r.custo_unitario, 2)}
              </span>
            </div>
            <div style={{
              color: 'var(--ink-2)', display: '-webkit-box', WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical', overflow: 'hidden', lineHeight: 1.35,
            }}>{r.descricao}</div>
            <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>{r.unidade}</div>
          </div>
        ))}
      </div>

      {(referencias.data?.count ?? 0) > 40 && (
        <div style={{
          padding: '6px 10px', fontSize: 10.5, color: 'var(--ink-3)', flex: 'none',
          borderTop: '1px solid var(--line)',
        }}>
          {referencias.data?.count} resultados — refine a busca ou use a janela <b>Item</b> para
          marcar vários de uma vez.
        </div>
      )}
    </aside>
  )
}
