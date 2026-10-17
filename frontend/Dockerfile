# The screen. It reads the API from the server, at LIGHTHOUSE_API. Bun installs the
# packages from bun.lock; Next.js builds and runs on Node.
FROM oven/bun:1.3.11 AS packages
WORKDIR /srv/frontend
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM node:22-slim AS build
WORKDIR /srv/frontend
COPY --from=packages /srv/frontend/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL=http://localhost:3002
ENV NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL=$NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL
ARG NEXT_PUBLIC_LIGHTHOUSE_MEMORY_URL=http://localhost:3003
ENV NEXT_PUBLIC_LIGHTHOUSE_MEMORY_URL=$NEXT_PUBLIC_LIGHTHOUSE_MEMORY_URL
RUN node_modules/.bin/next build

# Only what the server needs: the standalone build traces its own node_modules.
FROM node:22-slim
WORKDIR /srv/frontend
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node /srv/frontend/.next/standalone ./
COPY --from=build --chown=node /srv/frontend/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
