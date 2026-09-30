# Configuração e Execução da Aplicação

Este guia descreve como configurar e executar a aplicação completa usando Docker Compose.

## Pré-requisitos

- Docker Desktop instalado e em execução
- WSL2 habilitado (no Windows)
- Node.js e Angular CLI instalados (para desenvolvimento do frontend)

## Passos de Configuração

### 1. Build do Frontend Angular

Navegue até o diretório do frontend e compile a aplicação:

```bash
cd /home/eegm/Metashape/funcoesODM/frontend
ng build
```

Isso criará os arquivos estáticos em `dist/frontend-app`, que serão servidos pelo Nginx.

### 2. Volte para a raiz do projeto

```bash
cd ..
```

### 3. Inicie todos os serviços com Docker Compose

Execute o seguinte comando para construir e iniciar todos os serviços:

```bash
docker compose up -d --build
```

 Este comando irá:
- Construir as imagens Docker para os serviços Java e Python
- Iniciar o Nginx (porta 8088)
- Iniciar o PostgreSQL (banco de dados principal)
 - Iniciar o NodeODM (processamento)
- Criar automaticamente as tabelas do banco de dados

### 4. Verifique se todos os serviços estão rodando

```bash
docker ps
```

Você deve ver os seguintes containers em execução:
- `nginx`
- `java-service`
- `db` (PostgreSQL)
 - `nodeodm`

### 5. Acesse a Aplicação

Abra seu navegador e navegue para:

```
http://localhost:8088
```

Você deverá ver a tela de login da aplicação.

---

## Registro e Login de Usuário

Como a aplicação inicia com o banco de dados vazio, você precisará registrar o primeiro usuário.

### 1. Registre um novo usuário via API

Use o comando `curl` abaixo (ou Postman/Insomnia):

```bash
curl -X POST \
  http://localhost:8088/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "EEGM",
    "password": "3775",
    "email": "test@example.com"
  }'
```

**Resposta esperada:**
```
User registered successfully!
```

### 2. Faça Login na aplicação

1. Acesse `http://localhost:8088` no navegador
2. Use as credenciais que você acabou de registrar:
   - **Username:** `EEGM`
   - **Password:** `3775`

---

## Troubleshooting

### Erro 502 Bad Gateway

Se você receber um erro 502 ao tentar registrar:

1. Verifique se o java-service está rodando:
   ```bash
   docker ps | grep java
   ```

2. Verifique os logs do java-service:
   ```bash
   docker compose logs java-service
   ```

3. Se você ver "ERROR: relation 'users' does not exist", reinicie o java-service:
   ```bash
   docker compose restart java-service
   ```

### NodeODM não inicia

Se o NodeODM falhar:

```bash
docker compose logs nodeodm
```

 ### NodeODM não está acessível
 
 Certifique-se de que o NodeODM está rodando:
 
 ```bash
 docker ps | grep nodeodm
 ```
 
 Se não estiver, inicie-o:
 
 ```bash
 docker compose up -d nodeodm
 ```

---

## Comandos Úteis

### Ver logs de um serviço específico
```bash
docker compose logs -f <service_name>
```

### Reiniciar um serviço
```bash
docker compose restart <service_name>
```

### Parar todos os serviços
```bash
docker compose down
```

### Reconstruir e reiniciar todos os serviços
```bash
docker compose up -d --build
```

### Limpar volumes (CUIDADO: apaga dados do banco)
```bash
docker compose down -v
```