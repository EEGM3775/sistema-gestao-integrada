# Portais e aplicativos — a interface de cada participante

> Distinção central (alinhada a [09-verticais-por-participante.md](09-verticais-por-participante.md)):
> **participante empresarial não tem "portal" — tem a sua edição** (é tenant, loga no app normal,
> com o hub da edição dele). **Portal** é a interface restrita das **personas de consumidor**
> (comprador, investidor, morador — quem não compra sistema de negócio), autenticadas pela IAM com
> escopo por objeto (E2 de [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md)).
> Nenhum portal tem backend próprio: consome APIs dedicadas do backend Django (AD-8) com
> serializers **allowlist** da persona (o mascaramento de campo da Fase 9 já dá o mecanismo).
> UI: React no mesmo shell (rotas `/portal/*`), **PWA-first** — app "instalável" sem custo de loja.

## 1. Portais de consumidor (personas E2)

| Portal | Persona | O que vê/faz | Módulos-fonte | Horizonte |
|---|---|---|---|---|
| **Portal do cliente** | Comprador da unidade | Contrato, extrato e **2ª via de boleto** (Asaas ✅), evolução da obra curada (diário/drone), documentos, vistoria, **abrir chamado de garantia**, manual do proprietário | clientes, moduloerp, funcoescobrancas, modulodiario, assistência técnica | **H1 — o primeiro** |
| Portal do investidor | Investidor do empreendimento | Andamento físico-financeiro, prestação de contas, documentos | empreendimentos, moduloerp, viabilidade | H3 |
| Portal do proprietário | Dono de unidade entregue | Manual, garantias, chamados, documentos do imóvel | assistência técnica, DMS | H2 (evolução do portal do cliente) |
| Portal do morador / síndico | Condomínio (personas da **Edição Administradora**) | Taxas (Asaas), reservas, avisos, assembleias, chamados prediais | condomínio, facility | H3 |

**Por que o portal do cliente primeiro:** todos os dados já existem no sistema (contrato,
parcelas, boletos Asaas com webhook, diário com fotos); reduz custo de suporte da construtora
(2ª via de boleto e "como anda a obra" são o grosso das ligações); é argumento de venda do SaaS
("seu cliente acompanha tudo"); e cria a base instalada de compradores que depois recebe
assistência técnica, indicação e — na entrega — vira morador da Edição Administradora. É também o
piloto do E2 com escopo mínimo: um objeto (`ClienteEmpreendimento`) por vínculo.

## 2. Workspaces internos (UIs do tenant, não personas)

| Workspace | Quem usa | O que concentra | Horizonte |
|---|---|---|---|
| Portal da obra | Equipe de campo do tenant | Visão única da obra: diário, etapas, entregas do dia, pendências | H1 |
| Fila da assistência técnica | Técnico de campo do tenant | Chamados, rota, checklist, foto antes/depois, assinatura do morador | H2 |
| Hub de cada edição vertical | O tenant da edição | Fila de RFQs (Loja), medições a faturar (Empreiteiro), carteira de parceiros (Imobiliária) | junto com a edição ([09](09-verticais-por-participante.md) §6) |

O que antes se pensaria como "portal do fornecedor/empreiteiro/corretor/engenheiro" **é o hub da
edição correspondente** — a empresa loga no seu próprio tenant e trabalha; o que chega dos
parceiros (RFQ, boletim, espelho) aparece dentro do fluxo normal dela via esfera transacional (E1).

## 3. Aplicativos móveis

Estratégia: **PWA primeiro** (mesmo código React, offline via service worker); nativo só onde
hardware/offline profundo exigir. O bot WhatsApp ✅ (`funcoeswhatsapp`) já é o "app de menor
atrito" — continua como canal paralelo de captura.

| App | Persona/tenant | Offline? | Recursos de dispositivo | Observação |
|---|---|---|---|---|
| **App da obra** (mestre/encarregado) | Tenant (campo) | **Sim — crítico** (canteiro sem sinal) | Câmera, GPS, voz→texto | Diário, foto georreferenciada, apontamento de equipe/ponto, recebimento de material. O WhatsApp bot é o MVP disso ✅ |
| App do engenheiro | Tenant (RT) | Parcial | Câmera | Aprovações, não-conformidades, medições em campo |
| App do técnico (assistência) | Tenant (pós-obra) | Sim | Câmera, assinatura na tela | Espelho da fila de chamados |
| App do corretor | Tenant da Edição Imobiliária | Não | — | Carteira + reserva + simulador na mão |
| App do proprietário/morador | Persona (B2C) | Não | Push | Boleto, chamado, avisos — o portal instalado |
| App do gestor (dono da empresa) | Tenant (decisor) — qualquer edição | Não | Push | KPIs, aprovações pendentes, alertas do motor de regras (E6) |

## 4. Regras transversais

- **Identidade:** persona de consumidor nasce por **convite** de um tenant e autentica na IAM —
  nunca cadastro paralelo por portal (AD-5). Um mesmo e-mail pode acumular vínculos (comprador em
  2 construtoras). Empresa **não** vira persona: recebe convite para **trial da edição dela**
  ([09](09-verticais-por-participante.md) §3).
- **Autorização:** escopo por objeto (ABAC, fatia D do [rbac-abac.md](../arquitetura/rbac-abac.md));
  o serializer da persona é **allowlist de campos** (nunca reusar o serializer interno).
- **Auditoria:** acesso de persona externa é logado no `AuditLog` (Fase 9.E) como qualquer outro.
- **Curadoria:** o que o consumidor vê é sempre subconjunto **explicitamente publicado** pelo
  tenant (fotos do diário marcadas como públicas, documentos liberados) — default fechado.
- **Monetização:** portais de consumidor são pagos pelo tenant (por unidade ativa) — ver
  [07-monetizacao-da-expansao.md](07-monetizacao-da-expansao.md) §3.
- **Notificação:** push do PWA + e-mail + WhatsApp (canal já multi-tenant ✅) — escolha da persona.
