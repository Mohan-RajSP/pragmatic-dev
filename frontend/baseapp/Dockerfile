# syntax=docker/dockerfile:1

# ---- Stage 1: build the static bundle with webpack ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY tsconfig.json webpack.config.js tailwind.config.js postcss.config.js ./
COPY src ./src
RUN npm run build

# ---- Stage 2: serve the built bundle with Express ----
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Install only production deps (express); build tools are devDependencies.
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./
COPY --from=build /app/dist ./dist

EXPOSE 9000
CMD ["node", "server.js"]

