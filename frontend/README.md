# Frontend — shell React do SGI

Shell React 19 + Vite 7 + TypeScript + Tailwind 4 da plataforma. **A documentação vive em
[`docs/`](../docs/README.md)**:

- Planta (design system, páginas, rotas, camada de dados): [docs/frontend.md](../docs/frontend.md)
- **Convenções de código (leitura obrigatória)**: [docs/frontend-convencoes.md](../docs/frontend-convencoes.md)
- Como rodar (dev isolado e via Docker/gateway): [docs/desenvolvimento.md](../docs/desenvolvimento.md)
- Status por módulo: [docs/roadmap.md](../docs/roadmap.md)

```bash
npm install
npm run dev        # dev isolado (Vite)
```

Atrás do gateway (`http://localhost:8090`), o container precisa de rebuild a cada mudança — ver o
gotcha de cache em [docs/desenvolvimento.md](../docs/desenvolvimento.md#rebuild-do-frontend-react-gotcha-de-cache).
