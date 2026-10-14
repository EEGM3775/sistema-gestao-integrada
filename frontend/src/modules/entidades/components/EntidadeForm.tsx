import { useState, type CSSProperties, type ReactNode } from 'react'
import { Btn, Modal } from '@/components/malha'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { PAPEIS, useExcluirEntidade, useSalvarEntidade, type Entidade, type EntidadeEntrada } from '../api'

const campo: CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line)',
  background: 'var(--surface)', color: 'var(--ink)', fontSize: 13.5,
}

const VAZIA: EntidadeEntrada = {
  tipo_pessoa: 'PJ', documento: '', nome: '', nome_fantasia: '', papel: 'spe', externa: false, matriz: null,
  inscricao_estadual: '', inscricao_municipal: '', endereco: '', cidade: '', estado: '', ativa: true,
}

export default function EntidadeForm({ entidade, grupo, onClose, onSalvo }: {
  entidade: Entidade | null
  grupo: Entidade[]
  onClose: () => void
  onSalvo: (e: Entidade) => void
}) {
  const [form, setForm] = useState<EntidadeEntrada>(entidade ? { ...entidade } : VAZIA)
  const [erros, setErros] = useState<FieldErrors>({})
  const salvar = useSalvarEntidade()
  const excluir = useExcluirEntidade()
  const set = <K extends keyof EntidadeEntrada>(k: K, v: EntidadeEntrada[K]) => {
    setErros(prev => ({ ...prev, [k]: '' }))
    setForm(prev => ({ ...prev, [k]: v }))
  }
  const papel = PAPEIS.find(p => p.valor === form.papel)
  const ehMatrizOuFilial = form.papel === 'matriz' || form.papel === 'filial'

  async function enviar() {
    const doc = form.documento ?? ''
    const errDoc = doc ? validateCPFCNPJ(doc) : null
    if (errDoc) { setErros({ documento: errDoc }); return }
    try {
      const salva = await salvar.mutateAsync({
        id: entidade?.entidade_id,
        dados: { ...form, matriz: form.papel === 'filial' ? form.matriz : null },
      })
      onSalvo(salva)
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  async function apagar() {
    if (!entidade) return
    try {
      await excluir.mutateAsync(entidade.entidade_id)
      onClose()
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  return (
    <Modal
      titulo={entidade ? `Editar ${entidade.nome}` : 'Nova entidade'}
      onClose={onClose}
      largura={640}
      rodape={
        <>
          {entidade && <Btn variant="perigo" onClick={() => void apagar()} disabled={excluir.isPending}>Excluir</Btn>}
          <span style={{ flex: 1 }} />
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" onClick={() => void enviar()} disabled={salvar.isPending || !form.nome}>
            {salvar.isPending ? 'Salvando…' : 'Salvar'}
          </Btn>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormErrorBanner errors={erros} />

        <Rotulo titulo="Está no grupo?">
          <div className="flex gap-2 flex-wrap">
            <Escolha ativa={!form.externa} onClick={() => set('externa', false)}>
              Do grupo — tem financeiro aqui
            </Escolha>
            <Escolha ativa={!!form.externa} onClick={() => { set('externa', true); if (ehMatrizOuFilial) set('papel', 'outra') }}>
              Externa — dono de empreendimento que executamos, sócio de fora
            </Escolha>
          </div>
          <FieldError msg={erros.externa} />
        </Rotulo>

        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <Rotulo titulo="Papel">
            <select value={form.papel} onChange={e => set('papel', e.target.value as Entidade['papel'])} style={campo}>
              {PAPEIS.filter(p => !(form.externa && (p.valor === 'matriz' || p.valor === 'filial'))).map(p => (
                <option key={p.valor} value={p.valor}>{p.rotulo}</option>
              ))}
            </select>
            {papel && <span className="text-xs" style={{ color: 'var(--ink-3)' }}>{papel.ajuda}</span>}
          </Rotulo>
          <Rotulo titulo="Tipo de pessoa">
            <select value={form.tipo_pessoa} onChange={e => set('tipo_pessoa', e.target.value as 'PJ' | 'PF')} style={campo}>
              <option value="PJ">Pessoa jurídica (CNPJ)</option>
              <option value="PF">Pessoa física (CPF)</option>
            </select>
          </Rotulo>
        </div>

        {form.papel === 'filial' && (
          <Rotulo titulo="Matriz">
            <select value={form.matriz ?? ''} onChange={e => set('matriz', e.target.value ? Number(e.target.value) : null)} style={campo}>
              <option value="">Escolha a matriz…</option>
              {grupo.filter(g => g.entidade_id !== entidade?.entidade_id).map(g => (
                <option key={g.entidade_id} value={g.entidade_id}>{g.nome}</option>
              ))}
            </select>
            <FieldError msg={erros.matriz} />
          </Rotulo>
        )}

        <div className="grid gap-4" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <Rotulo titulo={form.tipo_pessoa === 'PF' ? 'Nome civil' : 'Razão social'}>
            <input value={form.nome} onChange={e => set('nome', e.target.value)} style={campo} />
            <FieldError msg={erros.nome} />
          </Rotulo>
          <Rotulo titulo={form.tipo_pessoa === 'PF' ? 'CPF' : 'CNPJ'}>
            <input
              value={maskCPFCNPJ(form.documento ?? '')}
              onChange={e => set('documento', e.target.value.replace(/\D/g, ''))}
              onBlur={() => {
                const err = form.documento ? validateCPFCNPJ(form.documento) : null
                if (err) setErros(prev => ({ ...prev, documento: err }))
              }}
              inputMode="numeric" style={campo}
            />
            <span className="text-xs" style={{ color: 'var(--ink-3)' }}>Pode ficar para depois; sem ele, a entidade não emite nota nem boleto.</span>
            <FieldError msg={erros.documento} />
          </Rotulo>
        </div>

        <Rotulo titulo="Nome fantasia">
          <input value={form.nome_fantasia} onChange={e => set('nome_fantasia', e.target.value)} style={campo} />
        </Rotulo>

        {!form.externa && (
          <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <Rotulo titulo="Inscrição estadual">
              <input value={form.inscricao_estadual} onChange={e => set('inscricao_estadual', e.target.value)} style={campo} />
            </Rotulo>
            <Rotulo titulo="Inscrição municipal">
              <input value={form.inscricao_municipal} onChange={e => set('inscricao_municipal', e.target.value)} style={campo} />
            </Rotulo>
          </div>
        )}

        <div className="grid gap-4" style={{ gridTemplateColumns: '2fr 1fr 80px' }}>
          <Rotulo titulo="Endereço">
            <input value={form.endereco} onChange={e => set('endereco', e.target.value)} style={campo} />
          </Rotulo>
          <Rotulo titulo="Cidade">
            <input value={form.cidade} onChange={e => set('cidade', e.target.value)} style={campo} />
          </Rotulo>
          <Rotulo titulo="UF">
            <input value={form.estado} maxLength={2} onChange={e => set('estado', e.target.value.toUpperCase())} style={campo} />
          </Rotulo>
        </div>

        {entidade && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!form.ativa} onChange={e => set('ativa', e.target.checked)} />
            Ativa (a inativa sai da barra do ERP)
          </label>
        )}
      </div>
    </Modal>
  )
}

function Rotulo({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{titulo}</span>
      {children}
    </label>
  )
}

function Escolha({ ativa, onClick, children }: { ativa: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={ativa}
      style={{
        padding: '8px 12px', borderRadius: 8, fontSize: 13, cursor: 'pointer', textAlign: 'left',
        border: `1px solid ${ativa ? 'var(--accent)' : 'var(--line)'}`,
        background: ativa ? 'var(--accent-soft)' : 'var(--surface)', color: ativa ? 'var(--accent-ink)' : 'var(--ink-2)',
      }}>
      {children}
    </button>
  )
}
