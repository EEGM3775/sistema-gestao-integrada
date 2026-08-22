import { AlertTriangle, DraftingCompass, Lock, ShieldCheck } from 'lucide-react'
import { Card, Empty, Loading, Modal, Num, Pill, SectionHead } from '@/components/malha'
import { useStatusPrancheta } from '../hooks'

/**
 * **Formatos & motores** — o que ESTE plano abre, e o que esta instalação tem.
 *
 * Era uma aba, ao lado das telas de trabalho, e não deveria: não recebe obra, não
 * tem verbo e fala de assinatura, não de acervo. Agora abre **de dentro do envio**,
 * que é o único momento em que a pergunta existe — *"posso mandar este arquivo?"*.
 * Quando a tela de Plano e quotas for construída ([frontend.md §5.16]), é para lá
 * que ela vai; até então, mora onde é útil em vez de ocupar uma parada na
 * navegação.
 *
 * Declara o catálogo **inteiro** com o cadeado e o motivo, nunca só o que passa:
 * um cliente que não sabe que o produto lê RVT não tem por que pedir o upgrade. E
 * as três colunas do motor respondem perguntas diferentes de propósito —
 * `habilitado` é o **plano**, `implementado` é o **código**, `disponível` é esta
 * **imagem**. Habilitado e indisponível é problema de deploy, não de venda.
 */
export function FormatosEMotores({ aoFechar }: { aoFechar: () => void }) {
  const { data, isLoading } = useStatusPrancheta(true)

  return (
    <Modal titulo="O que dá para enviar" onClose={aoFechar} largura={760}>
      {isLoading && <Loading o="os formatos do plano" />}
      {!isLoading && !data && <Empty>Não foi possível ler o status do módulo agora.</Empty>}

      {data && (
        <div style={{ display: 'grid', gap: 20 }}>
          <section style={{ display: 'grid', gap: 10 }}>
            <SectionHead
              sub={`Plano ${data.plano ?? '—'} · o arquivo é recusado na entrada quando o formato não está contratado, e o motivo vem junto.`}
              right={
                <Pill kind={data.conversao_disponivel ? 'good' : 'danger'}>
                  {data.conversao_disponivel ? 'conversão disponível' : 'sem motor nesta instalação'}
                </Pill>
              }
            >
              Formatos
            </SectionHead>
            <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))' }}>
              {data.formatos.map((f) => (
                <Card key={f.codigo} style={{ display: 'grid', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <DraftingCompass size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />
                    <strong style={{ fontSize: 13, color: 'var(--ink)' }}>{f.nome}</strong>
                    {f.contratado
                      ? <Pill kind="good">no seu plano</Pill>
                      : <Pill kind="accent"><Lock size={11} /> travado</Pill>}
                  </div>
                  <span className="num" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                    {f.extensoes.join(' · ')} · até <Num size={11.5}>{f.max_mb}</Num> MB
                  </span>
                  {!f.contratado && (
                    <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                      {f.exige_motor_premium
                        ? 'Exige o motor de alta fidelidade — o degrau é o motor, não o formato.'
                        : 'Não incluído neste plano.'}
                    </span>
                  )}
                </Card>
              ))}
            </div>
          </section>

          <section style={{ display: 'grid', gap: 10 }}>
            <SectionHead sub="Licença junto do motor: o LibreDWG é GPLv3 e entra como binário separado.">
              Motores
            </SectionHead>
            <Card pad={false} style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 620 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    {['Motor', 'Plano', 'Código', 'Nesta instalação', 'Licença'].map((h) => (
                      <th key={h} style={{ textAlign: 'left', padding: '9px 12px', fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.motores.map((m) => (
                    <tr key={m.codigo} style={{ borderBottom: '1px solid var(--line)' }}>
                      <td style={{ padding: '9px 12px', fontSize: 13, color: 'var(--ink)' }}>
                        {m.nome}
                        {m.custo_por_traducao && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}> · cobra por arquivo</span>}
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        {m.habilitado ? <Pill kind="good">habilitado</Pill> : <Pill kind="slate">fora do plano</Pill>}
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        {m.implementado ? <Pill kind="info">implementado</Pill> : <Pill kind="slate">fatia futura</Pill>}
                      </td>
                      <td style={{ padding: '9px 12px' }}>
                        {m.disponivel
                          ? <Pill kind="good"><ShieldCheck size={11} /> {m.versao}</Pill>
                          : m.implementado && m.habilitado
                            ? <Pill kind="danger"><AlertTriangle size={11} /> não instalado</Pill>
                            : <Pill kind="slate">—</Pill>}
                      </td>
                      <td style={{ padding: '9px 12px', fontSize: 12, color: 'var(--ink-3)' }}>{m.licenca}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </section>
        </div>
      )}
    </Modal>
  )
}
