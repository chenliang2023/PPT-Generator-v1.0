# Nginx 部署方案

本文档说明如何在服务器上为当前 PPT 服务增加一层 Nginx 反向代理。

适用场景：

- 你准备把服务部署到公网服务器
- 你希望通过域名访问服务
- 你希望后续接入 HTTPS
- 你不想直接把 `8000` 端口长期暴露给公网

当前服务本体仍然是：

- FastAPI
- Docker Compose
- 容器内监听 `8000`

Nginx 的作用是放在前面做代理层。

## 1. 推荐拓扑

推荐结构：

```text
浏览器 / 客户端
  -> Nginx
  -> 127.0.0.1:8000
  -> FastAPI 容器
```

也就是说：

- 外部流量先到 Nginx
- Nginx 再转发到本机的 `8000`
- FastAPI 容器不直接暴露给公网

## 2. 为什么要加 Nginx

直接暴露 `8000` 也能用，但不够稳。

加 Nginx 的好处：

- 可以绑定域名
- 可以配 HTTPS
- 可以隐藏后端端口
- 可以增加访问控制
- 以后可以同时挂前端页面和 API
- 更适合正式部署

## 3. 当前项目的现状

当前 [docker-compose.yml](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/docker-compose.yml>) 是：

```yaml
services:
  ppt-service:
    build:
      context: .
      dockerfile: server/Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - path: .env
        required: false
    volumes:
      - ./data:/data
    restart: unless-stopped
```

这表示：

- 宿主机 `8000` 端口会映射到容器 `8000`
- Nginx 可以直接代理到 `127.0.0.1:8000`

## 4. 推荐部署方式

推荐使用：

- Docker Compose 启动 PPT 服务
- 服务器系统层安装 Nginx
- Nginx 监听 `80` 或 `443`
- Nginx 反代到 `127.0.0.1:8000`

这是当前最简单、最稳的方案。

不建议第一版就做：

- Nginx 容器化并混在当前 compose 里
- 多层容器网络编排
- 复杂网关逻辑

先跑稳，再考虑把 Nginx 也容器化。

## 5. 服务器准备

假设服务器是 Ubuntu。

先安装 Nginx：

```bash
sudo apt update
sudo apt install -y nginx
```

确认 Nginx 启动：

```bash
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

## 6. 先启动 PPT 服务

先把你的 PPT 服务跑起来。

项目目录假设在：

```text
/opt/ppt-service
```

进入目录：

```bash
cd /opt/ppt-service
```

准备环境变量：

```bash
cp .env.example .env
nano .env
```

至少填：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
API_TOKEN=你自己的访问令牌
```

启动服务：

```bash
docker compose up -d --build
```

先本机测试：

```bash
curl http://127.0.0.1:8000/health
```

如果返回：

```json
{"status":"ok"}
```

说明后端服务已经正常运行。

## 7. Nginx 基础反向代理配置

假设你的域名是：

```text
ppt.example.com
```

新建 Nginx 配置文件：

```bash
sudo nano /etc/nginx/sites-available/ppt-service
```

写入：

```nginx
server {
    listen 80;
    server_name ppt.example.com;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

几个关键点：

- `client_max_body_size 50m;`
  防止上传 PDF 或 Markdown 时被 Nginx 拦掉

- `proxy_read_timeout 300s;`
  防止请求较长时，Nginx 提前断开连接

## 8. 启用配置

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/ppt-service /etc/nginx/sites-enabled/ppt-service
```

检查配置：

```bash
sudo nginx -t
```

重载 Nginx：

```bash
sudo systemctl reload nginx
```

## 9. 测试代理是否成功

先测试健康检查：

```bash
curl http://ppt.example.com/health
```

如果你配置了 `API_TOKEN`，`/styles` 这类接口需要带 token：

```bash
curl -H "Authorization: Bearer 你的API_TOKEN" \
  http://ppt.example.com/styles
```

## 10. HTTPS 配置

如果你已经有域名，建议直接配 HTTPS。

Ubuntu 上推荐用 Certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

然后执行：

```bash
sudo certbot --nginx -d ppt.example.com
```

它会自动：

- 申请 Let’s Encrypt 证书
- 修改 Nginx 配置
- 自动加 HTTPS 跳转

配置完成后，你就可以通过：

```text
https://ppt.example.com
```

访问服务。

## 11. API Token 配合建议

Nginx 只是代理层，不会替代服务内部鉴权。

建议你在 `.env` 里配置：

```text
API_TOKEN=一个足够长的随机字符串
```

然后调用接口时始终带：

```text
Authorization: Bearer 你的_token
```

这样即使别人知道你的域名，也不能直接随便调用服务。

## 12. 防火墙建议

如果用了 Nginx，建议：

- 只开放 `80` 和 `443`
- 不要长期对公网开放 `8000`

如果你使用 UFW：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp
sudo ufw status
```

如果你需要先调试，也可以临时放开 `8000`，确认完成后再关掉。

## 13. 请求示例

### 查询健康状态

```bash
curl https://ppt.example.com/health
```

### 查询风格列表

```bash
curl -H "Authorization: Bearer 你的API_TOKEN" \
  https://ppt.example.com/styles
```

### 上传文件创建任务

```bash
curl -X POST https://ppt.example.com/jobs \
  -H "Authorization: Bearer 你的API_TOKEN" \
  -F "file=@./example.pdf" \
  -F "style=scientific-defense" \
  -F "language=zh" \
  -F "page_count=8" \
  -F "image_concurrency=2"
```

### 查询任务状态

```bash
curl -H "Authorization: Bearer 你的API_TOKEN" \
  https://ppt.example.com/jobs/JOB_ID
```

### 下载 PPT

```bash
curl -L \
  -H "Authorization: Bearer 你的API_TOKEN" \
  https://ppt.example.com/jobs/JOB_ID/download \
  -o result.pptx
```

## 14. 日志与排查

### 查看 PPT 服务日志

```bash
cd /opt/ppt-service
docker compose logs -f
```

### 查看 Nginx 日志

访问日志：

```bash
sudo tail -f /var/log/nginx/access.log
```

错误日志：

```bash
sudo tail -f /var/log/nginx/error.log
```

### 查看任务目录

```bash
ls /opt/ppt-service/data/jobs
```

单个任务目录里重点看：

- `status.json`
- `job.log`
- `deck_spec.json`
- `output.pptx`

## 15. 常见问题

### 15.1 访问域名 502 Bad Gateway

通常表示：

- Nginx 能收到请求
- 但转发到 `127.0.0.1:8000` 失败

检查：

```bash
curl http://127.0.0.1:8000/health
docker compose ps
docker compose logs -f
```

### 15.2 上传大文件时报 413

说明：

- Nginx 限制了请求体大小

处理：

- 提高 `client_max_body_size`

例如：

```nginx
client_max_body_size 50m;
```

### 15.3 请求超时

说明：

- 生图和 PPT 生成过程可能较长

处理：

- 调大这些超时参数：

```nginx
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
```

### 15.4 外网可以访问但接口一直 401

说明：

- 你设置了 `API_TOKEN`
- 但请求里没带 token，或者 token 不对

处理：

- 检查：

```text
Authorization: Bearer 你的API_TOKEN
```

## 16. 最终建议

按当前项目阶段，最推荐的公网部署方式是：

```text
Ubuntu 服务器
Docker Compose 运行 PPT 服务
系统层 Nginx 做反向代理
Certbot 配 HTTPS
API_TOKEN 做接口鉴权
```

这条路线最稳，排查最直接，也最适合你现在这种小规模、自用或少量用户访问的场景。
