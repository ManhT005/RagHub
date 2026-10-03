FROM node:24.12.0-alpine3.22 AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS development

COPY . .
EXPOSE 4200
CMD ["npm", "start", "--", "--poll=1000"]

FROM dependencies AS build

COPY . .
RUN npm run build

FROM nginx:1.29.1-alpine3.22 AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/admin-web/browser /usr/share/nginx/html

EXPOSE 80
