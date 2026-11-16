# syntax=docker/dockerfile:1
#
# Static Next.js export served by unprivileged nginx (docs/aws-architecture.md §5).
# nginx also reverse-proxies /api/* to the backend Service, so the browser sees one origin
# (no CORS), and one image can be promoted unchanged from dev to staging to prod.
#
# Build:  docker build -t bceao-rag-web:<tag> web/
# Run:    docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 bceao-rag-web:<tag>

ARG NODE_VERSION=22

# ---------------------------------------------------------------------------
# build: npm ci + next build -> /app/out
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Relative path: lib/api.ts calls /api/query on the same origin, and nginx proxies it.
# This keeps environment-specific API hostnames out of the image.
ENV NEXT_PUBLIC_API_BASE_URL=/api \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------------------------------------------------------------------------
# runtime: nginx serving the static files, running as non-root on port 8080
# ---------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

# The official image runs envsubst over /etc/nginx/templates/*.template at startup and
# writes the result to /etc/nginx/conf.d/. API_UPSTREAM is the backend base URL:
# "http://api" is the `api` Service in the same Kubernetes namespace (port 80).
# Compose overrides it to http://api:8000.
ENV API_UPSTREAM=http://api \
    NGINX_ENVSUBST_FILTER=^API_UPSTREAM$

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/out /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1
