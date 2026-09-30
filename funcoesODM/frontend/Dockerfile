# Stage 1: Build Angular application
FROM node:18-alpine AS build
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (use npm install to update lock file if needed)
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build for production
RUN npm run build -- --configuration=production

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built assets from build stage.
# Servidos sob /drone/ (base href = /drone/) para integrar com o gateway (Fase 2)
# e funcionar standalone (redirect / -> /drone/). Subpasta 'drone' alinha o
# caminho da URL ao filesystem, evitando armadilhas de alias/regex no nginx.
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html/drone

# Copy custom nginx config (will be overwritten by volume mount in docker-compose)
COPY nginx.conf /etc/nginx/nginx.conf

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
