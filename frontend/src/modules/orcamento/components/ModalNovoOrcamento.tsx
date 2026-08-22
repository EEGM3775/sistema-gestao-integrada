import { useState } from 'react'
import { Aviso, Btn, Field, inp, Modal, mono, Select } from '../ui'
import { paraDecimal } from '../lib'
import type { ObraOpt, Orcamento } from '../types'

/** Criar a planilha do zero.
 *
 *  Mora em `components/` — e não dentro da página de orçar — porque quem cria
 *  orçamento agora é a **lista** (a obra e seus orçamentos), e a planilha só
 *  edita o que já existe. Duas cópias do formulário divergiriam no primeiro
 *  campo novo, e o campo esquecido seria descoberto na tela errada.
 */
export default function ModalNovoOrcamento({ obras, bases, existentes, obraFixa, salvando, onFechar, onCriar }: {
  obras: ObraOpt[]
  bases: { base_id: number; rotulo: string }[]
  existentes: Orcamento[]
  /** Aberto de dentro de uma obra, a obra já vem escolhida — o passo de
   *  navegação já respondeu essa pergunta, e repetir a pergunta é atrito. */
  obraFixa?: number
  salvando: boolean
  onFechar: () => void
  onCriar: (dados: Partial<Orcamento>) => Promise<void>
}) {
  const [form, setForm] = useState({
    obra: obraFixa ? String(obraFixa) : '',
    descricao: '',
    base_referencial: '',
    bdi_percentual: '22,5',
    encargos_sociais_percentual: '84,7',
  })
  const [erro, setErro] = useState('')
  // A obra pode já ter planilha: a nova nasce como a próxima versão (reorçamento),
  // e é melhor dizer isso antes do que o orçamentista descobrir no cabeçalho.
  const daObra = form.obra ? existentes.filter(o => o.obra === Number(form.obra)) : []
  const proximaVersao = daObra.reduce((maior, o) => Math.max(maior, o.versao), 0) + 1
  return (
    <Modal
      titulo="Novo orçamento"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={async () => {
            if (!form.obra || !form.descricao.trim()) { setErro('Obra e descrição são obrigatórias.'); return }
            setErro('')
            try {
              await onCriar({
                obra: Number(form.obra),
                descricao: form.descricao.trim(),
                base_referencial: form.base_referencial ? Number(form.base_referencial) : null,
                bdi_percentual: paraDecimal(form.bdi_percentual),
                encargos_sociais_percentual: paraDecimal(form.encargos_sociais_percentual),
              })
            } catch (e) {
              // Sem isto o 400 virava só uma promise rejeitada no console: o modal
              // ficava aberto, sem recado, e parecia que o botão não fez nada.
              const dados = (e as { response?: { data?: Record<string, unknown> } })?.response?.data
              const primeiro = dados && Object.values(dados)[0]
              const detalhe = Array.isArray(primeiro) ? String(primeiro[0]) : primeiro ? String(primeiro) : null
              setErro(detalhe ?? 'Não foi possível criar o orçamento.')
            }
          }}>Criar em rascunho</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Field
        label="Obra"
        dica={daObra.length ? `Esta obra já tem ${daObra.length} planilha(s) — esta nasce como v${proximaVersao}.` : undefined}
      >
        <Select
          value={form.obra}
          disabled={obraFixa != null}
          onChange={e => setForm(f => ({ ...f, obra: e.target.value }))}
          style={{ width: '100%', maxWidth: 'none' }}
        >
          <option value="">Selecione</option>
          {obras.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
        </Select>
      </Field>
      <Field label="Descrição"><input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} placeholder="Ex.: Orçamento executivo — Residencial Alfa" style={inp} /></Field>
      <Field label="Base de preço" dica="A data-base do orçamento é copiada da publicação e sobrevive a ela.">
        <Select value={form.base_referencial} onChange={e => setForm(f => ({ ...f, base_referencial: e.target.value }))} style={{ width: '100%', maxWidth: 'none' }}>
          <option value="">Sem base — preço digitado à mão</option>
          {bases.map(b => <option key={b.base_id} value={b.base_id}>{b.rotulo}</option>)}
        </Select>
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="BDI (%)"><input value={form.bdi_percentual} onChange={e => setForm(f => ({ ...f, bdi_percentual: e.target.value }))} style={{ ...inp, ...mono }} /></Field>
        <Field label="Encargos (%)"><input value={form.encargos_sociais_percentual} onChange={e => setForm(f => ({ ...f, encargos_sociais_percentual: e.target.value }))} style={{ ...inp, ...mono }} /></Field>
      </div>
    </Modal>
  )
}
