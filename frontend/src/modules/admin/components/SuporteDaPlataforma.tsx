import React, { useCallback, useEffect, useState } from 'react'
import { LifeBuoy, Lock, Unlock } from 'lucide-react'
import iamAdminClient from '@/api/iamAdminClient'
import { FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Consentimento {
  id: number
  concedido_por: string
  motivo: string
  ate: string
  vigente: boolean
}

interface EstadoSuporte {
  vigente: Consentimento | null
  dias: { padrao: number; maximo: number }
  empresas?: { id: string; nome: string; ate: string }[]
}

const quando = (iso: string) =>
  new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

export const SuporteDaPlataforma: React.FC<{ supervisor: boolean }> = ({ supervisor }) => {
  const [estado, setEstado] = useState<EstadoSuporte | null>(null)
  const [dias, setDias] = useState(1)
  const [motivo, setMotivo] = useState('')
  const [erros, setErros] = useState<FieldErrors>({})
  const [salvando, setSalvando] = useState(false)

  const carregar = useCallback(async () => {
    const r = await iamAdminClient.get('/suporte/')
    setEstado(r.data as EstadoSuporte)
    setDias((r.data as EstadoSuporte).dias.padrao)
  }, [])

  useEffect(() => {
    void carregar().catch(() => setEstado(null))
  }, [carregar])

  const liberar = async () => {
    setSalvando(true)
    setErros({})
    try {
      await iamAdminClient.post('/suporte/', { dias, motivo })
      setMotivo('')
      await carregar()
    } catch (err) {
      setErros(parseApiErrors(err))
    } finally {
      setSalvando(false)
    }
  }

  const encerrar = async () => {
    setSalvando(true)
    setErros({})
    try {
      await iamAdminClient.delete('/suporte/')
      await carregar()
    } catch (err) {
      setErros(parseApiErrors(err))
    } finally {
      setSalvando(false)
    }
  }

  if (!estado) return null

  if (supervisor) {
    const empresas = estado.empresas ?? []
    return (
      <div className="rounded-xl p-4 mb-5" style={{ border: '1px solid #e2e8f0', background: '#FFFFFF' }}>
        <div className="flex items-center gap-2 mb-1">
          <LifeBuoy size={16} style={{ color: 'var(--color-brand)' }} />
          <h2 className="text-sm font-bold" style={{ color: 'var(--color-brand)' }}>Empresas que liberaram o suporte</h2>
        </div>
        {empresas.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
            Nenhuma empresa liberou o acesso agora. A lista abaixo mostra só as pessoas da sua empresa.
          </p>
        ) : (
          <ul className="text-sm" style={{ color: 'var(--color-text)' }}>
            {empresas.map((e) => (
              <li key={e.id}>{e.nome} — até {quando(e.ate)}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  const vigente = estado.vigente
  return (
    <div className="rounded-xl p-4 mb-5" style={{ border: '1px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="flex items-center gap-2 mb-1">
        {vigente ? <Unlock size={16} style={{ color: '#b45309' }} /> : <Lock size={16} style={{ color: 'var(--color-brand)' }} />}
        <h2 className="text-sm font-bold" style={{ color: 'var(--color-brand)' }}>Acesso do suporte da plataforma</h2>
      </div>
      <FormErrorBanner errors={erros} />
      {vigente ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm flex-1" style={{ color: 'var(--color-text)' }}>
            O suporte pode ver e ajustar as pessoas, os papéis e os acessos desta empresa até{' '}
            <b>{quando(vigente.ate)}</b>, liberado por {vigente.concedido_por}
            {vigente.motivo ? ` (${vigente.motivo})` : ''}.
          </p>
          <button type="button" onClick={() => void encerrar()} disabled={salvando}
            className="px-3 py-2 rounded-xl text-sm font-semibold disabled:opacity-60"
            style={{ background: '#f1f5f9', color: 'var(--color-text)' }}>
            Encerrar agora
          </button>
        </div>
      ) : (
        <>
          <p className="text-sm mb-3" style={{ color: 'var(--color-text-muted)' }}>
            O suporte da plataforma não vê as pessoas nem os papéis desta empresa. Libere só quando
            abrir um chamado que precise disso — o acesso termina sozinho no prazo escolhido.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Por quantos dias
              <select value={dias} onChange={(e) => setDias(Number(e.target.value))}
                className="block mt-1 px-2 py-2 rounded-lg border text-sm" style={{ borderColor: '#cbd5e1' }}>
                {Array.from({ length: estado.dias.maximo }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>{n} {n === 1 ? 'dia' : 'dias'}</option>
                ))}
              </select>
            </label>
            <label className="text-xs flex-1 min-w-[12rem]" style={{ color: 'var(--color-text-muted)' }}>
              Motivo (opcional)
              <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={200}
                placeholder="Ex.: chamado 123 — acesso do Pedro"
                className="block w-full mt-1 px-2 py-2 rounded-lg border text-sm" style={{ borderColor: '#cbd5e1' }} />
            </label>
            <button type="button" onClick={() => void liberar()} disabled={salvando}
              className="px-3 py-2 rounded-xl text-sm font-semibold disabled:opacity-60"
              style={{ background: 'var(--color-brand)', color: '#FFFFFF' }}>
              Liberar acesso
            </button>
          </div>
        </>
      )}
    </div>
  )
}
