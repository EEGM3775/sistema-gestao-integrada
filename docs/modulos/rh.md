# RH (`rh`)

> Gestão de pessoas: funcionários, cargos, folha de pagamento e documentos. Módulo **vendável**.
> Código: [backend/rh/](../../backend/rh/).

## Acesso
Entitlement **`rh`** (todo ViewSet declara `required_module = "rh"` com
`[IsAuthenticated, RequireModule]`). Isolado por tenant. **Atenção (LGPD):** guarda PII **sensível**
(dados médicos, bancários).

## Modelos
| Modelo | Guarda |
|---|---|
| `Cargo` | Cargo/função, departamento |
| `Funcionario` | Cadastro completo (PII), CTPS, salário-base, status do contrato; liga a usuário do sistema e empreendimento |
| `DadoMedicoFuncionario` | **Dados médicos gerais** (cartão SUS, tipo sanguíneo, alergias, medicamentos, contato de emergência) — 1-para-1, PII sensível |
| `ASOFuncionario` | **ASOs** (Atestado de Saúde Ocupacional) — múltiplos por funcionário (1 por exame ocupacional/ano: admissional/periódico/demissional), `arquivo` é upload (FileField), não URL — PII sensível |
| `DocumentoFuncionario` | Documentos (RG, CTPS, …) |
| `DadoBancarioFuncionario` | Dados bancários para pagamento |
| `PagamentoFuncionario` | Pagamentos avulsos (descontos, adicionais, líquido, forma) |
| `FolhaPagamento` | Folha mensal (bruto, descontos, proventos, líquido, holerite) — `unique(funcionario, mes)` |

## Relações
- `Funcionario.usuario` → OneToOne `nucleo.Usuario`; `Funcionario.cargo` → `Cargo`;
  `Funcionario.empreendimento_vinculado` → `empreendimentos.Empreendimento`.
- Os demais modelos referenciam `Funcionario`.
- `Funcionario` é referenciado por `obras` (responsáveis/equipe/etapas/documentos) e
  `clientes.ContratoCliente.responsavel`.

## Endpoints (`/api/`)
`/cargos/` · `/funcionarios/` · `/dados-medicos-funcionarios/` · `/asos-funcionarios/` ·
`/documentos-funcionarios/` · `/dados-bancarios-funcionarios/` · `/pagamentos-funcionarios/` ·
`/folhas-pagamento/`.

## Os quatro arquivos saem pela porta única, cada um com o gate do seu conteúdo

Os `FileField` do RH não são publicados como caminho de `/media/`: o JSON traz a URL do
[funcoesimpexp](funcoesimpexp.md) e o binário só sai por ela ([D70](../historico-correcoes.md),
[declaração em rh/impexp.py](../../backend/rh/impexp.py)).

| Arquivo | Recurso · espécie | Gate |
|---|---|---|
| `Funcionario.carteira_trabalho` | `rh.documentos` · `ctps` | `rh.documento.view` |
| `DocumentoFuncionario.arquivo` | `rh.documentos` · `documento` | `rh.documento.view` |
| `ASOFuncionario.arquivo` | `rh.aso` · `aso` | `rh.dado_medico.view` |
| `FolhaPagamento.holerite` | `rh.holerite` · `holerite` | `rh.folha.view` |

**O gate do arquivo é o mesmo que mascara o campo, e é o ponto.** O ASO responde a
`rh.dado_medico.view` — a permissão que já esconde o prontuário; o holerite, a `rh.folha.view` — a que
já esconde o salário. Enquanto isso não valia, a máscara da 9.C protegia o *valor* e o mesmo payload
entregava o PDF que o contém em claro.

A **entrada** continua sendo o POST do próprio ViewSet, com `UploadValidationMixin`. Levá-la também
para a porta única é a IE.6 ([funcoesimpexp §7.2](funcoesimpexp.md)).

## Frontend React ✅ 07/06/2026

Rotas: `/app/rh` · `/app/rh/cargos` · `/app/rh/:id`.

| Arquivo | Descrição |
|---|---|
| `pages/FuncionariosListPage.tsx` | Lista com filtros (busca+status), badge de status, salário (—se ausente/mascarado), link para Cargos |
| `pages/CargosPage.tsx` | CRUD completo de cargos (nome, departamento, descrição) |
| `pages/FuncionarioDetailPage.tsx` | 4 abas: Dados Pessoais, Documentos, Saúde, Financeiro |
| `components/FuncionarioForm.tsx` | Sheet de criação/edição de funcionário (5 seções) |
| `components/CargoForm.tsx` | Modal de criação/edição de cargo |
| `components/DadoMedicoForm.tsx` | Sheet dados de saúde gerais — 1-para-1 (exige papel `rh_medico`) |
| `components/ASOForm.tsx` | Sheet de ASO — registro múltiplo (1 por exame/ano), upload de arquivo via `<input type="file">` (exige papel `rh_medico`) |
| `components/DadoBancarioRHForm.tsx` | Modal conta bancária (exige papel `rh_financeiro`) |
| `components/PagamentoForm.tsx` | Modal registro de pagamento avulso (exige `rh_financeiro`) |
| `components/FolhaPagamentoForm.tsx` | Modal folha mensal (exige `rh_financeiro`) |
| `hooks/useCargos.ts` | CRUD de Cargo |
| `hooks/useFuncionarios.ts` | Lista de Funcionario |
| `hooks/useFuncionario.ts` | Detalhe + 7 sub-recursos (incl. `asos`, lista) com `Promise.allSettled`; 403 → flags `acessoMedicoNegado` / `acessoFinanceiroNegado` |

**Comportamento de acesso:**
- Aba **Saúde**: renderiza cadeado se o token não tem papel `rh_medico` (403)
- Aba **Financeiro**: renderiza cadeado se o token não tem papel `rh_financeiro` (403)
- Mascaramento de `salario_base` já ocorre no serializer do backend (Fase 6); a UI exibe `—` quando nulo

## Status / pendências
Backend e frontend ativos. Mascaramento de campos por papel (`rh_medico` / `rh_financeiro`) implementado
via `RequireRole` no backend (403 no endpoint) e flag de negação na UI. **Mascaramento granular de campo**
(campo visível mas redigido na resposta) é pendência da Fase 9 (LGPD). Trilha de auditoria: Fase 9.5.
