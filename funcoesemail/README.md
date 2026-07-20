# funcoesemail — e-mail da plataforma

Pasta única onde mora **o texto de todo e-mail** que o sistema envia.

## Mudar o texto de um e-mail

Edite o `.txt` em [templates/](templates/). É texto puro, com `{{ variavel }}` nos
trechos que mudam. Nenhum código precisa ser tocado — mas a alteração exige deploy
(o texto é versionado em git, e é assim de propósito nos e-mails de segurança).

## Criar um e-mail novo

1. Crie o `.txt` em `templates/<area>/`.
2. Registre a chave em [mensagens.py](mensagens.py).
3. Chame de qualquer serviço:

```python
from funcoesemail import enviar

enviar("crm.lembrete_tarefa", "cliente@empresa.com", {"nome": "Maria", "dias": 3})
```

## Por que é um pacote na raiz, e não um app Django

IAM e backend são **serviços separados**. Um app do backend não é importável pela
IAM, e fazer a IAM pedir envio ao backend por HTTP quebraria a garantia de que
**recuperação de senha funciona mesmo com o backend fora do ar** — que é também
como Entra ID, WSO2 e ForgeRock operam. Centraliza-se o texto; cada serviço
entrega pelo SMTP que configurou (em produção, ambos no mesmo provedor).

## Quem já usa

| Chave | Origem | Quando dispara |
|---|---|---|
| `identidade.*` (6) | IAM | recuperação/troca de senha, troca de e-mail, mudança de acessos |
| `crm.lembrete_tarefa` | backend (beat) | tarefa do CRM vencendo em 24h |
| `calendario.lembrete_evento` | backend (beat) | lembrete de evento, junto do aviso in-app |

**Não há mais nenhum `send_mail` fora deste pacote** — a verificação é
`grep -rn "send_mail" --include="*.py" backend/ iam/`.

## O que ainda não faz

Fila/retry próprios, log de entrega em banco, canal in-app ou WhatsApp,
preferência de canal por usuário, e edição de texto por tela (sem deploy). O
gancho para o último já existe: `render.carregar_fonte` é o único ponto que
precisa mudar para buscar o texto no banco.

## Configuração

Cada serviço entrega pelo **próprio** SMTP (`MAIL_HOST`, `MAIL_PORT`, …). Sem
`MAIL_HOST` o envio é no-op e fica registrado em WARNING no log — para a IAM,
fora de `IAM_DEBUG`, a variável é obrigatória e o serviço recusa subir sem ela.

Em dev/staging todos apontam para o **Mailpit** (`:8025`), que captura e não
entrega a ninguém. Atenção à porta **1025**: ela não oferece STARTTLS, e é por
isso que `EMAIL_USE_TLS` a exclui explicitamente nos dois settings — foi a causa
do achado **D20**.
