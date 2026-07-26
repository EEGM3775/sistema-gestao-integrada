# Build de produção do shell React (app) servido por nginx.
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
# `npm run build` = `tsc -b && vite build`. Era `npx vite build` puro, e o
# comentário original explicava por quê: o shell tinha erro de tipo demais. Só
# que o esbuild do Vite transpila SEM type-check — com o CI marcando o build como
# informativo (D27), erro de tipo não aparecia em lugar nenhum da esteira, e foi
# assim que o SIL v2 subiu com 10 erros de contrato entre backend e front. Zerados
# em 26/07/2026, o type-check voltou para o caminho que todo mundo percorre.
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
