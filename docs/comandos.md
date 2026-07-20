============================================================
 COMANDOS PARA RODAR E TESTAR O SISTEMA
 Guia prático. Siga na ordem. Atualizado em 18/07/2026.
============================================================

Tudo roda dentro do Docker. Você não instala banco, Python nem Node à
mão. Sempre que disser "digite", é escrever no terminal e apertar ENTER.

REGRA DE OURO: o Docker Desktop (baleia azul) precisa estar ABERTO.
Metade dos problemas é ele fechado.

Abra o "Ubuntu" (menu Iniciar) e SEMPRE comece entrando na pasta:

    cd /home/eegm/projetos/02sistema_gestao_integrada


============================================================
 EXISTEM DOIS AMBIENTES — e eles servem para coisas diferentes
============================================================

                    DEV                      STAGING
 Endereço           http://localhost:8090    https://localhost:8443
 Como liga          docker compose ...       bash infra/staging/up.sh
 Modo               desenvolvimento          PRODUÇÃO (DEBUG desligado)
 HTTPS              não                      sim (certificado local)
 Asaas / NFE.io     credenciais PREENCHIDAS  credenciais VAZIAS
 Dados financeiros  seus boletos e NFs       nenhum (só o seed)

Os dois podem ficar ligados ao mesmo tempo — usam portas e bancos
separados, não se atrapalham.

>> ONDE TESTAR O QUÊ (isto evita perder tempo):

  - Boletos, Asaas, Nota Fiscal, contas a pagar/receber ... use o DEV.
    Só ele tem as credenciais e os dados que você já gerou.

  - Login, sessão, expiração, cookie seguro, HTTPS ......... use o STAGING.
    Só ele roda em modo produção com HTTPS, que é o que torna o teste
    de sessão fiel ao mundo real.

  - Qualquer outra tela (obras, clientes, RH, CRM, diário) ... tanto faz.


============================================================
 DEV — o do dia a dia
============================================================

 LIGAR
    docker compose --profile full up -d

    Na primeira vez demora (pode passar de 10 min). Depois é rápido.
    Espere de 30 a 60 segundos para o sistema "acordar" por completo.

 ABRIR NO NAVEGADOR
    http://localhost:8090

 VER SE ESTÁ TUDO NO AR
    docker compose --profile full ps
    (todos devem estar "Up"; vários dizem "healthy")

 DESLIGAR (mantém seus dados)
    docker compose --profile full down --remove-orphans

 APAGAR TUDO E COMEÇAR DO ZERO  ⚠️ apaga banco e uploads
    docker compose --profile full down -v --remove-orphans
    (depois é preciso ligar e rodar os seeds de novo — veja abaixo)


------------------------------------------------------------
 MUDEI O CÓDIGO E QUERO VER A MUDANÇA (rebuild)
------------------------------------------------------------
Ligar de novo NÃO basta: é preciso remontar a imagem do serviço que
mudou. Rebuild só do que mudou é bem mais rápido que rebuildar tudo.

 Mudou tela / React (pasta frontend/):
    docker compose --profile full up -d --build react

 Mudou backend Python (pasta backend/):
    docker compose --profile full up -d --build erp worker beat

 Mudou login / IAM (pasta iam/):
    docker compose --profile full up -d --build iam

 Mudou o drone (Java):
    docker compose --profile full up -d --build java-service

 Mudou TUDO / na dúvida (demora mais):
    docker compose --profile full up -d --build

Depois do rebuild, no navegador aperte Ctrl+Shift+R (limpa o cache).
Sem isso o navegador mostra a tela antiga e parece que não funcionou.

⚠️ Mudou arquivo de CONFIGURAÇÃO montado no container (ex.: nginx.conf)?
   Rebuild não resolve — tem que RECRIAR o container:
      docker compose --profile full up -d --force-recreate gateway


------------------------------------------------------------
 CRIAR OS DADOS DE DEMONSTRAÇÃO (após apagar o banco)
------------------------------------------------------------
Rode os DOIS, nesta ordem. Pode repetir sem medo — não duplica.

 1) Usuários e permissões:
    docker compose exec -T iam python manage.py shell < iam/seed_demo.py

 2) Empreendimentos, obras, clientes, RH, eventos:
    docker compose exec -T erp python manage.py shell < backend/seed_demo_data.py

 O seed NÃO cria boletos, notas fiscais nem contas a pagar/receber —
 esses nascem de você usar o sistema (e dependem de Asaas / NFE.io).


============================================================
 STAGING — o ambiente igual ao de produção
============================================================
Serve para testar como vai se comportar de verdade: HTTPS, senhas
seguras, sessão real. Fica em portas separadas e não mexe no dev.

 LIGAR (monta as imagens e sobe)
    bash infra/staging/up.sh

 CRIAR OS DADOS DE DEMONSTRAÇÃO (só na 1ª vez ou após apagar o banco)
    bash infra/staging/seed.sh

 ABRIR NO NAVEGADOR
    https://localhost:8443

    O navegador vai avisar "Sua conexão não é privada". É ESPERADO:
    o certificado é local, feito aqui na máquina, e nenhuma autoridade
    o assinou. Clique em "Avançado" > "Ir para localhost (não seguro)".
    Se o Chrome não mostrar a opção, clique na página e digite:
       thisisunsafe
    (não aparece nada enquanto digita — ele libera sozinho)

 CONFERIR QUE ESTÁ TUDO CERTO (roda a bateria de testes automáticos)
    bash infra/staging/validate.sh
    (deve terminar com "6 verde / 0 vermelho")

 DESLIGAR (mantém os dados)
    bash infra/staging/down.sh

 DESLIGAR E APAGAR O BANCO  ⚠️
    bash infra/staging/down.sh -v
    (depois: up.sh e seed.sh de novo)


============================================================
 LOGINS DE TESTE (valem nos dois ambientes)
============================================================
    demo      / demo123        -> vê tudo (todos os módulos)
    semdrone  / semdrone123    -> acesso restrito (bom p/ testar bloqueios)
    admin     / admin123       -> administrador (papéis, usuários, auditoria)
    acme      / acme123        -> outra empresa (testar isolamento de dados)


============================================================
 TESTES AUTOMATIZADOS
============================================================

 Backend (Python) — a bateria completa:
    docker compose exec erp python manage.py test

 Só um módulo (mais rápido):
    docker compose exec erp python manage.py test moduloerp
    docker compose exec erp python manage.py test rh

 Login / IAM:
    docker compose exec iam python manage.py test identity

 Frontend — conferir erros de tipo (não altera nada):
    docker run --rm -v $PWD/frontend:/app -w /app node:22-alpine npx tsc -b --pretty false

 Testes de ponta a ponta (com o DEV ligado):
    python3 infra/gateway/phase4_e2e.py         (login e navegação geral)
    python3 infra/gateway/phase6_rbac_test.py   (permissões)
    python3 infra/gateway/phase8_tenancy_test.py (isolamento entre empresas)
    python3 infra/gateway/phase9_auditoria_test.py (trilha de auditoria)


============================================================
 ESPIAR O QUE ESTÁ ACONTECENDO
============================================================

 Ver o log de um serviço (Ctrl+C para sair):
    docker compose logs -f erp
    docker compose logs -f worker      (tarefas em segundo plano)
    docker compose logs -f gateway     (a "portaria")

 Ver os últimos erros do backend:
    docker compose logs erp --tail 50

 Contar o que existe no banco (dev):
    docker exec sgi-postgres psql -U postgres -d erp_db -c \
      "SELECT (SELECT count(*) FROM moduloerp_boleto) AS boletos,
              (SELECT count(*) FROM moduloerp_notafiscalservico) AS notas,
              (SELECT count(*) FROM clientes_cliente) AS clientes;"

 O mesmo no staging: troque "sgi-postgres" por "sgi-stg-postgres".


============================================================
 DEU PROBLEMA? Tente nesta ordem
============================================================
Antes de tudo: o Docker Desktop está ABERTO?

1) A página não abre, ou dá erro logo depois de ligar
   - Espere mais 1 minuto (o sistema leva tempo para acordar).
   - Ctrl+Shift+R no navegador.

2) Aparece 502 ou 500, ou a tela fica em branco
    docker compose --profile full up -d
   - Espere 40 segundos e recarregue com Ctrl+Shift+R.
   - Se persistir:
    docker compose restart gateway erp

3) Algum serviço aparece "Exited" no ps
    docker compose --profile full up -d
   - Se voltar a cair, veja o motivo:
    docker compose logs <nome-do-servico> --tail 40

4) "Mudei o código e não mudou nada na tela"
   - Faltou o REBUILD (veja a seção de rebuild acima).
   - Ou faltou Ctrl+Shift+R no navegador.

5) "O Asaas não está disponível" / não aparece boleto nem nota fiscal
   - Você está no STAGING. Ele não tem credenciais nem esses dados.
     Use o DEV (http://localhost:8090) para esses testes.

6) Login some sozinho / cai a sessão
   - No STAGING isso é o esperado: a sessão dura 2 horas sem atividade
     (ou 7 dias se marcar "manter conectado"), e avisa 15 min antes.


------------------------------------------------------------
 ANOTAÇÕES (coisas que já deram trabalho)
------------------------------------------------------------
- Bind-mount órfão do gateway: editar a conf trocou o inode e o Docker
  Desktop deixou o container preso ao inode antigo -> gateway caiu
  (exit 127). Corrigido recriando o container. Conf de container montada
  exige "up --force-recreate", não basta "nginx -s reload".


============================================================
 RESUMO — decore só estes
============================================================
   LIGAR (dev):     docker compose --profile full up -d
   ABRIR (dev):     http://localhost:8090      demo / demo123
   REBUILD tela:    docker compose --profile full up -d --build react
   DESLIGAR (dev):  docker compose --profile full down

   LIGAR staging:   bash infra/staging/up.sh
   ABRIR staging:   https://localhost:8443
   DESLIGAR:        bash infra/staging/down.sh

Guia técnico completo, para desenvolvedores: docs/desenvolvimento.md
