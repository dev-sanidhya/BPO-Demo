# Bundles JsSIP + its transitive deps into a single self-contained file at
# build time. JsSIP hasn't shipped a pre-bundled browser file since ~v3.5 —
# every recent version expects a bundler — and loading it from a CDN at
# runtime turned out to be genuinely unreliable (confirmed broken by an ad
# blocker/network policy in a real browser, not just this sandbox). Bundling
# it here means agent-ui has zero runtime dependency on any external host.
FROM node:20-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY app.js /usr/share/nginx/html/app.js
COPY --from=build /build/vendor/jssip.bundle.js /usr/share/nginx/html/vendor/jssip.bundle.js
EXPOSE 80
