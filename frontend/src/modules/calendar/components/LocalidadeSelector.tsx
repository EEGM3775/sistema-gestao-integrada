import { useEffect } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import { useObrasLocalidades, useMunicipios } from '../hooks/useLocalidades'
import { UFS } from '../utils'
import type { LocalidadeSelecionada } from '../types'

interface Props {
  value: LocalidadeSelecionada
  onChange: (loc: LocalidadeSelecionada) => void
}

const selectCls: React.CSSProperties = {
  padding: '5px 6px', borderRadius: '7px', border: 'none', background: 'transparent',
  fontFamily: 'var(--font-body)', fontSize: '0.78rem', fontWeight: 500,
  color: 'var(--color-text)', outline: 'none', cursor: 'pointer', maxWidth: 168,
}

const divider = <span className="w-px h-4 shrink-0" style={{ background: '#dfe5ee' }} />

/**
 * Seletor de localidade dos feriados (Fatia F). A **obra determina** estado e
 * município (resolvidos do endereço via `nucleo.geo`); se a obra não tem endereço
 * ou nenhuma é escolhida, o usuário seleciona estado e município **livremente**.
 * O município só habilita depois que há um estado.
 */
export function LocalidadeSelector({ value, onChange }: Props) {
  const [obraId, setObraId] = usePersistedState<string>('sgi_calendar_obra', '')
  const { data: obras } = useObrasLocalidades()
  const { data: municipios } = useMunicipios(value.uf)

  // Reconcilia a seleção POR OBRA persistida com o estado atual das obras: se a
  // obra foi excluída, zera; se o endereço mudou/foi removido, re-deriva uf/ibge
  // do dado atual. Seleção manual (obraId vazio) não vai stale — não mexe nela.
  useEffect(() => {
    if (!obras || !obraId) return
    const obra = obras.find(o => String(o.obra_id) === obraId)
    if (!obra) setObraId('')                 // obra excluída
    const uf = obra?.uf || ''
    const ibge = obra?.ibge || ''
    if (uf !== value.uf || ibge !== value.ibge) onChange({ uf, ibge })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [obras])

  const escolherObra = (id: string) => {
    setObraId(id)
    const obra = obras?.find(o => String(o.obra_id) === id)
    if (obra && obra.uf) onChange({ uf: obra.uf, ibge: obra.ibge || '' })
    else if (!id) onChange({ uf: '', ibge: '' })
  }

  const escolherUf = (uf: string) => {
    setObraId('')            // escolha manual desvincula da obra
    onChange({ uf, ibge: '' })
  }

  const escolherMunicipio = (ibge: string) => {
    setObraId('')
    onChange({ uf: value.uf, ibge })
  }

  return (
    <div className="inline-flex flex-wrap items-center gap-1 rounded-xl pl-3 pr-1.5 py-1"
      style={{ background: '#f6f8fb', border: '1px solid #e6eaf1' }}>
      <span className="text-[0.7rem] font-bold uppercase tracking-wide mr-1"
        style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
        Local
      </span>

      <select style={selectCls} value={obraId} onChange={e => escolherObra(e.target.value)} aria-label="Obra">
        <option value="">Obra…</option>
        {(obras ?? []).map(o => (
          <option key={o.obra_id} value={o.obra_id}>
            {o.nome}{o.cidade ? ` — ${o.cidade}/${o.uf}` : o.uf ? ` — ${o.uf}` : ' — (sem endereço)'}
          </option>
        ))}
      </select>

      {divider}

      <select style={selectCls} value={value.uf} onChange={e => escolherUf(e.target.value)} aria-label="Estado">
        <option value="">Estado…</option>
        {UFS.map(u => (
          <option key={u.uf} value={u.uf}>{u.nome}</option>
        ))}
      </select>

      {divider}

      <select
        style={{ ...selectCls, opacity: value.uf ? 1 : 0.45, cursor: value.uf ? 'pointer' : 'not-allowed' }}
        value={value.ibge}
        onChange={e => escolherMunicipio(e.target.value)}
        disabled={!value.uf}
        aria-label="Município"
      >
        <option value="">{value.uf ? 'Município…' : 'Escolha o estado'}</option>
        {(municipios ?? []).map(m => (
          <option key={m.ibge} value={m.ibge}>{m.nome}</option>
        ))}
      </select>
    </div>
  )
}
