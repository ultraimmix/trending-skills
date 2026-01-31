# 使用 Playwright 官方镜像（已包含浏览器和依赖）
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN uv pip install --system -r requirements.txt

# 复制项目代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 运行主程序
CMD ["python", "src/main_trending.py"]
