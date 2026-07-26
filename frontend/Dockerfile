# Build de produção do shell React (app) servido por nginx.
# Usa `vite build` direto (sem `tsc -b`) para não quebrar por erros de tipo no
# shell ainda incipiente — o esbuild do vite transpila sem type-check.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# `npm ci` (Fase 10.4.1): instala EXATAMENTE o package-lock.json, e falha se o
# lock divergir do package.json. Era `npm install --legacy-peer-deps`, que
# reresolvia tudo e ignorava o lock — foi o que deixou o lock derivar sem os
# seis `@fullcalendar/*` por 7 dias: a imagem buildava e só o CI quebrava (F6).
# O `--legacy-peer-deps` era de um conflito de peer do `valibot`, que saiu do
# grafo quando o projeto passou a usar `zod`; sem ele o `npm ci` resolve limpo.
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx vite build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
