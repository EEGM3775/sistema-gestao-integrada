import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Search } from 'lucide-react'
import { Card, Empty, Loading, Pill } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { useLocais } from '../hooks'
import type { LocalObra } from '../types'

interface NoDaArvore {
  local: LocalObra
  nivel: number
  filhos: NoDaArvore[]
}

/** A hierarquia construtiva — o eixo Y da linha de balanço e o endereço de
 *  tudo o que acontece no campo. */
export function PainelLocais({ obraId }: { obraId: number }) {
  const { data, isLoading, isError } = useLocais(obraId)
  const [busca, setBusca] = useState('')
  const [fechados, setFechados] = useState<Set<number>>(new Set())

  const arvore = useMemo(() => montar(data ?? []), [data])

  const visiveis = useMemo(() => {
    const termo = busca.trim()
    const saida: NoDaArvore[] = []
    function descer(nos: NoDaArvore[]) {
      for (const no of nos) {
        const casa = !termo || contemSemAcento(`${no.local.codigo} ${no.local.nome}`, termo)
        if (casa) saida.push(no)
        if (termo || !fechados.has(no.local.local_id)) descer(no.filhos)
      }
    }
    descer(arvore)
    return saida
  }, [arvore, busca, fechados])

  if (isLoading) return <Loading o="os locais da obra" />
  if (isError) {
    return (
      <Card>
        <Empty>Não foi possível carregar os locais. Tente de novo.</Empty>
      </Card>
    )
  }
  if (!data || data.length === 0) {
    return (
      <Card>
        <Empty>
          Esta obra ainda não tem locais. Sem eles não há linha de balanço nem
          endereço para o que o campo registra.
        </Empty>
      </Card>
    )
  }

  function alternar(id: number) {
    setFechados((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  return (
    <Card pad={false}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '11px 14px', borderBottom: '1px solid var(--line-2)',
        }}
      >
        <Search size={14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar local"
          style={{
            border: 'none', outline: 'none', background: 'transparent',
            color: 'var(--ink)', fontSize: 13, flex: 1,
          }}
        />
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
          {data.length} locais
        </span>
      </div>

      <div style={{ maxHeight: 520, overflowY: 'auto' }}>
        {visiveis.length === 0 && (
          <div style={{ padding: '16px 14px', fontSize: 12.5, color: 'var(--ink-3)' }}>
            Nenhum local com esse nome.
          </div>
        )}
        {visiveis.map((no) => {
          const temFilhos = no.filhos.length > 0
          const aberto = !fechados.has(no.local.local_id)
          return (
            <div
              key={no.local.local_id}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', paddingLeft: 14 + no.nivel * 16,
                borderBottom: '1px solid var(--line-2)',
              }}
            >
              {temFilhos && !busca.trim() ? (
                <button
                  type="button"
                  onClick={() => alternar(no.local.local_id)}
                  aria-label={aberto ? 'Recolher' : 'Expandir'}
                  style={{
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-3)', display: 'flex', padding: 0, flexShrink: 0,
                  }}
                >
                  {aberto ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>
              ) : (
                <span style={{ width: 13, flexShrink: 0 }} />
              )}

              <span
                style={{
                  fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)',
                  flexShrink: 0, minWidth: 68,
                }}
              >
                {no.local.codigo}
              </span>
              <span style={{ flex: 1, fontSize: 13, color: 'var(--ink)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {no.local.nome}
              </span>
              <Pill kind="slate">{no.local.nivel_rotulo}</Pill>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function montar(locais: LocalObra[]): NoDaArvore[] {
  const porPai = new Map<number | null, LocalObra[]>()
  for (const l of locais) {
    const chave = l.pai ?? null
    const grupo = porPai.get(chave)
    if (grupo) grupo.push(l)
    else porPai.set(chave, [l])
  }
  for (const grupo of porPai.values()) {
    grupo.sort((a, b) => (a.ordem - b.ordem) || a.codigo.localeCompare(b.codigo, 'pt-BR'))
  }

  function descer(pai: number | null, nivel: number): NoDaArvore[] {
    return (porPai.get(pai) ?? []).map((local) => ({
      local,
      nivel,
      filhos: descer(local.local_id, nivel + 1),
    }))
  }
  return descer(null, 0)
}
