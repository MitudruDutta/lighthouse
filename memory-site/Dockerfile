FROM oven/bun:1.3.11 AS packages
WORKDIR /srv/memory-site
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM node:22-slim AS build
WORKDIR /srv/memory-site
COPY --from=packages /srv/memory-site/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_MEMORY_DOCS_URL=http://localhost:3002
ENV NEXT_PUBLIC_MEMORY_DOCS_URL=$NEXT_PUBLIC_MEMORY_DOCS_URL
RUN node_modules/.bin/next build

# Only what the server needs: the standalone build traces its own node_modules.
FROM node:22-slim
WORKDIR /srv/memory-site
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3003
COPY --from=build --chown=node /srv/memory-site/.next/standalone ./
COPY --from=build --chown=node /srv/memory-site/.next/static ./.next/static
USER node
EXPOSE 3003
CMD ["node", "server.js"]
