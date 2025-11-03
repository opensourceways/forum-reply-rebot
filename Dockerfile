# 使用官方Python运行时作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 创建普通用户（按照指定方式配置）
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /sbin/nologin appuser

# 添加 umask 设置以增强安全性
RUN echo "umask 0027" >> /etc/bashrc

RUN echo "set +o history" >> /etc/bashrc

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /etc/apt/sources.list.d/*

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN rm -rf /etc/alternatives/cpp \
    /usr/bin/ar \
    /usr/bin/cpp \
    /usr/bin/gcc \
    /usr/bin/ld \
    /usr/bin/objdump \
    /usr/bin/readelf \
    /usr/bin/rpcgen \
    /usr/lib/apt/methods/mirror \
    /usr/lib/compat-ld/ld \
    /usr/lib/cpp \
    /usr/lib/gcc \
    /usr/libexec/gcc \
    /usr/share/bug/binutils \
    /usr/share/doc/binutils \
    /usr/share/doc/binutils/ld \
    /usr/share/doc/cpp \
    /usr/share/doc/gcc \
    /usr/share/doc/gcc-14-base/gcc \
    /usr/share/gcc \
    /usr/share/gdb \
    /var/lib/dpkg/alternatives/cpp \
    && rm -f /usr/local/lib/python3.9/bdb.py \
    /usr/local/lib/python3.9/pdb.py \
    /usr/local/lib/python3.9/timeit.py \
    /usr/local/lib/python3.9/trace.py \
    /usr/local/lib/python3.9/tracemalloc.py

# 移除 dpkg 相关配置，防止包管理操作
RUN rm -rf /var/lib/dpkg/triggers/Lock \
    /var/cache/debconf/* \
    /var/log/apt/* \
    && find /usr/bin -name "*dpkg*" -delete 2>/dev/null || true \
    && find /usr/sbin -name "*dpkg*" -delete 2>/dev/null || true

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p data/forum_data logs lightrag_data/rag_data && \
    rm -f /app/logs/*.log* 2>/dev/null || true && \
    chown -R appuser:appuser /app

RUN chmod -R 750 /app && \
    chmod -R 700 /app/config && \
    chmod -R 600 /app/config/config.yaml && \
    chmod -R 700 /app/data && \
    chmod -R 700 /app/data/forum_data && \
    find /app/data/forum_data -type f -exec chmod 600 {} \; && \
    rm -rf /app/data/forum_data/lost+found

# 切换到普通用户
USER appuser

# 暴露端口（Flask应用需要监听端口提供健康检查服务）
EXPOSE 5000

# 设置启动命令
CMD ["python", "main.py"]
