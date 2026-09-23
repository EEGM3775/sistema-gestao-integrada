import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { Select } from '../ui'
import { FONTE_ROTULO } from '../lib'
import type { BaseResumo } from '../types'

/** Escolher a publicação em passos encadeados, e não numa lista só.
 *
 *  **O problema que isto resolve.** A identidade de uma publicação é
 *  `fonte × UF × mês × regime` — quatro eixos. Uma lista plana multiplica os
 *  quatro: com a SINAPI carregada de 01/2025 a 08/2026 são 27 UFs × 20 meses ×
 *  3 regimes = **1.460 opções** num `<select>`, ordenadas por data, em que achar
 *  "SINAPI BA 08/2026 desonerado" é rolar às cegas. O relato do dono foi direto:
 *  *"a seleção é extremamente enorme"*.
 *
 *  Encadear devolve cada eixo ao seu tamanho natural: ~27 praças, ~20 meses,
 *  3 regimes. Nenhuma caixa passa de algumas dezenas de itens, e a escolha
 *  vira uma frase — *SINAPI BA · 08/2026 · desonerado* — em vez de uma busca.
 *
 *  **Por que o regime não pode ficar de fora.** Onerado × desonerado muda o
 *  custo de toda composição com mão de obra; são publicações diferentes, não um
 *  detalhe de exibição. Sem esta terceira caixa, `fonte+UF+mês` ainda deixa três
 *  candidatas e o sistema teria de escolher uma por conta própria — exatamente o
 *  tipo de palpite que faz um orçamento sair com o custo errado sem ninguém ver.
 *
 *  **A quarta caixa, e por que ela não é enfeite.** A EMBASA publica, para o
 *  mesmo semestre e o mesmo regime, uma tabela por escopo × convenção coletiva:
 *  expansão, operação de água, de esgoto — cada uma pelo sindicato da região, e
 *  todas com os **mesmos 6.992 códigos e preços diferentes**. Sem esta caixa, as
 *  seis chegariam ao fim do encadeamento como seis linhas de nome igual e o
 *  sistema escolheria uma — que é o palpite que faz um orçamento sair com o
 *  preço de outra região sem ninguém ver. Ela fica cinza e travada nas fontes
 *  que publicam uma tabela só, que são quase todas.
 *
 *  Trocar de praça **não** perde o resto da escolha: `escolher` tenta o mesmo
 *  mês e o mesmo regime na praça nova e só relaxa quando aquela combinação não
 *  existe — quem compara o mesmo mês entre dois estados não tem de reescolher a
 *  data toda vez. */

/** `onerado` é o nome do campo, não o da vida real: a publicação que a Caixa
 *  chama de "não desonerada" chega aqui como `onerado`, e orçamentista procura
 *  pelo nome do edital. `na` é a base sem eixo de encargos (TCPO, SICRO). */
const REGIME_ROTULO: Record<string, string> = {
  onerado: 'Não desonerado', desonerado: 'Desonerado',
  sem: 'Sem encargos', na: 'Regime único',
}

/** Fonte + UF é **uma** escolha, não duas: ninguém quer SINAPI sem saber de
 *  onde, e base nacional (TCPO, SICRO) não tem UF para escolher. */
const chaveDaPraca = (b: BaseResumo) => `${b.fonte}|${b.uf}`
const rotuloDaPraca = (b: BaseResumo) =>
  `${FONTE_ROTULO[b.fonte] ?? b.fonte.toUpperCase()}${b.uf ? ` — ${b.uf}` : ' — Nacional'}`

/** `2026-08-01` → `08/2026`. Só o mês importa: o dia é sempre 1 (data-base). */
const rotuloDoMes = (iso: string) => {
  const [ano, mes] = iso.split('-')
  return `${mes}/${ano}`
}

/** O nome da variante que a **fonte** deu, e não o slug do banco.
 *
 *  O rótulo da publicação da EMBASA é `EMBASA BA 06/2026 · Expansão SINTRACOM
 *  (LS H 158,56% · M 119,40%) R2`: o que discrimina vem depois do primeiro `· `,
 *  e o que vem antes já está nas três caixas anteriores. Quando o rótulo não
 *  segue esse desenho — publicação carregada antes da ORC.8b, ou rótulo editado
 *  à mão —, o slug cru é melhor que uma caixa vazia: feio, mas verdadeiro. */
const rotuloDaVariante = (b: BaseResumo) => {
  const corte = b.rotulo.indexOf('· ')
  return corte >= 0 ? b.rotulo.slice(corte + 2) : b.variante
}

export default function SeletorDeBase({ bases, valor, onChange, rotuloVazio, style }: {
  bases: BaseResumo[]
  valor: number | ''
  onChange: (baseId: number | '') => void
  /** Texto da opção "nenhuma publicação", quando **não escolher** é uma resposta
   *  legítima — no orçamento novo, "sem base" quer dizer preço digitado à mão.
   *  Sem esta prop a caixa só oferece publicações, e o vazio é mero placeholder. */
  rotuloVazio?: string
  style?: CSSProperties
}) {
  const atual = bases.find(b => b.base_id === valor)
  const praca = atual ? chaveDaPraca(atual) : ''
  const mes = atual?.mes_referencia ?? ''
  const regime = atual?.regime_encargos ?? ''
  const variante = atual?.variante ?? ''

  // Praças em ordem alfabética — é assim que se procura um estado.
  const pracas = useMemo(() => {
    const vistas = new Map<string, string>()
    for (const b of bases) if (!vistas.has(chaveDaPraca(b))) vistas.set(chaveDaPraca(b), rotuloDaPraca(b))
    return [...vistas].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR'))
  }, [bases])

  // Meses do mais recente para o mais antigo: a data-base que se quer é quase
  // sempre a última publicada.
  const meses = useMemo(() => {
    const vistos = new Set<string>()
    for (const b of bases) if (chaveDaPraca(b) === praca) vistos.add(b.mes_referencia)
    return [...vistos].sort((a, b) => b.localeCompare(a))
  }, [bases, praca])

  const regimes = useMemo(() => {
    const vistos = new Set<string>()
    for (const b of bases) {
      if (chaveDaPraca(b) === praca && b.mes_referencia === mes) vistos.add(b.regime_encargos)
    }
    return [...vistos]
  }, [bases, praca, mes])

  // As tabelas que sobram depois dos três primeiros eixos. Ordenadas pelo nome
  // que a fonte deu — na EMBASA é `1.1`, `1.2`, `1.3`…, a ordem da própria
  // página, e a alfabética a preserva.
  const variantes = useMemo(() => {
    const vistas = new Map<string, string>()
    for (const b of bases) {
      if (chaveDaPraca(b) === praca && b.mes_referencia === mes && b.regime_encargos === regime) {
        vistas.set(b.variante, rotuloDaVariante(b))
      }
    }
    return [...vistas].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR'))
  }, [bases, praca, mes, regime])

  /** Resolve os quatro eixos numa publicação, relaxando na ordem em que doer
   *  menos: primeiro tenta o pedido exato, depois solta a variante, depois o
   *  regime (o mês é mais importante — é a data-base do orçamento), e só então
   *  cai no mês mais recente da praça. */
  function escolher(
    novaPraca: string, novoMes: string, novoRegime: string, novaVariante: string,
  ) {
    if (novaPraca === '') return onChange('')
    const naPraca = bases.filter(b => chaveDaPraca(b) === novaPraca)
    if (naPraca.length === 0) return

    const doMesERegime = naPraca.filter(
      b => b.mes_referencia === novoMes && b.regime_encargos === novoRegime,
    )
    const exata = doMesERegime.find(b => b.variante === novaVariante)
    if (exata) return onChange(exata.base_id)
    if (doMesERegime.length > 0) return onChange(doMesERegime[0].base_id)

    const doMes = naPraca.filter(b => b.mes_referencia === novoMes)
    if (doMes.length > 0) return onChange(doMes[0].base_id)

    const recentes = [...naPraca].sort((a, b) => b.mes_referencia.localeCompare(a.mes_referencia))
    const preferida = recentes.find(b => b.regime_encargos === novoRegime) ?? recentes[0]
    onChange(preferida.base_id)
  }

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', ...style }}>
      <Select
        value={praca}
        onChange={e => escolher(e.target.value, mes, regime, variante)}
        title="Fonte e estado"
        style={{ maxWidth: 190 }}
      >
        {rotuloVazio !== undefined
          ? <option value="">{rotuloVazio}</option>
          : praca === '' && <option value="">Escolha a base…</option>}
        {pracas.map(([chave, rotulo]) => (
          <option key={chave} value={chave}>{rotulo}</option>
        ))}
      </Select>

      <Select
        value={mes}
        onChange={e => escolher(praca, e.target.value, regime, variante)}
        title="Data-base (mês de referência)"
        disabled={meses.length === 0}
        style={{ maxWidth: 120, opacity: meses.length === 0 ? 0.5 : 1 }}
      >
        {mes === '' && <option value="">Mês…</option>}
        {meses.map(m => <option key={m} value={m}>{rotuloDoMes(m)}</option>)}
      </Select>

      {/* **Cinza, não escondida.** Nem toda fonte publica os dois regimes — uma
          tabela de concessionária (EMBASA, SEDOP) costuma ter preço único, e a
          SINAPI tem três. Sumir com a caixa faria a linha inteira mudar de
          tamanho ao trocar de fonte, e quem nunca viu o eixo não descobriria que
          ele existe. Travada e apagada diz as duas coisas: "isto existe" e
          "aqui não se aplica". Mesma régua do mês antes de escolher a praça. */}
      <Select
        value={regime}
        onChange={e => escolher(praca, mes, e.target.value, variante)}
        title={regimes.length > 1 ? 'Regime de encargos' : 'Esta publicação tem regime único'}
        disabled={regimes.length <= 1}
        style={{ maxWidth: 150, opacity: regimes.length <= 1 ? 0.5 : 1 }}
      >
        {regimes.length === 0 && <option value="">Regime…</option>}
        {regimes.map(r => <option key={r} value={r}>{REGIME_ROTULO[r] ?? r}</option>)}
      </Select>

      {/* Mesma régua das outras: cinza e travada quando a fonte publica uma
          tabela só — que é o caso de todas menos a EMBASA. Mais larga porque o
          rótulo dela carrega o que discrimina: escopo, convenção e a leis
          sociais do cabeçalho do PDF. */}
      <Select
        value={variante}
        onChange={e => escolher(praca, mes, regime, e.target.value)}
        title={
          variantes.length > 1
            ? 'Tabela da publicação (escopo e convenção coletiva)'
            : 'Esta publicação tem tabela única'
        }
        disabled={variantes.length <= 1}
        style={{ maxWidth: 260, opacity: variantes.length <= 1 ? 0.5 : 1 }}
      >
        {variantes.length === 0 && <option value="">Tabela…</option>}
        {variantes.map(([chave, rotulo]) => (
          <option key={chave} value={chave}>{rotulo || 'Tabela única'}</option>
        ))}
      </Select>
    </div>
  )
}
