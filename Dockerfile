# 使用官方Python镜像
FROM python:3.10-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 添加时间戳避免缓存，确保代码更新
ARG BUILD_DATE
ENV BUILD_DATE=${BUILD_DATE}

# 复制源代码文件
COPY futu_news_scraper.py .
COPY all_stocks_info.csv .

# 创建输出目录
RUN mkdir -p /etc/FUTUNews/output

# 设置权限
RUN chmod +x futu_news_scraper.py

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/etc/FUTUNews/output') else 1)"

# 默认运行测试模式
CMD ["python", "futu_news_scraper.py", "--mode", "test"]