import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, Building2, ClipboardCheck, CornerDownLeft, FileCheck2,
  FileText, HardHat, ListTree, MapPin, Search,
} from 'lucide-react'
import { Spinner } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { useAuth } from '@/hooks/useAuth'
import { usePdca } from '../contexto'
import { useBusca, useObras } from '../hooks'
import { POSTOS } from '../postos'
import { SemPermissaoAviso } from './SemPermissaoAviso'
import type { CodigoPosto, EspecieDoPdca } from '../types'

type Resultado =
  | { grupo: string; tipo: 'posto'; chave: string; id: string; titulo: string; detalhe: string }
  | { grupo: string; tipo: 'obra'; chave: string; id: number; titulo: string; detalhe: string }
  | {
      grupo: string
      tipo: EspecieDoPdca
      chave: string
      id: number
      titulo: string
      detalhe: string
      obra: number | null
    }

/** Onde cada espécie se resolve. É o que transforma um resultado de busca em
 *  navegação — e é conhecimento da tela, não da API. */
const POSTO_DA_ESPECIE: Record<string, CodigoPosto> = {
  atividade: 'plano',
  local: 'plano',
  contrato: 'medicao',
  medicao: 'medicao',
  verificacao: 'qualidade',
  nc: 'qualidade',
  ocorrencia: 'seguranca',
}

const ICONE: Record<string, typeof ListTree> = {
  obra: Building2,
  posto: ListTree,
  atividade: ListTree,
  local: MapPin,
  contrato: FileText,
  medicao: FileCheck2,
  verificacao: ClipboardCheck,
  nc: AlertTriangle,
  ocorrencia: HardHat,
}

/** **A válvula que permite manter o rail em seis.**
 *
 *  Uma busca só sobre atividade, local, contrato, medição, ficha, defeito e
 *  ocorrência — o servidor varre as sete e devolve por espécie, sem acento nas
 *  duas pontas. Quem usa o módulo todo dia para de navegar por menu na primeira
 *  semana; sem isto, cada assunto novo do backend volta a pressionar por uma
 *  porta no menu, que foi como o depósito nasceu da primeira vez.
 *
 *  Obras e postos continuam sendo filtrados aqui: são a navegação da própria
 *  casca, já estão em memória, e uma ida ao servidor para achar "Plano" seria
 *  latência sem ganho. */
export function PaletaDeComando() {
  const { paletaAberta, fecharPaleta, obraId, selecionar } = usePdca()
  const [termo, setTermo] = useState('')
  const [cursor, setCursor] = useState(0)
  const [soNestaObra, setSoNestaObra] = useState(true)
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const entrada = useRef<HTMLInputElement>(null)

  const { data: obras = [] } = useObras()
  const busca = useBusca(termo, soNestaObra ? obraId : undefined)

  useEffect(() => {
    if (paletaAberta) { setTermo(''); setCursor(0); entrada.current?.focus() }
  }, [paletaAberta])

  const resultados = useMemo<Resultado[]>(() => {
    const t = termo.trim()
    const saida: Resultado[] = []

    for (const p of POSTOS) {
      if (!hasPermission(p.permissao)) continue
      if (t && !contemSemAcento(p.rotulo, t)) continue
      saida.push({
        grupo: 'Postos desta obra', tipo: 'posto', chave: `posto:${p.codigo}`,
        id: p.codigo, titulo: p.rotulo, detalhe: `Cadência: ${p.cadencia}`,
      })
    }

    for (const o of obras) {
      if (o.obra_id === obraId) continue
      if (t && !contemSemAcento(o.nome_obra, t)) continue
      saida.push({
        grupo: 'Trocar de obra', tipo: 'obra', chave: `obra:${o.obra_id}`,
        id: o.obra_id, titulo: o.nome_obra, detalhe: 'Abre no mesmo posto',
      })
    }

    for (const especie of busca.data?.especies ?? []) {
      for (const r of especie.resultados) {
        saida.push({
          grupo: especie.rotulo,
          tipo: especie.codigo,
          chave: r.chave,
          id: r.id,
          titulo: r.titulo,
          detalhe: [r.subtitulo, soNestaObra ? '' : r.obra_nome]
            .filter(Boolean).join(' · '),
          obra: r.obra,
        })
      }
    }

    return saida
  }, [termo, obras, obraId, hasPermission, busca.data, soNestaObra])

  useEffect(() => { setCursor(0) }, [termo, soNestaObra])

  if (!paletaAberta) return null

  function executar(r: Resultado) {
    fecharPaleta()
    if (r.tipo === 'posto') {
      navigate(`/app/pdca/o/${obraId}/${r.id}`)
      return
    }
    if (r.tipo === 'obra') {
      navigate(`/app/pdca/o/${r.id}/hoje`)
      return
    }
    const destinoObra = ('obra' in r && r.obra) || obraId
    const posto = POSTO_DA_ESPECIE[r.tipo] ?? 'hoje'
    if (r.tipo === 'atividade') selecionar({ tipo: 'atividade', id: r.id })
    if (r.tipo === 'local') selecionar({ tipo: 'local', id: r.id })
    navigate(`/app/pdca/o/${destinoObra}/${posto}`)
  }

  function aoTeclar(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { fecharPaleta(); return }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, resultados.length - 1))
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    }
    if (e.key === 'Enter' && resultados[cursor]) {
      e.preventDefault()
      executar(resultados[cursor])
    }
  }

  const curto = termo.trim().length > 0 && termo.trim().length < 2
  let grupoAnterior = ''

  return (
    <div
      onMouseDown={fecharPaleta}
      style={{
        position: 'fixed', inset: 0, zIndex: 120,
        background: 'rgba(6,12,22,0.5)', backdropFilter: 'blur(2px)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: '12vh',
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Busca e comandos"
        style={{
          width: 'min(660px, 92vw)', background: 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-lg)', overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '13px 16px', borderBottom: '1px solid var(--line-2)',
          }}
        >
          <Search size={16} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
          <input
            ref={entrada}
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            onKeyDown={aoTeclar}
            placeholder="Buscar serviço, local, contrato, medição, ficha, defeito ou ocorrência"
            style={{
              border: 'none', outline: 'none', background: 'transparent',
              color: 'var(--ink)', fontSize: 14.5, width: '100%',
            }}
          />
          {busca.isFetching && <Spinner size={14} />}
          <button
            type="button"
            onClick={() => setSoNestaObra((v) => !v)}
            title={
              soNestaObra
                ? 'Procurando só nesta obra. Clique para procurar em todas.'
                : 'Procurando em todas as obras. Clique para limitar a esta.'
            }
            style={{
              flexShrink: 0, fontSize: 11, fontWeight: 650, cursor: 'pointer',
              borderRadius: 999, padding: '3px 9px', border: '1px solid',
              borderColor: soNestaObra ? 'var(--accent)' : 'var(--line)',
              background: soNestaObra ? 'var(--accent-soft)' : 'transparent',
              color: soNestaObra ? 'var(--accent-ink)' : 'var(--ink-3)',
            }}
          >
            {soNestaObra ? 'nesta obra' : 'todas as obras'}
          </button>
          <kbd
            style={{
              fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-3)',
              border: '1px solid var(--line)', borderRadius: 4, padding: '2px 5px',
            }}
          >
            esc
          </kbd>
        </div>

        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {/* **O aviso de uma letra aparece MESMO havendo resultados.**
              Postos e obras são filtrados aqui e casam com quase qualquer
              letra: sem esta linha, quem digita `a` procurando "alvenaria" vê
              uma lista cheia de postos, não encontra a alvenaria e conclui que
              ela não existe — que é a pior forma de falha, porque não parece
              falha. O servidor só varre a partir de duas letras, e a tela diz
              isso em vez de deixar a pessoa adivinhar. */}
          {curto && (
            <div
              style={{
                padding: '9px 16px', fontSize: 12, color: 'var(--ink-2)',
                background: 'var(--inset)', borderBottom: '1px solid var(--line-2)',
              }}
            >
              Escreva pelo menos 2 letras para procurar serviços, locais,
              contratos, medições, fichas, defeitos e ocorrências.
            </div>
          )}

          {resultados.length === 0 && !curto && (
            <div style={{ padding: '18px 16px', fontSize: 13, color: 'var(--ink-3)' }}>
              {busca.isFetching ? 'Procurando…' : 'Nada com esse nome.'}
            </div>
          )}

          {resultados.map((r, i) => {
            const Icone = ICONE[r.tipo] ?? ListTree
            const cabecalho = r.grupo !== grupoAnterior
            grupoAnterior = r.grupo
            return (
              <div key={r.chave}>
                {cabecalho && (
                  <div
                    style={{
                      padding: '7px 16px 3px', fontSize: 10,
                      letterSpacing: '0.07em', textTransform: 'uppercase',
                      color: 'var(--ink-3)', fontWeight: 700,
                    }}
                  >
                    {r.grupo}
                  </div>
                )}
                <button
                  type="button"
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => executar(r)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 11, width: '100%',
                    background: i === cursor ? 'var(--surface-2)' : 'transparent',
                    border: 'none', textAlign: 'left', cursor: 'pointer',
                    padding: '9px 16px',
                  }}
                >
                  <span style={{ color: 'var(--ink-3)', display: 'flex', flexShrink: 0 }}>
                    <Icone size={15} />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      style={{
                        display: 'block', fontSize: 13.5, color: 'var(--ink)',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {r.titulo}
                    </span>
                    {r.detalhe && (
                      <span
                        style={{
                          display: 'block', fontSize: 11, color: 'var(--ink-3)',
                          overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {r.detalhe}
                      </span>
                    )}
                  </span>
                  {i === cursor && (
                    <CornerDownLeft size={13} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
                  )}
                </button>
              </div>
            )
          })}

          {(busca.data?.sem_permissao?.length ?? 0) > 0 && (
            <div style={{ padding: '8px 12px 12px' }}>
              <SemPermissaoAviso itens={busca.data!.sem_permissao} />
            </div>
          )}
        </div>

        <div
          style={{
            padding: '8px 16px', borderTop: '1px solid var(--line-2)',
            fontSize: 11, color: 'var(--ink-3)', background: 'var(--surface-2)',
            display: 'flex', gap: 14,
          }}
        >
          <span>↑↓ para escolher · Enter para abrir</span>
          {busca.data && !busca.data.curta && (
            <span style={{ marginLeft: 'auto' }}>
              {busca.data.total} de {busca.data.especies_varridas} tipos de registro
              {busca.data.especies.some((e) => e.truncada) &&
                ` · mostrando ${busca.data.teto_por_especie} por tipo`}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
