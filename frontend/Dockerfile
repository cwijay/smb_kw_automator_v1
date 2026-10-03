FROM node:22-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG KEEL_API_URL=http://api:8000
ENV KEEL_API_URL=$KEEL_API_URL
RUN pnpm build

FROM node:22-slim
RUN corepack enable
WORKDIR /app
COPY --from=build /app ./
EXPOSE 3000
CMD ["pnpm", "start", "-p", "3000"]
