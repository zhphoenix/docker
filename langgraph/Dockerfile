FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY agent/ .

# 暴露端口
EXPOSE 8100

# 启动
CMD ["python", "main.py"]
