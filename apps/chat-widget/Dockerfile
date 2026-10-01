FROM node:24.12.0-alpine3.22 AS build
WORKDIR /app
RUN npm install --global typescript@5.9.3
COPY tsconfig.json ./
COPY src ./src
RUN tsc -p tsconfig.json
FROM nginx:1.29.1-alpine3.22
COPY --from=build /app/dist/raghub.js /usr/share/nginx/html/raghub.js
