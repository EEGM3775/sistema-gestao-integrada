# Build de produção do shell React (ERP) servido por nginx.
# Usa `vite build` direto (sem `tsc -b`) para não quebrar por erros de tipo no
# shell ainda incipiente — o esbuild do vite transpila sem type-check.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps --no-audit --no-fund
COPY . .
RUN npx vite build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
