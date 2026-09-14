import { useMemo, useState } from 'react'
import { Library, Lock } from 'lucide-react'
import { Btn, Empty, Modal, Pill } from '@/components/malha'
import { dateFromBR, dateToBR, maskDate, validateISO_Vigencia } from '@/utils/dates'
import { FieldError, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { contemSemAcento } from '@/utils/texto'
import { useAplicarModelo, useCalendarios, useMarcarModelo, useModelos } from '../hooks'
import type { Cronograma } from '../types'

/**
 * A biblioteca de padrões da construtora (PDCA.1b).
 *
 * *Decisão do dono, 23/08/2026:* **"é só ele colocar como plano modelo e usar
 * esse plano para outras obras — para não ter que criar 300 planos em um
 * empreendimento grande"**. É o caso mais comum que existe: um empreendimento de
 * 300 unidades repete a mesma sequência construtiva 300 vezes, e montar isso à
 * mão é o que faz a construtora desistir do planejamento e voltar à planilha.
 */

export function ModalSalvarComoModelo({ cronograma, aoFechar }: {
  cronograma: Cronograma
  aoFechar: () => void
}) {
  const [nome, setNome] = useState(cronograma.nome_modelo || cronograma.descricao)
  const [erros, setErros] = useState<FieldErrors>({})
  const marcar = useMarcarModelo()

  const salvar = () => {
    setErros({})
    marcar.mutate(
      { id: cronograma.cronograma_id, nome: nome.trim() },
      { onSuccess: aoFechar, onError: e => setErros(parseApiErrors(e)) },
    )
  }

  return (
    <Modal titulo="Salvar como plano modelo" onClose={aoFechar}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 4 }}>
        <p style={corpo}>
          O plano entra na <strong>biblioteca da empresa</strong> e pode ser aplicado em qualquer obra
          que ainda não tenha cronograma. O que se repete é a estrutura — WBS, durações e a rede; as
          datas são recalculadas na obra nova, sobre o calendário dela.
        </p>
        <label style={campo}>
          <span>Nome do modelo</span>
          <input
            value={nome} autoFocus maxLength={120}
            onChange={e => { setNome(e.target.value); setErros({}) }}
            placeholder="Ex.: Torre residencial 20 pav. — estrutura convencional"
          />
          <FieldError msg={erros.nome || erros.detail} />
          <small style={ajuda}>
            Único na empresa: dois modelos com o mesmo nome é a forma mais rápida de alguém aplicar o
            padrão errado numa obra inteira.
          </small>
        </label>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="brand" disabled={!nome.trim() || marcar.isPending} onClick={salvar}>
            {marcar.isPending ? 'Salvando…' : 'Salvar na biblioteca'}
          </Btn>
        </div>
      </div>
    </Modal>
  )
}

/**
 * Aplicar um modelo a uma obra — a tela do gesto que o dono pediu.
 *
 * O que nasce é um **rascunho v1** da obra escolhida: não é modelo (senão
 * aplicar encheria a biblioteca de cópias) e não é vigente (quem assume o prazo
 * é quem publica, e isso não vem de graça com o padrão).
 */
export function ModalAplicarModelo({ obra, obraNome, aoFechar, aoAplicar }: {
  obra: number
  obraNome: string
  aoFechar: () => void
  aoAplicar: (cronograma: Cronograma) => void
}) {
  const modelos = useModelos()
  const calendarios = useCalendarios({ para_obra: obra })
  const aplicar = useAplicarModelo()

  const [busca, setBusca] = useState('')
  const [escolhido, setEscolhido] = useState<number | null>(null)
  const [form, setForm] = useState({ data_inicio: '', descricao: '', calendario: '' as number | '' })
  const [erros, setErros] = useState<FieldErrors>({})

  const lista = useMemo(
    () => (modelos.data ?? []).filter(m => contemSemAcento(m.nome_modelo, busca)),
    [modelos.data, busca],
  )
  //: O recorte "o da obra + os da empresa" é do **servidor** (`para_obra`, D118),
  //: e não mais um filtro no cliente sobre a lista inteira: era o mesmo padrão
  //: que o F2 da revisão manda tirar dos selects — carregar tudo para mostrar
  //: pouco.
  const opcoes = calendarios.data ?? []

  const enviar = () => {
    const iso = dateFromBR(form.data_inicio)
    if (!iso) { setErros({ data_inicio: 'Informe a data de início no formato DD/MM/AAAA.' }); return }
    const erro = validateISO_Vigencia(iso)
    if (erro) { setErros({ data_inicio: erro }); return }
    if (escolhido == null) { setErros({ modelo: 'Escolha o modelo a aplicar.' }); return }

    setErros({})
    aplicar.mutate(
      {
        id: escolhido,
        payload: {
          obra,
          data_inicio: iso,
          descricao: form.descricao.trim() || undefined,
          calendario: form.calendario === '' ? null : form.calendario,
        },
      },
      { onSuccess: aoAplicar, onError: e => setErros(parseApiErrors(e)) },
    )
  }

  return (
    <Modal titulo={'Aplicar um plano modelo em ' + obraNome} onClose={aoFechar} largura={620} alto>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0, padding: 4 }}>
        {modelos.isError ? (
          <Empty>
            <Lock size={14} /> Não foi possível ler a biblioteca de modelos desta empresa.
          </Empty>
        ) : (modelos.data?.length ?? 0) === 0 ? (
          <Empty>
            A empresa ainda não tem plano modelo. Abra um cronograma que já esteja do jeito certo e
            use <strong>Salvar como modelo</strong> — a partir daí ele se aplica a qualquer obra nova.
          </Empty>
        ) : (
          <>
            <input
              value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar modelo pelo nome"
              style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)' }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, overflow: 'auto', minHeight: 0, maxHeight: 260 }}>
              {lista.map(m => (
                <button
                  key={m.cronograma_id} type="button" onClick={() => setEscolhido(m.cronograma_id)}
                  style={{
                    textAlign: 'left', border: '1px solid ' + (escolhido === m.cronograma_id ? 'var(--brand)' : 'var(--line)'),
                    background: escolhido === m.cronograma_id ? 'var(--inset)' : 'var(--surface)',
                    borderRadius: 10, padding: '9px 12px', cursor: 'pointer', color: 'var(--ink)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Library size={13} style={{ color: 'var(--ink-3)' }} />
                    <strong style={{ fontSize: 13 }}>{m.nome_modelo}</strong>
                    <Pill kind="slate">{m.atividades_count} atividades</Pill>
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>
                    de {m.obra_nome} · {m.descricao}
                    {m.termino_calculado && ' · plano de ' + dateToBR(m.data_inicio) + ' a ' + dateToBR(m.termino_calculado)}
                  </div>
                </button>
              ))}
              {lista.length === 0 && <span style={ajuda}>Nenhum modelo com esse nome.</span>}
            </div>
            <FieldError msg={erros.modelo || erros.detail || erros.obra} />
          </>
        )}

        {(modelos.data?.length ?? 0) > 0 && (
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }}>
            <label style={campo}>
              <span>Início do plano na obra</span>
              <input
                value={form.data_inicio} placeholder="DD/MM/AAAA"
                onChange={e => setForm(f => ({ ...f, data_inicio: maskDate(e.target.value) }))}
              />
              <FieldError msg={erros.data_inicio} />
            </label>
            <label style={campo}>
              <span>Calendário de trabalho</span>
              <select
                value={form.calendario}
                onChange={e => setForm(f => ({ ...f, calendario: e.target.value === '' ? '' : Number(e.target.value) }))}
              >
                <option value="">Sem calendário</option>
                {opcoes.map(c => (
                  <option key={c.calendario_id} value={c.calendario_id}>
                    {c.nome}{c.padrao ? ' (padrão da empresa)' : ''}
                  </option>
                ))}
              </select>
              <FieldError msg={erros.calendario} />
            </label>
            <label style={{ ...campo, gridColumn: '1 / -1' }}>
              <span>Descrição do plano (opcional)</span>
              <input
                value={form.descricao} maxLength={200}
                onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))}
                placeholder="Em branco, herda a descrição do modelo"
              />
            </label>
          </div>
        )}

        <p style={ajuda}>
          As datas não vêm do modelo — o que se repete é a <strong>estrutura</strong>. Os vínculos com
          local, etapa e item orçado ficam para trás de propósito: eles são da obra de origem, e um
          plano ponderando o avanço pelo orçamento de outra obra sai errado no boletim de medição.
        </p>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={escolhido == null || !form.data_inicio || aplicar.isPending}
            onClick={enviar}
          >
            {aplicar.isPending ? 'Aplicando…' : 'Aplicar à obra'}
          </Btn>
        </div>
      </div>
    </Modal>
  )
}

const campo: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 5, fontSize: 12.5 }
const ajuda: React.CSSProperties = { fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5, margin: 0 }
const corpo: React.CSSProperties = { fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }
