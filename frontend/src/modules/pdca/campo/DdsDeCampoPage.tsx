import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Check, Plus, X } from 'lucide-react'
import { Loading } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { maxTodayISO } from '@/utils/dates'
import { useAbrirDds, useDds, useEncerrarDds, useRegistrarPresenca } from '../hooks'
import { useCampo } from './contexto'
import {
  Aviso, BotaoGrande, Cartao, EscolhaDeObra, Rotulado, Titulo, VoltarParaFrente,
} from './pecas'
import { campoGrande } from '../estilos'
import { primeiraFrase } from '../formato'

/** **O diálogo antes do turno, no campo.** Duas telas: o tema (e só ele é
 *  obrigatório, porque é o que faz o registro servir de prova) e a roda — um
 *  nome de cada vez, com o dedo, e o encerramento que fecha a lista e escreve
 *  no diário da obra. */
export default function DdsDeCampoPage() {
  const { ddsId } = useParams()
  return ddsId ? <Roda ddsId={Number(ddsId)} /> : <NovoDialogo />
}

function NovoDialogo() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const { como, nomeDoServidor } = useCampo()
  const abrir = useAbrirDds()
  const [obra, setObra] = useState<number | null>(Number(params.get('obra')) || null)
  const [tema, setTema] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  if (!hasPermission('pdca.dds.registrar')) {
    return (
      <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <VoltarParaFrente />
        <Aviso tom="accent">
          Registrar o diálogo de segurança exige permissão. Quem libera é o administrador da empresa.
        </Aviso>
      </div>
    )
  }

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VoltarParaFrente />
      <Titulo sub="Antes do turno. A lista de presença é o que prova.">Diálogo de segurança</Titulo>
      <Cartao>
        <Rotulado rotulo="Sobre o que se vai falar">
          <input value={tema} onChange={(e) => setTema(e.target.value)} style={campoGrande} autoFocus
            placeholder="Ex.: uso do cinto na periferia da laje" />
        </Rotulado>
        <EscolhaDeObra valor={obra} aoMudar={setObra} />
        <Aviso tom="danger">{erro}</Aviso>
        <BotaoGrande
          disabled={!obra || !tema.trim() || abrir.isPending}
          onClick={async () => {
            if (!obra) return
            setErro(null)
            try {
              const novo = await abrir.mutateAsync({
                obra, data: maxTodayISO(), tema: tema.trim(),
                responsavel_nome: como || nomeDoServidor,
              })
              navigate(`/campo/dds/${novo.dds_id}`, { replace: true })
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          Começar a roda
        </BotaoGrande>
      </Cartao>
    </div>
  )
}

function Roda({ ddsId }: { ddsId: number }) {
  const navigate = useNavigate()
  const dds = useDds(ddsId)
  const presenca = useRegistrarPresenca()
  const encerrar = useEncerrarDds()
  const [nome, setNome] = useState('')
  const [novos, setNovos] = useState<string[]>([])
  const [erro, setErro] = useState<string | null>(null)
  const [fim, setFim] = useState<{ presentes: number; noDiario: boolean } | null>(null)

  if (dds.isLoading) return <Loading o="o diálogo" />
  if (dds.isError || !dds.data) {
    return (
      <div style={{ padding: 14 }}>
        <VoltarParaFrente />
        <Aviso tom="danger">Este diálogo não foi encontrado.</Aviso>
      </div>
    )
  }

  const d = dds.data
  const aberto = d.status === 'rascunho'

  function acrescentar() {
    const limpo = nome.trim()
    if (!limpo) return
    setNovos((n) => [...n, limpo])
    setNome('')
  }

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VoltarParaFrente />
      <Titulo sub={`${d.obra_nome} · ${d.presentes + novos.length} na roda`}>{d.tema}</Titulo>

      {fim && (
        <Aviso tom="good">
          Diálogo encerrado com {fim.presentes} presentes.
          {fim.noDiario ? ' Já está no diário da obra.' : ' O diário da obra não estava disponível para registrar.'}
        </Aviso>
      )}

      <Cartao>
        {[...d.participantes.map((p) => p.funcionario_nome || p.nome), ...novos].map((n, i) => (
          <div key={`${n}-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 16, color: 'var(--ink)', minHeight: 32 }}>
            <Check size={18} style={{ color: i < d.participantes.length ? 'var(--good-ink)' : 'var(--ink-3)' }} />
            <span style={{ flex: 1 }}>{n}</span>
            {i >= d.participantes.length && (
              <button
                type="button" aria-label={`Tirar ${n}`}
                onClick={() => setNovos((lista) => lista.filter((_, j) => j !== i - d.participantes.length))}
                style={{ minWidth: 44, minHeight: 44, background: 'none', border: 'none', color: 'var(--ink-3)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            )}
          </div>
        ))}

        {aberto && (
          <>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); acrescentar() } }}
                placeholder="Nome de quem está na roda"
                aria-label="Nome de quem está na roda"
                style={campoGrande}
              />
              <button
                type="button" onClick={acrescentar} aria-label="Acrescentar à roda"
                style={{
                  minWidth: 56, minHeight: 48, borderRadius: 10, border: '1px solid var(--line)',
                  background: 'var(--surface-2)', color: 'var(--ink)', cursor: 'pointer',
                  display: 'grid', placeItems: 'center',
                }}
              >
                <Plus size={22} />
              </button>
            </div>

            <Aviso tom="danger">{erro}</Aviso>

            {novos.length > 0 && (
              <BotaoGrande
                tom="neutro"
                disabled={presenca.isPending}
                onClick={async () => {
                  setErro(null)
                  try {
                    await presenca.mutateAsync({ id: ddsId, participantes: novos.map((n) => ({ nome: n, presente: true })) })
                    setNovos([])
                  } catch (e) {
                    setErro(primeiraFrase(e))
                  }
                }}
              >
                {presenca.isPending ? 'Gravando…' : `Gravar ${novos.length === 1 ? 'o nome' : `os ${novos.length} nomes`}`}
              </BotaoGrande>
            )}

            <BotaoGrande
              disabled={encerrar.isPending || presenca.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  if (novos.length) {
                    await presenca.mutateAsync({ id: ddsId, participantes: novos.map((n) => ({ nome: n, presente: true })) })
                    setNovos([])
                  }
                  const r = await encerrar.mutateAsync({ id: ddsId, publicar: true })
                  setFim({ presentes: r.presentes, noDiario: r.publicado_no_diario })
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              {encerrar.isPending ? 'Encerrando…' : 'Encerrar o diálogo'}
            </BotaoGrande>
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
              Encerrar grava os nomes que faltam, fecha a lista e escreve no diário da obra.
            </span>
          </>
        )}
      </Cartao>

      {!aberto && (
        <BotaoGrande tom="neutro" onClick={() => navigate('/campo')}>Voltar para a minha frente</BotaoGrande>
      )}
    </div>
  )
}
