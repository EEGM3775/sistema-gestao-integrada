# Domínio: GPU — FuncoesODM

> Cole junto com CONTEXT.md quando a sessão envolver aceleração GPU no NodeODM.

---

## Como funciona

O NodeODM usa NVIDIA CUDA para acelerar etapas de Structure-from-Motion e Dense Matching.  
A aceleração é configurada no `docker-compose.yml` e passada como opção de tarefa.

---

## Pré-requisitos

- GPU NVIDIA com suporte CUDA
- Driver NVIDIA instalado no host (Windows: driver Windows; WSL2: mesmo driver)
- NVIDIA Container Toolkit instalado (`nvidia-container-toolkit`)
- Docker configurado para usar runtime NVIDIA

---

## Configuração docker-compose.yml

```yaml
services:
  nodeodm:
    build: ./docker/nodeodm
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

---

## Verificação

```bash
# Verificar se GPU está disponível no container
docker exec nodeodm nvidia-smi

# Deve mostrar: driver version, CUDA version, GPU model e uso de memória
```

---

## Opção de tarefa

Ao criar uma tarefa NodeODM, passar:
```json
{ "use-gpu": true }
```

Ou via frontend: habilitar opção "Aceleração GPU" no formulário de criação de tarefa.

---

## Problemas comuns

| Sintoma | Causa provável | Fix |
|---------|---------------|-----|
| `nvidia-smi` falha dentro do container | Container Toolkit não configurado | Reinstalar `nvidia-container-toolkit`, reiniciar Docker |
| GPU visível mas sem aceleração | `use-gpu: false` na tarefa | Habilitar a opção ao criar a tarefa |
| Erro `CUDA out of memory` | GPU com VRAM insuficiente | Reduzir `pc-quality` ou `quality` da tarefa |
| Driver version mismatch | Driver host desatualizado | Atualizar driver NVIDIA |

---

**Guia completo (inclui Quick Start):** [guides/GPU_ACELERACAO.md](../guides/GPU_ACELERACAO.md)
