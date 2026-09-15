import { Printer, Receipt } from 'lucide-react'
import { Btn, Num, Pill } from '@/components/malha'
import type { Contrato, ContextoDeMedicao, Medicao } from '../types'
import { CORES_MEDICAO } from './cores'

/**
 * **O boletim — o documento que se assina.**
 *
 * Uma medição congelada não é uma planilha de digitação em cinza: é o papel que
 * o engenheiro, o fiscal e o empreiteiro assinam, e que o financeiro arquiva ao
 * lado do título. A tela antiga mostrava a medição aprovada na **mesma grade**
 * do rascunho, com as mesmas colunas editáveis-porém-travadas e as 200 linhas
 * do contrato inteiro — inclusive as que a medição não tocou.
 *
 * O que muda aqui, e cada mudança responde a uma pergunta que o papel responde:
 *
 * - **só as linhas medidas**, porque o boletim é o que se paga, não o contrato;
 * - **quem apurou, quem atestou e quando** — a escada inteira, com data;
 * - **bruto → retenção → deduções → líquido**, as parcelas separadas, porque é
 *   assim que o empreiteiro confere contra a nota dele;
 * - **o título gerado**, com o número do ERP, porque a pergunta seguinte à
 *   aprovação é sempre "e quando isso é pago?";
 * - **campo de assinatura**, porque ele é impresso e levado a campo.
 *
 * `@media print` tira a navegação e o fundo: o que sai na impressora é o
 * documento, não a tela.
 */
export default function BoletimDeMedicao({ medicao, contrato, contexto }: {
  medicao: Medicao
  contrato: Contrato
  contexto: ContextoDeMedicao | undefined
}) {
  const t = medicao.totais
  const porItem = new Map(
    (contexto?.linhas ?? []).map(l => [l.item_contrato_id, l]),
  )
  const temEstoque = medicao.itens.some(i => Number(i.quantidade_estocada) !== 0)

  return (
    <div className="boletim">
      <style>{estilo}</style>

      <div className="boletim-cabecalho">
        <div>
          <h1 style={{ margin: 0, fontSize: 20 }}>
            Boletim de medição nº {medicao.numero}
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ink-2)' }}>
            Contrato {contrato.numero} · {contrato.fornecedor_nome} · {contrato.obra_nome}
          </p>
          <p style={{ margin: '3px 0 0', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 620 }}>
            {contrato.objeto}
          </p>
        </div>
        <div className="sem-impressao">
          <Btn onClick={() => window.print()}><Printer size={14} /> Imprimir</Btn>
        </div>
      </div>

      <div className="boletim-faixa">
        <Campo rotulo="Período">
          {data(medicao.periodo_inicio)} a {data(medicao.periodo_fim)}
        </Campo>
        <Campo rotulo="Situação">
          <Pill kind={CORES_MEDICAO[medicao.status]}>{medicao.status_rotulo}</Pill>
        </Campo>
        <Campo rotulo="Regime">{contrato.regime_rotulo}</Campo>
        <Campo rotulo="Apurada por">{medicao.apurada_por || '—'}</Campo>
        <Campo rotulo="Congelada em">
          {medicao.congelada_em ? dataHora(medicao.congelada_em) : '—'}
        </Campo>
        {medicao.retifica != null && (
          <Campo rotulo="Retifica">medição nº {medicao.retifica}</Campo>
        )}
      </div>

      {contrato.regime === 'administracao' ? (
        <div className="boletim-bloco">
          <h2>Custo do período</h2>
          <table className="boletim-tabela">
            <tbody>
              <tr>
                <td>Custo reembolsável declarado</td>
                <td className="num"><Num>{dinheiro(medicao.custo_reembolsavel ?? 0)}</Num></td>
              </tr>
              <tr>
                <td>
                  Taxa de administração ({Number(medicao.taxa_administracao_aplicada ?? 0)}%)
                </td>
                <td className="num">
                  <Num>
                    {dinheiro(
                      Number(medicao.custo_reembolsavel ?? 0)
                      * Number(medicao.taxa_administracao_aplicada ?? 0) / 100,
                    )}
                  </Num>
                </td>
              </tr>
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '8px 0 0' }}>
            Custo <strong>{medicao.custo_origem_rotulo.toLowerCase()}</strong>
            {medicao.apurada_por ? ` · ${medicao.apurada_por}` : ''}
          </p>
        </div>
      ) : (
        <div className="boletim-bloco">
          <h2>
            Itens medidos ({medicao.itens.length}
            {contexto ? ` de ${contexto.linhas.length} do contrato` : ''})
          </h2>
          <table className="boletim-tabela">
            <thead>
              <tr>
                <th>Item</th>
                <th>Descrição</th>
                <th>Un.</th>
                <th className="num">Contratado</th>
                <th className="num">Acum. anterior</th>
                <th className="num">Este período</th>
                {temEstoque && <th className="num">Estocado</th>}
                <th className="num">Acumulado</th>
                <th className="num">%</th>
                <th className="num">Preço</th>
                <th className="num">Valor</th>
              </tr>
            </thead>
            <tbody>
              {medicao.itens.map(item => {
                const linha = porItem.get(item.item_contrato)
                const contratada = Number(linha?.quantidade_contratada ?? 0)
                const anterior = Number(linha?.quantidade_ja_medida ?? 0)
                const acumulado = anterior + Number(item.quantidade)
                return (
                  <tr key={item.item_medicao_id}>
                    <td className="mono">{item.codigo}</td>
                    <td>
                      {item.descricao}
                      {item.observacao && (
                        <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                          {item.observacao}
                        </div>
                      )}
                    </td>
                    <td>{item.unidade}</td>
                    <td className="num">{contratada ? quantidade(contratada) : '—'}</td>
                    <td className="num">{quantidade(anterior)}</td>
                    <td className="num forte">{quantidade(item.quantidade)}</td>
                    {temEstoque && (
                      <td className="num">{quantidade(item.quantidade_estocada)}</td>
                    )}
                    <td className="num">{quantidade(acumulado)}</td>
                    <td className="num">
                      {contratada ? `${((acumulado / contratada) * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td className="num">{dinheiro(item.preco_unitario)}</td>
                    <td className="num">
                      {dinheiro(Number(item.quantidade) * Number(item.preco_unitario))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="boletim-totais">
        {Number(t.material_estocado) !== 0 && (
          <>
            <Linha rotulo="Serviço executado" valor={dinheiro(t.executado)} />
            <Linha
              rotulo="Material posto na obra (variação do período)"
              valor={dinheiro(t.material_estocado)}
            />
          </>
        )}
        <Linha rotulo="Bruto" valor={dinheiro(t.bruto)} forte />
        <Linha
          rotulo={`Retenção contratual (${Number(t.retencao_percentual)}%) · ${contrato.retencao_natureza_rotulo}`}
          valor={`− ${dinheiro(t.retencao)}`}
        />
        {t.deducoes.map(d => (
          <Linha
            key={d.deducao_id}
            rotulo={`${d.tipo_rotulo}${d.descricao ? ` · ${d.descricao}` : ''}${
              d.percentual ? ` (${Number(d.percentual)}%)` : ''
            }`}
            valor={`− ${dinheiro(d.valor)}`}
          />
        ))}
        <Linha rotulo="Líquido a pagar" valor={dinheiro(t.liquido)} destaque />
      </div>

      {medicao.conta_pagar_ref && (
        <p className="boletim-titulo">
          <Receipt size={14} />
          Gerou o título <strong>#{medicao.conta_pagar_ref}</strong> no financeiro.
          Quem decide quando o dinheiro sai do caixa é o ERP — este documento
          autoriza o pagamento, não o executa.
        </p>
      )}

      {medicao.observacao && (
        <div className="boletim-bloco">
          <h2>Observações</h2>
          <p style={{ fontSize: 13, whiteSpace: 'pre-wrap', margin: 0 }}>
            {medicao.observacao}
          </p>
        </div>
      )}

      {(medicao.escada?.atestos.length ?? 0) > 0 && (
        <div className="boletim-bloco">
          <h2>Escada de atesto</h2>
          <table className="boletim-tabela">
            <thead>
              <tr>
                <th>Degrau</th>
                <th>Decisão</th>
                <th>Quem</th>
                <th>Com que autoridade</th>
                <th>Quando</th>
                <th>Observação</th>
              </tr>
            </thead>
            <tbody>
              {medicao.escada?.atestos.map(a => (
                <tr key={a.atesto_id}>
                  <td>{a.nivel_ordem}. {a.nivel_nome}</td>
                  <td>
                    <Pill kind={a.decisao === 'aprovado' ? 'good' : 'danger'}>
                      {a.decisao === 'aprovado' ? 'Aprovado' : 'Reprovado'}
                    </Pill>
                  </td>
                  <td>{a.autor || '—'}</td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {a.permissao_conferida || '—'}
                  </td>
                  <td>{dataHora(a.decidido_em)}</td>
                  <td>{a.observacao || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* As linhas de assinatura ficam **em branco**: este documento é impresso
          e assinado à mão em campo. O que o sistema sabe (quem apurou, quem
          atestou) está na faixa e na escada acima — imprimir o nome na linha de
          assinatura faria o papel parecer assinado sem ninguém ter assinado. */}
      <div className="boletim-assinaturas">
        <Assinatura papel="Fiscal / engenheiro da obra" nome="" />
        <Assinatura papel="Gerente do contrato" nome="" />
        <Assinatura papel={`Contratada · ${contrato.fornecedor_nome}`} nome="" />
      </div>
    </div>
  )
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.04em' }}>
        {rotulo}
      </div>
      <div style={{ fontSize: 13.5, marginTop: 2 }}>{children}</div>
    </div>
  )
}

function Linha({ rotulo, valor, forte, destaque }: {
  rotulo: string; valor: string; forte?: boolean; destaque?: boolean
}) {
  return (
    <div className={`boletim-linha${destaque ? ' destaque' : ''}`}>
      <span style={{ fontWeight: forte || destaque ? 600 : 400 }}>{rotulo}</span>
      <span style={{
        fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
        fontWeight: forte || destaque ? 600 : 400,
        fontSize: destaque ? 18 : 14,
        color: destaque ? 'var(--brand)' : 'var(--ink)',
      }}>
        {valor}
      </span>
    </div>
  )
}

function Assinatura({ papel, nome }: { papel: string; nome: string }) {
  return (
    <div>
      <div className="boletim-risco" />
      <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{papel}</div>
      <div style={{ fontSize: 12.5 }}>{nome || ' '}</div>
    </div>
  )
}

const data = (v: string) => v.split('-').reverse().join('/')
const dataHora = (v: string) =>
  new Date(v).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
const dinheiro = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const quantidade = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })

const estilo = `
.boletim { display: flex; flex-direction: column; gap: 18px; }
.boletim-cabecalho { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.boletim-faixa {
  display: flex; gap: 26px; flex-wrap: wrap;
  padding: 12px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
}
.boletim-bloco h2 { margin: 0 0 8px; font-size: 14px; }
.boletim-tabela { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.boletim-tabela th {
  text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ink-2); padding: 6px 8px; border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.boletim-tabela td { padding: 6px 8px; border-bottom: 1px solid var(--line); }
.boletim-tabela .num { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
.boletim-tabela .mono { font-family: var(--mono); }
.boletim-tabela .forte { font-weight: 600; }
.boletim-totais {
  display: flex; flex-direction: column; gap: 4px; margin-left: auto;
  min-width: min(420px, 100%);
}
.boletim-linha {
  display: flex; justify-content: space-between; gap: 20px; font-size: 13px;
  padding: 4px 0;
}
.boletim-linha.destaque { border-top: 2px solid var(--line); padding-top: 8px; margin-top: 4px; }
.boletim-titulo {
  display: flex; align-items: center; gap: 7px; font-size: 12.5px;
  color: var(--good-ink); background: var(--surface-2);
  padding: 9px 11px; border-radius: 8px; margin: 0;
}
.boletim-assinaturas {
  display: grid; gap: 28px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  margin-top: 26px;
}
.boletim-risco { border-top: 1px solid var(--ink-3); margin-bottom: 5px; }

@media print {
  .sem-impressao, nav, aside, header { display: none !important; }
  .boletim { gap: 14px; font-size: 11px; }
  .boletim-tabela { font-size: 10.5px; }
  .boletim-tabela tr { break-inside: avoid; }
  .boletim-assinaturas { break-inside: avoid; }
}
`
