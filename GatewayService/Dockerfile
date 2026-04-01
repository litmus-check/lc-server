FROM node:20-alpine

WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY gateway_logic.js ./
COPY .env ./
EXPOSE 8080
CMD ["node", "gateway_logic.js"]