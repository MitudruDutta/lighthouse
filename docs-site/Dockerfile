FROM oven/bun:1.3.11 AS packages
WORKDIR /srv/docs
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM node:22-slim AS build
WORKDIR /srv/docs
COPY --from=packages /srv/docs/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_MEMORY_CONSOLE_URL=http://localhost:3003
ENV NEXT_PUBLIC_MEMORY_CONSOLE_URL=$NEXT_PUBLIC_MEMORY_CONSOLE_URL
RUN node scripts/search-index.mjs && node_modules/.bin/next build

# Only what the server needs: the standalone build traces its own node_modules.
FROM node:22-slim
WORKDIR /srv/docs
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3002
COPY --from=build --chown=node /srv/docs/.next/standalone ./
COPY --from=build --chown=node /srv/docs/.next/static ./.next/static
USER node
EXPOSE 3002
CMD ["node", "server.js"]
