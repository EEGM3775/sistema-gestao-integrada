import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Plus, Search, Trash2 } from 'lucide-react'
import { BotaoExportar, Btn, Card, Loading, Pill, WizardImportacao } from '@/components/malha'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { contemSemAcento } from '@/utils/texto'
import { useEditarLocais, useLocais } from '../hooks'
import { mensagemDe } from '../montagem'
import type { LocalObra, NivelLocal } from '../types'

interface NoDaArvore {
  local: LocalObra
  nivel: number
  filhos: NoDaArvore[]
}

const NIVEIS: { valor: NivelLocal; rotulo: string }[] = [
  { valor: 'bloco', rotulo: 'Bloco / Torre' },
  { valor: 'pavimento', rotulo: 'Pavimento' },
  { valor: 'unidade', rotulo: 'Unidade' },
  { valor: 'ambiente', rotulo: 'Ambiente' },
  { valor: 'frente', rotulo: 'Frente de serviço' },
  { valor: 'trecho', rotulo: 'Trecho' },
  { valor: 'estaca', rotulo: 'Estaca' },
  { valor: 'area', rotulo: 'Área' },
]

/** O degrau que costuma vir abaixo de cada um — a sugestão do "+ dentro". */
const ABAIXO: Partial<Record<NivelLocal, NivelLocal>> = {
  bloco: 'pavimento', pavimento: 'unidade', unidade: 'ambiente', trecho: 'estaca', frente: 'trecho',
}

const ESTILO_CAMPO = {
  fontSize: 12, padding: '4px 6px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', minWidth: 0,
} as const

/** A hierarquia construtiva — o eixo Y da linha de balanço e o endereço de
 *  tudo o que acontece no campo. **Cadastra-se aqui mesmo**: o seletor de
 *  local do Inspetor mandava para cá, e a lista era só leitura (o beco da
 *  convenção §12). Um local por vez, ou em série ("Trecho 1…12"). */
export function PainelLocais({ obraId }: { obraId: number }) {
  const { data, isLoading, isError } = useLocais(obraId)
  const { hasPermission } = useAuth()
  const podeCriar = hasPermission('pdca.local.edit')
  const podeExcluir = hasPermission('pdca.local.delete')
  const editar = useEditarLocais(obraId)
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')
  const [fechados, setFechados] = useState<Set<number>>(new Set())
  const [novoEm, setNovoEm] = useState<{ pai: LocalObra | null } | null>(null)
  const [erro, setErro] = useState<string | null>(null)

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

  function alternar(id: number) {
    setFechados((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  async function excluir(l: LocalObra) {
    const filhos = l.filhos_count ? ` e os ${l.filhos_count} locais dentro dele` : ''
    if (!window.confirm(`Excluir "${l.nome}"${filhos}? As atividades ligadas a ele ficam sem local.`)) return
    setErro(null)
    try { await editar.remover.mutateAsync(l.local_id) } catch (e) { setErro(mensagemDe(e)) }
  }

  const lista = data ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        <strong>Locais são os lugares da obra</strong> onde o serviço acontece — numa obra vertical, torre,
        pavimento, apartamento; numa obra linear (rede, drenagem, pavimentação), trecho, estaca, frente.
        Ligar a atividade a um local é <strong>opcional</strong>: é o que desenha a linha de balanço (vista
        Ritmo, "que trecho está em qual serviço") e permite apontar avanço e registrar restrição por frente.
      </div>

      {/* Planilha: a árvore entra nível a nível (o pai pelo caminho de códigos, "T1/P02"). */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <BotaoExportar recurso="pdca.local" recorte={{ obra: obraId }} />
        <WizardImportacao recurso="pdca.local" contexto={{ obra: obraId }}
          onConcluida={() => qc.invalidateQueries({ queryKey: ['pdca'] })} />
      </div>

      {erro && <div style={{ fontSize: 12, color: 'var(--danger-ink)' }}>{erro}</div>}
      {isError && <div style={{ fontSize: 12, color: 'var(--danger-ink)' }}>Não foi possível carregar os locais. Tente de novo.</div>}

      {podeCriar && novoEm?.pai == null && novoEm && (
        <FormularioDeLocal
          pai={null}
          irmaos={lista.filter((l) => l.pai == null)}
          ocupado={editar.criar.isPending}
          aoCriar={async (corpos) => {
            setErro(null)
            try { await editar.criar.mutateAsync(corpos); setNovoEm(null) } catch (e) { setErro(mensagemDe(e)) }
          }}
          aoCancelar={() => setNovoEm(null)}
        />
      )}

      <Card pad={false}>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '9px 14px', borderBottom: '1px solid var(--line-2)',
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
            {lista.length} locais
          </span>
          {podeCriar && (
            <Btn tam="sm" onClick={() => setNovoEm({ pai: null })}><Plus size={13} /> Local</Btn>
          )}
        </div>

        <div style={{ maxHeight: 520, overflowY: 'auto' }}>
          {lista.length === 0 && (
            <div style={{ padding: '16px 14px', fontSize: 12.5, color: 'var(--ink-3)' }}>
              Esta obra ainda não tem locais.{podeCriar ? ' Comece pelo topo — "+ Local" — e acrescente os de dentro em cada linha.' : ''}
            </div>
          )}
          {lista.length > 0 && visiveis.length === 0 && (
            <div style={{ padding: '16px 14px', fontSize: 12.5, color: 'var(--ink-3)' }}>
              Nenhum local com esse nome.
            </div>
          )}
          {visiveis.map((no) => {
            const temFilhos = no.filhos.length > 0
            const aberto = !fechados.has(no.local.local_id)
            return (
              <div key={no.local.local_id}>
                <div
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
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)', flexShrink: 0, minWidth: 68 }}>
                    {no.local.codigo}
                  </span>
                  <span style={{ flex: 1, fontSize: 13, color: 'var(--ink)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {no.local.nome}
                  </span>
                  <Pill kind="slate">{no.local.nivel_rotulo}</Pill>
                  {podeCriar && (
                    <button type="button" title="Acrescentar dentro deste" aria-label={`Acrescentar dentro de ${no.local.nome}`} onClick={() => setNovoEm({ pai: no.local })} style={BOTAO_ICONE}>
                      <Plus size={13} />
                    </button>
                  )}
                  {podeExcluir && (
                    <button type="button" title="Excluir" aria-label={`Excluir ${no.local.nome}`} onClick={() => void excluir(no.local)} style={BOTAO_ICONE}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
                {podeCriar && novoEm?.pai?.local_id === no.local.local_id && (
                  <div style={{ padding: '8px 14px', paddingLeft: 30 + no.nivel * 16, borderBottom: '1px solid var(--line-2)', background: 'var(--inset)' }}>
                    <FormularioDeLocal
                      pai={no.local}
                      irmaos={lista.filter((l) => l.pai === no.local.local_id)}
                      ocupado={editar.criar.isPending}
                      aoCriar={async (corpos) => {
                        setErro(null)
                        try {
                          await editar.criar.mutateAsync(corpos)
                          setNovoEm(null)
                          setFechados((f) => { const n = new Set(f); n.delete(no.local.local_id); return n })
                        } catch (e) { setErro(mensagemDe(e)) }
                      }}
                      aoCancelar={() => setNovoEm(null)}
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}

/** Um local, ou uma série: "Trecho" × 12 vira Trecho 1…12, com código
 *  seguido (o do pai como prefixo). */
function FormularioDeLocal(
  { pai, irmaos, ocupado, aoCriar, aoCancelar }: {
    pai: LocalObra | null
    irmaos: LocalObra[]
    ocupado: boolean
    aoCriar: (corpos: Partial<LocalObra>[]) => unknown
    aoCancelar: () => void
  },
) {
  const [nivel, setNivel] = useState<NivelLocal>((pai && ABAIXO[pai.nivel]) || 'trecho')
  const [nome, setNome] = useState('')
  const [quantos, setQuantos] = useState('1')
  const n = Math.max(1, Math.min(200, Math.round(Number(quantos)) || 1))

  function montarCorpos(): Partial<LocalObra>[] {
    // O código continua do maior já usado entre os irmãos (único entre eles):
    // contar os irmãos repetiria o código de quem foi excluído no meio.
    const usados = irmaos.map((l) => Number(l.codigo.split('.').pop())).filter((x) => Number.isFinite(x))
    const base = Math.max(0, ...usados)
    const prefixo = pai ? `${pai.codigo}.` : ''
    return Array.from({ length: n }, (_, i) => ({
      pai: pai?.local_id ?? null,
      nivel,
      nome: n > 1 ? `${nome.trim()} ${i + 1}` : nome.trim(),
      codigo: `${prefixo}${base + i + 1}`,
      ordem: irmaos.length + i,
    }))
  }

  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{pai ? `Dentro de ${pai.nome}:` : 'Novo local no topo:'}</span>
      <select value={nivel} onChange={(e) => setNivel(e.target.value as NivelLocal)} aria-label="Tipo de local" style={ESTILO_CAMPO}>
        {NIVEIS.map((x) => <option key={x.valor} value={x.valor}>{x.rotulo}</option>)}
      </select>
      <input
        autoFocus
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && nome.trim()) void aoCriar(montarCorpos())
          if (e.key === 'Escape') aoCancelar()
        }}
        placeholder={n > 1 ? 'Nome (vira "Nome 1…N")' : 'Nome — ex.: Trecho Rua A'}
        aria-label="Nome do local"
        style={{ ...ESTILO_CAMPO, flex: 1, minWidth: 160 }}
      />
      <label style={{ fontSize: 12, color: 'var(--ink-3)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        ×
        <input value={quantos} onChange={(e) => setQuantos(e.target.value)} inputMode="numeric" aria-label="Quantos" title="Quantos criar em série" style={{ ...ESTILO_CAMPO, width: 44, textAlign: 'right' }} />
      </label>
      <Btn tam="sm" variant="primary" disabled={ocupado || !nome.trim()} onClick={() => aoCriar(montarCorpos())}>
        {ocupado ? 'Criando…' : n > 1 ? `Criar ${n}` : 'Criar'}
      </Btn>
      <Btn tam="sm" onClick={aoCancelar}>Cancelar</Btn>
    </div>
  )
}

const BOTAO_ICONE = {
  background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)',
  display: 'flex', padding: 2, flexShrink: 0,
} as const

function montar(locais: LocalObra[]): NoDaArvore[] {
  const porPai = new Map<number | null, LocalObra[]>()
  for (const l of locais) {
    const chave = l.pai ?? null
    const grupo = porPai.get(chave)
    if (grupo) grupo.push(l)
    else porPai.set(chave, [l])
  }
  for (const grupo of porPai.values()) {
    grupo.sort((a, b) => (a.ordem - b.ordem) || a.codigo.localeCompare(b.codigo, 'pt-BR', { numeric: true }))
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
