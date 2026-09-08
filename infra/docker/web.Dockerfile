ARG NODE_BASE_IMAGE=node:24.18.0-bookworm-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d
ARG CADDY_BASE_IMAGE=caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d
FROM ${NODE_BASE_IMAGE} AS builder

WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm install --global npm@12.0.1
RUN npm ci --ignore-scripts
COPY apps/web ./apps/web
RUN npm run build --workspace @splitbind/web

FROM ${CADDY_BASE_IMAGE} AS runtime

RUN mkdir -p /data/caddy /config/caddy /srv/web \
    && chown -R 10002:10002 /data /config /srv/web
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=builder --chown=10002:10002 /src/apps/web/dist /srv/web

USER 10002:10002
EXPOSE 8080 8443
