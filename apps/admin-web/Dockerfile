FROM node:24.12.0-alpine3.22 AS dependencies

WORKDIR /repo/apps/admin-web
COPY apps/admin-web/package.json apps/admin-web/package-lock.json ./
RUN npm ci

FROM dependencies AS development

COPY apps/admin-web/ .
COPY assets/providers/ /repo/assets/providers/
COPY scripts/sync-provider-assets.mjs /repo/scripts/sync-provider-assets.mjs
EXPOSE 4200
CMD ["npm", "start", "--", "--poll=1000"]

FROM dependencies AS build

COPY apps/admin-web/ .
COPY assets/providers/ /repo/assets/providers/
COPY scripts/sync-provider-assets.mjs /repo/scripts/sync-provider-assets.mjs
RUN npm run build

FROM nginx:1.29.1-alpine3.22 AS runtime
COPY apps/admin-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/admin-web/dist/admin-web/browser /usr/share/nginx/html

EXPOSE 80
