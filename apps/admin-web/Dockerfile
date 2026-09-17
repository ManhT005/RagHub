FROM node:24.12.0-alpine AS build
WORKDIR /src/admin-web
COPY admin-web/package*.json ./
RUN npm ci
COPY admin-web/ ./
COPY chat-widget/ /src/chat-widget/
RUN npm run build
FROM nginx:1.28.0-alpine
COPY --from=build /src/admin-web/dist/admin/browser /usr/share/nginx/html
COPY admin-web/nginx.conf /etc/nginx/conf.d/default.conf
