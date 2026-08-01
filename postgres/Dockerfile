# PostgreSQL 17 + pgvector + Apache AGE
# 自建镜像：完全可控的图数据库 + 向量数据库统一基础设施

FROM pgvector/pgvector:pg17

LABEL maintainer="ai-platform"
LABEL description="PostgreSQL 17 with pgvector and Apache AGE for AI Investment Research Platform"

# 编译 Apache AGE 所需依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libreadline-dev \
    zlib1g-dev \
    flex \
    bison \
    libxml2-dev \
    libxslt-dev \
    libssl-dev \
    libxml2-utils \
    xsltproc \
    ccache \
    pkg-config \
    git \
    postgresql-server-dev-17 \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 Apache AGE 1.7.0 (PG17 分支)
RUN git clone --branch release/PG17/1.7.0 --depth 1 \
    https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make install \
    && rm -rf /tmp/age

# 预加载 AGE（避免每次连接手动 LOAD）
RUN echo "shared_preload_libraries = 'age'" >> /usr/share/postgresql/postgresql.conf.sample
