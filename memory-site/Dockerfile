FROM oven/bun:1.3.11 AS packages
WORKDIR /srv/memory-site
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM node:22-slim
WORKDIR /srv/memory-site
COPY --from=packages /srv/memory-site/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_MEMORY_DOCS_URL=http://localhost:3002
ENV NEXT_PUBLIC_MEMORY_DOCS_URL=$NEXT_PUBLIC_MEMORY_DOCS_URL
RUN node_modules/.bin/next build
ENV NODE_ENV=production
USER node
EXPOSE 3003
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3003"]
