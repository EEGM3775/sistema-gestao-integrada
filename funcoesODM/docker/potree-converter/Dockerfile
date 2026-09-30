FROM node:18-alpine

RUN apk add --no-cache curl unzip libstdc++ libgcc

WORKDIR /app

# Download PotreeConverter 2.1.1 Linux binary (nome correto do arquivo)
RUN curl -fsSL -o potree.zip \
    "https://github.com/potree/PotreeConverter/releases/download/2.1.1/PotreeConverter_2.1.1_x64_linux.zip" \
    && unzip potree.zip \
    && cp PotreeConverter_linux_x64/PotreeConverter ./PotreeConverter \
    && cp PotreeConverter_linux_x64/liblaszip.so ./liblaszip.so \
    && chmod +x PotreeConverter \
    && rm -rf potree.zip PotreeConverter_linux_x64

# liblaszip.so precisa estar no LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH=/app

COPY package.json .
RUN npm install --omit=dev

COPY server.js .

ENV NODEODM_DATA=/nodeodm/data
ENV POTREE_OUTPUT=/potree/data
ENV PORT=5001

EXPOSE 5001
CMD ["node", "server.js"]
