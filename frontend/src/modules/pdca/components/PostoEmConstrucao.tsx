import { Card, SectionHead } from '@/components/malha'

interface Props {
  titulo: string
  cadencia: string
  pergunta: string
  /** O que a pessoa vai conseguir fazer aqui — em verbos do trabalho dela,
   *  nunca em nome de tabela nem de fatia. */
  fara: string[]
  /** Quando o posto depende de leitura que o servidor ainda não faz, a espera é
   *  dita em voz alta: prometer tela sem dado é o que fabrica número. */
  esperando?: string
}

export function PostoEmConstrucao({ titulo, cadencia, pergunta, fara, esperando }: Props) {
  return (
    <div style={{ padding: '24px 26px', display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 760 }}>
      <SectionHead sub={`Cadência: ${cadencia}`}>{titulo}</SectionHead>

      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div
            style={{
              fontSize: 15, color: 'var(--ink)', fontWeight: 650,
              lineHeight: 1.45, fontStyle: 'italic',
            }}
          >
            {pergunta}
          </div>

          <div
            style={{
              fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6,
              paddingTop: 12, borderTop: '1px solid var(--line-2)',
            }}
          >
            Este posto ainda não está no ar. Quando estiver, você vai:
            <ul style={{ margin: '9px 0 0', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 5 }}>
              {fara.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>

          {esperando && (
            <div
              style={{
                fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6,
                paddingTop: 12, borderTop: '1px solid var(--line-2)',
              }}
            >
              {esperando}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
