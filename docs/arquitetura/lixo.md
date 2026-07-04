# Sistema de Lixo — Exclusão Segura com Auditoria

> Plano de arquitetura para exclusão reversível de registros no SGI.
> **Status: 📋 Planejado** — implementação ocorre após todos os módulos principais existirem.
> Esta prancha define o contrato de implementação para que todos os módulos sejam projetados
> de forma compatível desde o início.

---

## 1. Decisões de design

| Decisão | Escolha | Justificativa |
|---|---|---|
| **Modelo de armazenamento** | Tabela genérica separada (`Lixo`) | Separa fisicamente dados ativos de excluídos; evita poluir queries de negócio com filtros de soft-delete em todos os ViewSets |
| **Quem pode restaurar/purgar** | Papel `gestor_lixo` (intra-tenant) | Mais granular que `admin`; não depende de admin da plataforma para decisões internas do tenant |
| **Retenção** | Auto-purge configurável por tenant + purge manual pelo `gestor_lixo` | Flexibilidade operacional; tenant controla o próprio ciclo de vida |
| **Escopo** | Todos os módulos principais | Implementação única na base → herança em todos os modelos sem retrabalho |

---

## 2. Modelo de dados

### 2.1 Tabela `Lixo`

```python
class Lixo(models.Model):
    """
    Repositório genérico de registros excluídos de qualquer módulo.
    Nunca é editado após criação — é imutável até purge ou restauração.
    """
    # Identidade do item no lixo
    lixo_id         = models.AutoField(primary_key=True)   # próprio ID, nunca reutilizado
    tenant          = models.ForeignKey('nucleo.Tenant', on_delete=models.PROTECT)
    modelo_origem   = models.CharField(max_length=100)     # ex: 'Empreendimento', 'Obra'
    app_origem      = models.CharField(max_length=100)     # ex: 'empreendimentos', 'obras'
    objeto_id       = models.PositiveBigIntegerField()     # ID original do registro

    # Snapshot completo do objeto no momento da exclusão
    payload         = models.JSONField()                   # todos os campos + relacionamentos

    # Auditoria de exclusão
    deleted_at      = models.DateTimeField(auto_now_add=True)
    deleted_by      = models.ForeignKey('nucleo.Usuario', on_delete=models.PROTECT,
                                        related_name='itens_excluidos')
    motivo_exclusao = models.TextField(blank=True)         # razão fornecida pelo usuário

    # Auditoria de restauração (preenchido se o item foi restaurado)
    restored_at     = models.DateTimeField(null=True, blank=True)
    restored_by     = models.ForeignKey('nucleo.Usuario', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='itens_restaurados')

    # Auditoria de purge permanente
    purged_at       = models.DateTimeField(null=True, blank=True)
    purged_by       = models.ForeignKey('nucleo.Usuario', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='itens_purgados')

    class Meta:
        db_table = 'lixo'
        indexes = [
            models.Index(fields=['tenant', 'modelo_origem']),
            models.Index(fields=['tenant', 'deleted_at']),
        ]
        # Cada objeto_id só pode aparecer UMA vez como ativo no lixo (sem purge)
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'modelo_origem', 'objeto_id'],
                condition=models.Q(purged_at__isnull=True, restored_at__isnull=True),
                name='lixo_unico_ativo'
            )
        ]
```

### 2.2 Configuração de retenção por tenant

```python
class ConfiguracaoLixo(models.Model):
    """
    Política de retenção do lixo para o tenant.
    Configurável pelo gestor_lixo via API/UI.
    """
    tenant             = models.OneToOneField('nucleo.Tenant', on_delete=models.CASCADE,
                                              related_name='configuracao_lixo')
    auto_purge_ativo   = models.BooleanField(default=False)
    retencao_dias      = models.PositiveIntegerField(default=30)   # 0 = somente manual
    notificar_antes    = models.PositiveIntegerField(default=7)    # dias antes do purge automático
    data_atualizacao   = models.DateTimeField(auto_now=True)
    atualizado_por     = models.ForeignKey('nucleo.Usuario', on_delete=models.SET_NULL, null=True)
```

---

## 3. Garantia de ID — sem reutilização

O SGI adota PostgreSQL como banco de registro. PostgreSQL garante que sequências de autoincrement
**nunca retrocedem**: mesmo após deletar um registro, a sequência continua avançando.

### Regra de ouro

> **Um `objeto_id` no lixo (não purgado, não restaurado) indica que aquele ID está "reservado".**
> O ID só é considerado liberado após o item ser purgado (`purged_at IS NOT NULL`).
> Na prática, PostgreSQL não vai reutilizá-lo de qualquer forma — esta regra é uma garantia
> semântica adicional para auditoria.

### Fluxo de IDs

```
Criação   → empreendimento_id = 42  (sequência em 42)
Exclusão  → registro movido para Lixo com objeto_id = 42
           → sequência agora em 43; próximo registro será 43
Restauração → INSERT em empreendimentos com empreendimento_id = 42 explícito
            → ajuste de sequência: SELECT setval('empreendimentos_empreendimento_id_seq',
                                                  MAX(empreendimento_id)) FROM empreendimentos
Purge     → linha do Lixo hard-deletada → ID 42 "liberado" semanticamente (mas nunca vai ser
             gerado pela sequência de novo, pois ela já passou de 42)
```

### Prevenção de conflito na restauração

Antes de restaurar, o sistema verifica:
1. `objeto_id` não existe na tabela origem → prossegue
2. `objeto_id` existe → bloqueia com erro `409 Conflict` (situação anormal — investigar)

---

## 4. Controle de acesso — papel `gestor_lixo`

| Operação | Usuário comum | `gestor_lixo` | Admin plataforma |
|---|---|---|---|
| Mover para o lixo | ✅ | ✅ | ✅ |
| Ver itens no lixo | ❌ | ✅ | ✅ |
| Restaurar item | ❌ | ✅ | ✅ |
| Purgar item permanentemente | ❌ | ✅ | ✅ |
| Configurar retenção automática | ❌ | ✅ | ✅ |
| Ver log de auditoria do lixo | ❌ | ✅ | ✅ |

O papel `gestor_lixo` é um entitlement intra-tenant atribuído na IAM ao nível de `Role`
(ver [acesso-e-permissoes.md](../acesso-e-permissoes.md)).
O guard no backend: `RequireRole('gestor_lixo')` nos endpoints sensíveis.

---

## 5. Fluxo de operações

### 5.1 Excluir (mover para lixo)

```
Usuário clica "Excluir" → Modal de confirmação (obrigatório, com campo motivo opcional)
  ↓
POST /api/lixo/mover/
  payload: { modelo: 'Empreendimento', objeto_id: 42, motivo: '...' }
  ↓
Backend:
  1. Busca o registro (scoped ao tenant)
  2. Serializa com todos os campos para JSON
  3. Cria entrada em Lixo
  4. Hard-deleta o registro original
  5. Retorna 200 com lixo_id criado
```

### 5.2 Restaurar

```
gestor_lixo clica "Restaurar" na tela do lixo
  ↓
POST /api/lixo/{lixo_id}/restaurar/
  ↓
Backend:
  1. Verifica papel gestor_lixo
  2. Verifica que objeto_id NÃO existe na tabela origem (anti-conflito)
  3. Deserializa payload → INSERT com ID explícito
  4. Atualiza sequência se necessário
  5. Marca restored_at e restored_by no Lixo
  6. Retorna 200 com o objeto restaurado
```

### 5.3 Purgar permanentemente

```
gestor_lixo clica "Purgar" (ação irreversível)
  ↓
DELETE /api/lixo/{lixo_id}/purgar/
  ↓
Backend:
  1. Verifica papel gestor_lixo
  2. Registra purged_at e purged_by (log de auditoria antes do hard-delete)
  3. Hard-deleta a linha do Lixo
  4. Retorna 204
```

### 5.4 Auto-purge (Celery task)

```python
# Roda diariamente via Celery beat
@shared_task
def auto_purge_lixo():
    configs = ConfiguracaoLixo.objects.filter(auto_purge_ativo=True, retencao_dias__gt=0)
    for config in configs:
        cutoff = timezone.now() - timedelta(days=config.retencao_dias)
        itens = Lixo.objects.filter(
            tenant=config.tenant,
            deleted_at__lt=cutoff,
            restored_at__isnull=True,
            purged_at__isnull=True,
        )
        for item in itens:
            item.purged_at = timezone.now()
            item.purged_by = None   # sistema, não usuário
            item.save()
            item.delete()           # hard-delete após registrar auditoria
```

---

## 6. API (endpoints planejados)

| Método | Endpoint | Papel | Descrição |
|---|---|---|---|
| `POST` | `/api/lixo/mover/` | qualquer autenticado | Move objeto para o lixo |
| `GET` | `/api/lixo/` | `gestor_lixo` | Lista itens do lixo do tenant |
| `GET` | `/api/lixo/{lixo_id}/` | `gestor_lixo` | Detalhe de um item (payload completo) |
| `POST` | `/api/lixo/{lixo_id}/restaurar/` | `gestor_lixo` | Restaura o registro original |
| `DELETE` | `/api/lixo/{lixo_id}/purgar/` | `gestor_lixo` | Purge permanente |
| `GET` | `/api/lixo/configuracao/` | `gestor_lixo` | Lê configuração de retenção |
| `PUT` | `/api/lixo/configuracao/` | `gestor_lixo` | Atualiza configuração de retenção |

Todos os endpoints filtram por tenant automaticamente (TenantScopedViewSetMixin).

---

## 7. Frontend (planejado)

Tela acessível por `/app/lixo` — visível apenas para `gestor_lixo`:

```
┌───────────────────────────────────────────────────────────────────┐
│  🗑 Lixo                             [⚙ Configurar retenção]     │
├──────────────┬────────────────────────────────────────────────────┤
│  Filtros:    │                                                    │
│  [Módulo ▼]  │  Tabela: Módulo | Nome | Excluído por | Data      │
│  [Data ▼]    │        |      |            | Ações [Restaurar][🗑] │
│              │  ...                                               │
│              │  Paginação                                         │
└──────────────┴────────────────────────────────────────────────────┘
```

Modal de purge permanente:
- Aviso em vermelho com texto do item a ser purgado
- Campo de confirmação: o usuário digita o nome do item para confirmar
- Botão "Purgar permanentemente" habilitado só após digitação correta

---

## 8. Escopo de módulos — todos os principais

| Módulo Django | Modelos com suporte ao lixo |
|---|---|
| `empreendimentos` | `Empreendimento` |
| `obras` | `Obra`, `EtapaObra`, `DocumentoObra` |
| `clientes` | `Cliente`, `ClienteEmpreendimento`, `ContratoCliente` |
| `fornecedores` | `Fornecedor` |
| `moduloerp` | `ContaPagar`, `ContaReceber`, `NotaFiscalEmitida` |
| `rh` | `Funcionario`, `Cargo` |
| `modulocrm` | `Lead`, `Oportunidade`, `Conta` |

> Registros filhos (ex: `CobrancaCliente`, `DocumentoDiario`) seguem o pai — se o pai vai para
> o lixo, os filhos também; se o pai é restaurado, os filhos são restaurados juntos (o payload
> inclui os filhos serializados).

---

## 9. Considerações de segurança e LGPD

- **Dados PII em repouso no lixo:** o payload JSON pode conter CPF, dados bancários, etc.
  Aplicar a mesma política de mascaramento da Fase 9 (RBAC de campo) ao visualizar payloads.
- **Retenção e LGPD:** o direito ao esquecimento (art. 18 LGPD) exige que dados pessoais
  sejam purgados quando solicitado. O `auto_purge` com `retencao_dias` deve respeitar
  prazos legais. A implementação definitiva de retenção LGPD está na **Fase 9**.
- **Auditoria imutável:** as colunas `deleted_at/by`, `restored_at/by`, `purged_at/by`
  nunca devem ser editadas — somente `INSERT`. O endpoint de mover deve ser idempotente:
  se o `objeto_id` já está no lixo (não purgado), retornar `409`.

---

## 10. Sequência de implementação

A implementação acontece **após** os módulos de negócio estarem construídos:

```
Fase C (módulos core) completa
  ↓
Criar app Django 'lixo' com modelos Lixo + ConfiguracaoLixo
  ↓
Adicionar role 'gestor_lixo' na IAM + RequireRole no backend
  ↓
Endpoint POST /api/lixo/mover/ + wiring nos ViewSets de cada módulo
  ↓
Endpoints restaurar + purgar
  ↓
Celery task auto_purge_lixo
  ↓
Frontend: tela /app/lixo (gestor_lixo)
  ↓
Configuração de retenção (UI + API)
  ↓
Testes E2E: phase_lixo_test.py
```
