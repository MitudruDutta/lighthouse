FROM oven/bun:1.3.11 AS packages
WORKDIR /srv/docs
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM node:22-slim
WORKDIR /srv/docs
COPY --from=packages /srv/docs/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_MEMORY_CONSOLE_URL=http://localhost:3003
ENV NEXT_PUBLIC_MEMORY_CONSOLE_URL=$NEXT_PUBLIC_MEMORY_CONSOLE_URL
RUN node scripts/search-index.mjs && node_modules/.bin/next build
ENV NODE_ENV=production
USER node
EXPOSE 3002
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3002"]
