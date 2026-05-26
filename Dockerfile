# Multi-stage build for HLSL TC57 website with Hugo and LaTeX

# Stage 1: Builder
FROM ubuntu:26.04 AS build

# Set environment variables
ENV HUGO_VERSION=0.148.1 \
    DEBIAN_FRONTEND=noninteractive \
    HUGO_ENVIRONMENT=production

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    npm \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Hugo extended and Pandoc for the container architecture
RUN arch=$(dpkg --print-architecture) \
    && case "$arch" in \
      amd64) HUGO_ARCH=amd64 PANDOC_ARCH=amd64 ;; \
      arm64|arm64v8) HUGO_ARCH=arm64 PANDOC_ARCH=arm64 ;; \
      aarch64) HUGO_ARCH=arm64 PANDOC_ARCH=arm64 ;; \
      *) echo "Unsupported architecture: $arch" >&2 ; exit 1 ;; \
    esac \
    && wget -O /tmp/hugo.deb https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-${HUGO_ARCH}.deb \
    && dpkg -i /tmp/hugo.deb \
    && rm /tmp/hugo.deb

# Install Dart Sass
RUN npm install -g sass

# Set working directory
WORKDIR /workspace

# Copy the entire repository
COPY . .

# Install Node.js dependencies for the theme
RUN if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then npm ci; fi || true

# Build Hugo website
RUN  hugo \
    --minify \
    --baseURL "/"

# Stage 2: Runtime (optional - for serving the built site)
FROM nginx:alpine AS run

COPY --from=build /workspace/public /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
