FROM node:18-slim

# Install dependencies for Playwright (Chromium) and Python for canvas compilation
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxkbcommon0 \
    libasound2 \
    libx11-xcb1 \
    libxshmfence1 \
    # Python and build tools for canvas compilation
    python3 \
    python3-pip \
    build-essential \
    pkg-config \
    libcairo2-dev \
    libpango1.0-dev \
    libjpeg-dev \
    libgif-dev \
    librsvg2-dev \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package definition files first for caching optimization
COPY package*.json ./
COPY tsconfig.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Install Playwright dependencies
RUN npx playwright install --with-deps

# Install Edge browser only on x86_64 architecture
RUN if [ "$(uname -m)" = "x86_64" ]; then npx playwright install msedge; fi

# Copy source code
COPY src/ ./src/

# Copy .env file
COPY .env ./.env

# Copy LLM prompts to dist folder
RUN mkdir -p ./dist/LLM/prompts
COPY src/LLM/prompts/ ./dist/LLM/prompts/

# Build the TypeScript code
RUN npm run build

# Copy websocket-server.js to dist/ so it's available at runtime
RUN cp src/websocket-server.js dist/websocket-server.js

# Default command
CMD ["node", "dist/index.js"]
