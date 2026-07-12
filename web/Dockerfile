# A-Cal Frontend — Next.js standalone production build
# Multi-stage: build → slim runtime image

# ---- Stage 1: Build ----
FROM node:20-slim AS builder

WORKDIR /app

# Enable pnpm via corepack
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package files for dependency caching
COPY package.json pnpm-lock.yaml* ./

RUN pnpm install --frozen-lockfile || pnpm install

# Copy the rest of the source
COPY . .

# Build the Next.js app
# The API proxy is configured via A_CAL_API_URL env at runtime via rewrites
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- Stage 2: Runtime ----
FROM node:20-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3456

# Copy the standalone build output
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

EXPOSE 3456

CMD ["npx", "next", "start", "--port", "3456"]
