# 容器化 Nginx 部署方案

本文档说明如何直接使用项目内已经合并好的 Nginx 配置，把 PPT 服务通过 Nginx 暴露出去。

当前项目已经包含：

- [docker-compose.yml](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/docker-compose.yml>)
- [nginx/default.conf](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/nginx/default.conf>)

这套方案适合：

- 你想尽快在服务器上部署
- 你不想单独在系统层安装 Nginx
- 你先接受 HTTP，后面再升级 HTTPS

## 1. 工作方式

启动后，结构是：

```text
客户端
  -> nginx:80
  -> ppt-service:8000
  -> FastAPI
```

其中：

- `ppt-service` 是后端服务
- `nginx` 是反向代理容器
- Nginx 通过容器网络访问 `ppt-service:8000`

## 2. 当前主 compose 的行为

现在的 [docker-compose.yml](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/docker-compose.yml>) 已经直接包含：

- `ppt-service`
- `nginx`

并且：

- `ppt-service` 只做内部 `expose: 8000`
- `nginx` 对宿主机暴露 `80:80`

也就是说，部署时不再需要第二个 compose 文件。

## 3. 启动前准备

先准备 `.env`：

```bash
cp .env.example .env
```

至少填：

```text
DEEPSEEK_API_KEY=你的_deepseek_key
OPENAI_API_KEY=你的_openai_key
API_TOKEN=你自己的访问令牌
```

建议保留：

```text
MAX_ACTIVE_JOBS=1
MAX_IMAGE_CONCURRENCY_PER_JOB=3
MAX_IMAGE_RETRIES=2
MAX_QUEUED_JOBS=10
```

## 4. 启动命令

在项目根目录执行：

```bash
docker compose up -d --build
```

这个命令会同时启动：

- `ppt-service`
- `nginx`

## 5. 查看状态

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

## 6. 访问方式

启动成功后，默认通过宿主机 `80` 端口访问。

健康检查：

```bash
curl http://127.0.0.1/health
```

如果在远端服务器上有公网 IP：

```bash
curl http://你的服务器IP/health
```

如果你已经配置了域名：

```bash
curl http://你的域名/health
```

## 7. 接口调用

因为建议你设置了 `API_TOKEN`，所以正式接口请求应带：

```text
Authorization: Bearer 你的API_TOKEN
```

查询风格：

```bash
curl -H "Authorization: Bearer 你的API_TOKEN" \
  http://你的服务器IP/styles
```

创建任务：

```bash
curl -X POST http://你的服务器IP/jobs \
  -H "Authorization: Bearer 你的API_TOKEN" \
  -F "file=@./example.pdf" \
  -F "style=scientific-defense" \
  -F "language=zh" \
  -F "page_count=8" \
  -F "image_concurrency=2"
```

查询状态：

```bash
curl -H "Authorization: Bearer 你的API_TOKEN" \
  http://你的服务器IP/jobs/JOB_ID
```

下载 PPT：

```bash
curl -L \
  -H "Authorization: Bearer 你的API_TOKEN" \
  http://你的服务器IP/jobs/JOB_ID/download \
  -o result.pptx
```

## 8. 结果目录

结果仍然落在宿主机：

```text
./data/jobs/{job_id}/
```

因为 compose 里仍然挂载了：

```text
./data:/data
```

## 9. HTTPS 说明

当前这套容器化 Nginx 方案默认只提供 HTTP。

如果你后面要上 HTTPS，建议两条路选一条：

- 继续保留当前容器化结构，再自己扩展 Nginx 证书配置
- 改为系统层 Nginx + Certbot

如果你现在只是先把服务跑起来，先用 HTTP 足够。

## 10. 常见问题

### 10.1 `80` 端口被占用

说明：

- 服务器上可能已经有别的 Web 服务

处理：

- 先停掉已有服务
- 或者把 [docker-compose.yml](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/docker-compose.yml>) 里的：

```yaml
    ports:
      - "80:80"
```

改成：

```yaml
    ports:
      - "8080:80"
```

这样就可以通过：

```text
http://服务器IP:8080
```

访问。

### 10.2 访问 502

说明：

- Nginx 容器起来了
- 但后端 `ppt-service` 不可用或者没起来

排查：

```bash
docker compose ps
docker compose logs -f
```

### 10.3 上传文件时报 413

说明：

- 上传内容超过了 Nginx 请求体限制

处理：

- 修改 [nginx/default.conf](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/nginx/default.conf>) 里的：

```nginx
client_max_body_size 50m;
```

### 10.4 长任务超时

处理：

- 修改 [nginx/default.conf](</C:/Users/Windows/Desktop/Explore/PPT_Generator_v2/nginx/default.conf>) 里的：

```nginx
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
```

## 11. 最终建议

如果你想最快把服务放上服务器，现在最直接的部署命令就是：

```bash
docker compose up -d --build
```

这就是当前项目里已经准备好的 Nginx 部署方式。HTTPS 可以等服务跑稳之后再补。
