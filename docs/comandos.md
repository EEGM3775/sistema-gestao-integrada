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

    Os TRÊS, sempre — eles compartilham a mesma imagem. Rebuildar só o
    "erp" deixa o worker com o código velho, e o efeito é traiçoeiro:
    a tela responde certo (202, "estamos processando") e o trabalho de
    fundo simplesmente nunca acontece, sem erro em lugar nenhum.
    Foi o D25 em pendencias.md.

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
    docker compose exec -T iam python manage.py shell < testes/seeds/seed_demo.py

 2) Empreendimentos, obras, clientes, RH, eventos:
    docker compose exec -T erp python manage.py shell < testes/seeds/seed_demo_data.py

 O seed NÃO cria boletos, notas fiscais nem contas a pagar/receber —
 esses nascem de você usar o sistema (e dependem de Asaas / NFE.io).

 3) OPCIONAL — carteira grande, para ver a grade de clientes com volume
    (5000 clientes, suas quadras/lotes e um carnê com atrasos distribuídos):

    docker compose exec erp python manage.py semear_carteira_demo --clientes 5000
    docker compose exec erp python manage.py completar_enderecos_demo   # endereços reais (ViaCEP/OSM) — sem eles, NFS-e e CNAB recusam

    Só dev/staging. É idempotente (repetir não duplica) e aceita
    --tenant, --empreendimentos e --semente.


 4) OPCIONAL — o PDCA com obra planejada e em execução, para ver os postos
    com dado real em vez de tela vazia. Dois comandos, nesta ordem:

    docker compose exec erp python manage.py semear_pdca_demo --tenant demo --obra 9
    docker compose exec erp python manage.py semear_pdca_execucao --tenant demo

    O primeiro planeja UMA obra (locais, expediente, WBS, avanço apontado) e
    exige que ela tenha etapas e orcamento aprovado. O segundo semeia o resto
    do ciclo em TODAS as obras reais que ja tem plano: contrato e medicoes,
    restricoes, tres semanas de Last Planner com PPC, fichas de verificacao e
    nao-conformidades nas quatro faixas da fila, DDS e ocorrencias com CAT.

    Ele pula as obras de teste automatizado (E2E, REPRO, PROBE, VIS) e as que
    ja tem contrato — para nao passar por cima de dado seu. --limpar refaz.

    A semana corrente sai com DOIS donos: metade dos cartoes no rotulo que o
    escritorio usa ("Encarregado da frente") e metade no nome do usuario
    `campo`. E o que faz a tela do canteiro (/campo) abrir com frente de
    verdade em vez de vazia — ela procura o que esta no nome de quem entrou.

    So dev/staging. Nao aprova medicao (aprovar gera titulo no ERP) e nao
    inventa homem-hora: as taxas de SSMA seguem nulas, com motivo.


============================================================
 STAGING — o ambiente igual ao de produção
============================================================
Serve para testar como vai se comportar de verdade: HTTPS, senhas
seguras, sessão real. Fica em portas separadas e não mexe no dev.

 LIGAR (monta as imagens e sobe)
    bash infra/staging/up.sh

 CRIAR OS DADOS DE DEMONSTRAÇÃO (só na 1ª vez ou após apagar o banco)
    bash testes/seeds/seed_staging.sh

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
    admin     / admin123       -> administrador DO TENANT (papéis, usuários, auditoria)
    acme      / acme123        -> outra empresa (testar isolamento de dados)
    dono      / dono123        -> DONO DA PLATAFORMA (is_platform_admin)

    A diferenca entre `admin` e `dono` importa, e sao dois eixos:

      * o `admin` manda em tudo DENTRO da empresa dele -- e para no que ela
        assinou: modulo nao contratado fica fechado para ele tambem;
      * o `dono` alcanca TODO modulo do catalogo, contratado ou nao (ele e o
        teste supremo do sistema), e opera o que vale para TODAS as empresas:
        carregar a base SINAPI (ORC.8), confirmar incidente ANPD, publicar
        base-mae pelo impexp. O `admin`, mesmo com o catalogo inteiro de
        permissoes, recebe 403 nessas tres.

    O que o `dono` NAO faz: atravessar a fronteira de tenant. Ele le a empresa
    onde esta, como qualquer um -- nao e chave mestra. E plano/quota nao
    aparecem no hub dele: assunto de cliente nao e dele. Ver
    docs/acesso-e-permissoes.md.

    ONDE FICA A CARGA DA BASE: menu lateral -> SISTEMA -> Bases oficiais
    (/app/sistema/bases). A secao SISTEMA so existe para o `dono` -- para os
    demais ela nao aparece nem trancada, de proposito.


============================================================
 TESTES AUTOMATIZADOS
============================================================

 Os testes moram em testes/ (raiz do repositório) e NÃO vão para a
 imagem. Antes de rodar dentro do contêiner, copie a pasta para lá:
    docker exec sgi-erp mkdir -p /app/testes
    docker cp testes/. sgi-erp:/app/testes/
    (para a IAM, o mesmo com sgi-iam)

 Backend (Python) — a bateria completa:
    docker exec sgi-erp python manage.py test --noinput

 Só um módulo (mais rápido):
    docker exec sgi-erp python manage.py test moduloerp --noinput
    docker exec sgi-erp python manage.py test rh --noinput

 Login / IAM:
    docker exec sgi-iam python manage.py test --noinput

 Frontend — conferir erros de tipo (não altera nada):
    docker run --rm -v $PWD/frontend:/app -w /app node:22-alpine npx tsc -b --pretty false

 Testes de ponta a ponta (com o DEV ligado):
    python3 testes/e2e/phase4_e2e.py         (login e navegação geral)
    python3 testes/e2e/phase6_rbac_test.py   (permissões)
    python3 testes/e2e/phase8_tenancy_test.py (isolamento entre empresas)
    python3 testes/e2e/phase9_auditoria_test.py (trilha de auditoria)


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
 CARREGAR A TABELA SINAPI
------------------------------------------------------------
O Orcamento precisa da tabela de precos da Caixa. Ha DOIS caminhos, e o
que decide qual usar e o MES da publicacao:

 * 01/2025 EM DIANTE -- pelo botao (ORC.8). A Caixa publica um ZIP
   nacional so, com as 27 UFs em colunas, e o sistema le esse arquivo
   sozinho: um clique rende as 54 publicacoes do mes.
   Onde: http://localhost:8090 -> menu lateral SISTEMA -> Bases oficiais.
   A secao SISTEMA so aparece para o dono da plataforma
   (is_platform_admin) -- para os outros ela nao existe, nem trancada.
   (Ate 22/08/2026 o painel morava em Orcamento -> Bases & bancos; saiu
   de la porque base-mae e dado de plataforma, nao do modulo.)

   Da primeira vez, cadastre o endereco: botao "Endereco da fonte" ->
   cole o template da URL do pacote (aceita {ano_mes}, {ano}, {mes}).
   Sem template, nada e baixado -- de proposito: um job que adivinha
   endereco e um job que um dia importa dado errado com a confianca de
   um robo. O envio manual do arquivo (botao "Enviar o arquivo")
   continua valendo sempre, e e o plano B do mes em que a Caixa mudar
   o layout ou o WAF apertar.

   Pela bancada, quando o Celery ou o gateway estiverem fora:
   docker exec sgi-erp python manage.py carregar_base_oficial \
     --fonte sinapi --mes 2026-07
   (acrescente --resumo para so conferir, sem gravar; ou
    --arquivo /tmp/pacote.zip para o plano B)

------------------------------------------------------------
 CARREGAR A TABELA DA EMBASA (saneamento -- BA)
------------------------------------------------------------
A EMBASA publica em PDF e por SEMESTRE, nao por mes -- e nao publica
UM arquivo: sao 65 tabelas por semestre (expansao, operacao de agua e
de esgoto, cada uma pela convencao coletiva da regiao) mais a lista de
insumos. Nenhuma delas e "a do mes", entao a carga e POR ESCOLHA.

Pela tela: SISTEMA -> Bases oficiais -> fonte EMBASA. Aparece uma caixa
"Tabela" com a lista que o site publica; escolha e clique em Carregar.
O endereco ja vem cadastrado (e a pagina do semestre -- quando a EMBASA
abrir o proximo, e essa URL que muda, em "Endereco da fonte").

Pela bancada:
  # ver o que o semestre publicou
  docker exec sgi-erp python manage.py carregar_base_oficial \
    --fonte embasa --listar

  # carregar uma tabela (o slug vem do --listar)
  docker exec sgi-erp python manage.py carregar_base_oficial \
    --fonte embasa \
    --documento 1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2

  # carregar TODAS, uma corrida por documento
  docker exec sgi-erp python manage.py carregar_base_oficial \
    --fonte embasa --todas

--todas e de bancada, e so de bancada: sao ~65 documentos de 6 MB, cerca
de uma hora entre download e leitura de PDF. Pela tela, cada documento e
uma corrida sua -- uma tabela que falhe nao derruba as outras.

A competencia NAO precisa ser informada: a data-base vale a do proprio
PDF ("Relatorio de Servicos Junho/2026"), porque publicacao de semestre
faz da competencia pedida um palpite.

Os PDFs de "Encargos Sociais" aparecem na lista e NAO sao carregaveis:
eles sao a memoria de calculo das leis sociais (quadro de encargos do
ORC.7), nao base de preco.

 * ATE 12/2024 -- pelo comando abaixo. Aquelas publicacoes sao um ZIP
   por UF x regime, em formato "longo" (uma linha por item, uma coluna
   de preco), que o motor da carga nao le. Leva uns 10 segundos.

1) BAIXAR o pacote no site da Caixa, pelo NAVEGADOR:
   https://www.caixa.gov.br/site/Paginas/downloads.aspx
   -> "SINAPI - Insumos e Composicoes" -> baixe o ZIP do mes.
   (Baixe pelo navegador mesmo. O site recusa download por script.)

2) DESCOMPACTAR e mandar os arquivos para dentro do sistema.
   Troque CAMINHO pela pasta onde voce descompactou:

   docker exec sgi-erp mkdir -p /tmp/sinapi
   docker cp "CAMINHO/SINAPI_Preco_Ref_Insumos_*.xlsx"          sgi-erp:/tmp/sinapi/insumos.xlsx
   docker cp "CAMINHO/SINAPI_Custo_Ref_Composicoes_Sintetico_*.xlsx" sgi-erp:/tmp/sinapi/sintetico.xlsx
   docker cp "CAMINHO/SINAPI_Custo_Ref_Composicoes_Analitico_*.xlsx" sgi-erp:/tmp/sinapi/analitico.xlsx

3) CONFERIR antes de gravar (--dry-run so conta, nao grava):
   Troque BA e 2024-10 pelo seu estado e mes.
   ATENCAO: "NaoDesonerado" = --regime onerado.

   docker exec sgi-erp python manage.py importar_base_referencial \
     --fonte sinapi --uf BA --mes 2024-10 --regime onerado \
     --insumos /tmp/sinapi/insumos.xlsx \
     --composicoes /tmp/sinapi/sintetico.xlsx \
     --analitica /tmp/sinapi/analitico.xlsx --dry-run

4) GRAVAR: o mesmo comando, SEM o --dry-run no final.

4b) SE RECUSAR com "NAO IMPORTADO -- N classe(s) ... sem traducao":
   nao e defeito. A publicacao usa palavras de classe que o sistema nao
   traduz em natureza, e ele para antes de gravar em vez de chutar.
   A propria mensagem lista quais sao e as duas saidas (declarar a
   traducao, ou --aceitar-sem-classe). Leia a mensagem: ela e o manual.

   Onde declarar e por que:
   backend/moduloorcamento/dados/classes/README.md

5) VER na tela: http://localhost:8090 -> Orcamento -> Bases & bancos.
   Clique no cartao da publicacao para a lista aparecer.
   O cartao avisa quando a publicacao nao classifica insumo, e diz quais
   palavras nao foram entendidas.

6) DEPOIS DE IMPORTAR: acertar a natureza dos itens ja adotados.
   A publicacao traz a coluna "Classificacao" (MATERIAL, MAO DE OBRA,
   EQUIPAMENTO, ENCARGOS COMPLEMENTARES...). Quem foi adotado antes disso
   pode estar com a natureza errada -- e natureza errada muda encargo
   social, ou seja, muda preco.

   Conferir primeiro (nao grava nada, so mostra o de-para):
   docker exec sgi-erp python manage.py reclassificar_itens_catalogo \
     --all-tenants --dry-run

   Aplicar: o mesmo comando SEM o --dry-run.
   Ele corrige o catalogo e refaz so os orcamentos EM RASCUNHO.
   Aprovado nao se mexe (e regua de medicao); a proxima revisao dele ja
   nasce certa. Linha com preco digitado a mao mantem o preco -- o
   comando corrige a categoria e avisa no relatorio.

   SE a publicacao for ANTERIOR a 01/2025, o relatorio dira "Sem
   classificacao na fonte: N item(ns)" -- ela nao traz a coluna, e a
   natureza saiu da unidade. Para classificar a mao so o que importa:

   docker exec sgi-erp python manage.py reclassificar_itens_catalogo \
     --all-tenants --dry-run \
     --de-para moduloorcamento/dados/classificacao-sinapi-ba-2024-10.csv

   (esse arquivo e o exemplo pronto da SINAPI BA 10/2024)

   NAO confundir os dois arquivos:
   - dados/classes/<fonte>.csv -> por CLASSE, vale para a fonte toda
   - --de-para arquivo.csv     -> por CODIGO, vale para item ja adotado

   O desenho dos dois esta na planta:
   docs/modulos/moduloorcamento.md

Reimportar o mesmo mes NAO duplica: atualiza o preco.
CUIDADO: hoje o --dry-run ja cria a publicacao vazia (achado A15). Se
uma publicacao com 0 itens aparecer na lista, foi isso; rodar o comando
de verdade a preenche.

------------------------------------------------------------
 ANOTAÇÕES (coisas que já deram trabalho)
------------------------------------------------------------
- Frontend: o SPA e assado na imagem. "docker cp" de uma pasta para um
  destino que JA EXISTE aninha (vira assets/assets) e o site quebra com
  404 no bundle. Apague o destino antes: rm -rf .../assets && docker cp.
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
