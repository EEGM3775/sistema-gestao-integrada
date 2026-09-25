import { useState } from 'react'
import { Btn, Modal } from '@/components/malha'
import { useRegistrarOcorrencia } from '../hooks'
import { Ajuda, Campo, Escolhas, FaixaDeErro, Grupo, Linha } from './Formulario'
import { SeletorDeLugar } from './SeletorDeLugar'
import type { Ocorrencia, TipoOcorrencia } from '../types'
import { entrada } from '../estilos'
import { agoraLocal, primeiraFrase } from '../formato'
import { TIPOS_DE_OCORRENCIA } from '../vocabulario'


/** **Registrar o fato — sem atrito.**
 *
 *  Tipo, hora e o que aconteceu; o resto é opcional e fica para depois. É a
 *  porta mais larga do módulo de propósito: o quase-acidente é o registro que
 *  mais vale e o mais fácil de não fazer, e todo campo obrigatório a mais aqui
 *  vira subnotificação. Classificar (afastamento, dias) é outro verbo, de
 *  outra pessoa — quem é medido não classifica a própria medida. */
export function FormularioDeOcorrencia({
  obraId, aoFechar, aoCriar,
}: {
  obraId: number
  aoFechar: () => void
  aoCriar: (o: Ocorrencia) => void
}) {
  const registrar = useRegistrarOcorrencia()
  const [tipo, setTipo] = useState<TipoOcorrencia | null>(null)
  const [quando, setQuando] = useState(agoraLocal())
  const [descricao, setDescricao] = useState('')
  const [acidentado, setAcidentado] = useState('')
  const [agente, setAgente] = useState('')
  const [local, setLocal] = useState<number | null>(null)
  const [atividade, setAtividade] = useState<number | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const comVitima = TIPOS_DE_OCORRENCIA.find((t) => t.valor === tipo)?.vitima ?? false

  return (
    <Modal
      titulo="Registrar uma ocorrência"
      onClose={aoFechar}
      largura={640}
      alto
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={!tipo || !quando || !descricao.trim() || registrar.isPending}
            onClick={async () => {
              if (!tipo) return
              setErro(null)
              try {
                aoCriar(await registrar.mutateAsync({
                  obra: obraId, tipo, ocorrido_em: quando, descricao: descricao.trim(),
                  local, atividade,
                  acidentado_nome: comVitima ? acidentado.trim() : '',
                  agente_causador: agente.trim(),
                }))
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            {registrar.isPending ? 'Gravando…' : 'Registrar'}
          </Btn>
        </div>
      }
    >
      <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FaixaDeErro>{erro}</FaixaDeErro>

        <Grupo rotulo="O que foi">
          <Escolhas
            valor={tipo}
            aoEscolher={setTipo}
            opcoes={TIPOS_DE_OCORRENCIA.map((t) => ({ valor: t.valor, rotulo: t.rotulo, tom: t.tom }))}
          />
          {tipo && (
            <Ajuda>{TIPOS_DE_OCORRENCIA.find((t) => t.valor === tipo)?.explica}</Ajuda>
          )}
        </Grupo>

        <Linha>
          <Campo rotulo="Quando">
            <input
              type="datetime-local" value={quando} max={agoraLocal()}
              onChange={(e) => setQuando(e.target.value)} style={entrada}
            />
          </Campo>
          {comVitima && (
            <Campo rotulo="Quem se feriu" larga>
              <input value={acidentado} onChange={(e) => setAcidentado(e.target.value)} style={entrada} />
              <Ajuda>Pode ficar em branco agora e ser completado depois.</Ajuda>
            </Campo>
          )}
        </Linha>

        <Campo rotulo="O que aconteceu">
          <textarea
            rows={3} value={descricao} onChange={(e) => setDescricao(e.target.value)}
            style={{ ...entrada, resize: 'vertical' }}
            placeholder="Ex.: tábua caiu do 3º pavimento na área de circulação, sem atingir ninguém"
          />
        </Campo>

        <Campo rotulo="O que causou (opcional)">
          <input value={agente} onChange={(e) => setAgente(e.target.value)} style={entrada}
            placeholder="Ex.: guarda-corpo solto" />
        </Campo>

        <SeletorDeLugar
          obraId={obraId}
          local={local}
          atividade={atividade}
          aoMudarLocal={setLocal}
          aoMudarAtividade={setAtividade}
        />
      </div>
    </Modal>
  )
}
