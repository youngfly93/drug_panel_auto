#!/bin/bash
# ============================================================
# 基因组Panel自动化报告系统 - 一键部署脚本
# 目标服务器: JD Cloud (117.72.75.45)
# 用法: ssh root@117.72.75.45 后粘贴执行，或上传后 bash deploy.sh
# ============================================================
set -e

APP_DIR="/opt/reportgen-web"
REPO_URL="https://github.com/youngfly93/drug_panel_auto.git"
DOMAIN="117.72.75.45"

echo "============================================"
echo "  基因组Panel自动化报告系统 - 部署开始"
echo "============================================"

# ---- 1. 系统依赖 ----
echo "[1/7] 安装系统依赖..."
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv nodejs npm nginx git curl
elif command -v yum &>/dev/null; then
    yum install -y python3 python3-pip nodejs npm nginx git curl
    # CentOS/RHEL 可能需要 epel
    yum install -y epel-release 2>/dev/null || true
fi

# Check Node version (need 18+)
NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [ -z "$NODE_VER" ] || [ "$NODE_VER" -lt 16 ]; then
    echo "  Node.js 版本过低或未安装，正在安装 Node 18..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - 2>/dev/null || \
    curl -fsSL https://rpm.nodesource.com/setup_18.x | bash - 2>/dev/null || true
    apt-get install -y nodejs 2>/dev/null || yum install -y nodejs 2>/dev/null || true
fi

echo "  Python: $(python3 --version)"
echo "  Node: $(node --version 2>/dev/null || echo 'N/A')"
echo "  Nginx: $(nginx -v 2>&1 | head -1)"

# ---- 2. 拉取代码 ----
echo ""
echo "[2/7] 拉取代码..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull origin main
else
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ---- 3. Python 虚拟环境 + 依赖 ----
echo ""
echo "[3/7] 安装 Python 依赖..."
python3 -m venv "$APP_DIR/venv" 2>/dev/null || python3 -m virtualenv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$APP_DIR/requirements.txt" -q
# Install the backend package
pip install -e "$APP_DIR/backend" -q
echo "  Python deps installed"

# ---- 4. 前端构建 ----
echo ""
echo "[4/7] 构建前端..."
cd "$APP_DIR/frontend"
npm install --no-audit --no-fund 2>&1 | tail -1
npm run build 2>&1 | tail -3
# Copy built files to backend static dir
rm -rf "$APP_DIR/backend/static"
cp -r "$APP_DIR/frontend/dist" "$APP_DIR/backend/static"
echo "  Frontend built and copied to backend/static/"

# ---- 5. 创建存储目录 + 环境配置 ----
echo ""
echo "[5/7] 配置环境..."
mkdir -p "$APP_DIR/storage"/{uploads,reports,previews,db}

# Generate a random secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > "$APP_DIR/backend/.env" << ENVEOF
RG_WEB_SECRET_KEY=$SECRET_KEY
RG_WEB_UPSTREAM_ROOT=$APP_DIR
RG_WEB_STORAGE_ROOT=$APP_DIR/storage
RG_WEB_DEFAULT_ADMIN_USERNAME=admin
RG_WEB_DEFAULT_ADMIN_PASSWORD=panel2026
RG_WEB_MAX_WORKERS=2
ENVEOF
echo "  .env created (admin password: panel2026)"

# ---- 6. Systemd 服务 ----
echo ""
echo "[6/7] 配置系统服务..."
cat > /etc/systemd/system/reportgen-web.service << SVCEOF
[Unit]
Description=Genomic Panel Report Web Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/backend
Environment=PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin
EnvironmentFile=$APP_DIR/backend/.env
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable reportgen-web
systemctl restart reportgen-web
sleep 3

# Check if service started
if systemctl is-active --quiet reportgen-web; then
    echo "  ✅ reportgen-web service running"
else
    echo "  ❌ Service failed to start, checking logs..."
    journalctl -u reportgen-web --no-pager -n 20
fi

# ---- 7. Nginx 反向代理 ----
echo ""
echo "[7/7] 配置 Nginx 反向代理..."

cat > /etc/nginx/conf.d/reportgen-web.conf << 'NGXEOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    # Frontend static files
    location / {
        root /opt/reportgen-web/backend/static;
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }

    # OpenAPI docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
NGXEOF

# Remove default site if it conflicts
rm -f /etc/nginx/sites-enabled/default 2>/dev/null
rm -f /etc/nginx/conf.d/default.conf 2>/dev/null

# Test and reload nginx
nginx -t 2>&1
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo ""
echo "============================================"
echo "  ✅ 部署完成！"
echo "============================================"
echo ""
echo "  访问地址: http://$DOMAIN"
echo "  API 文档: http://$DOMAIN/docs"
echo "  登录账号: admin / panel2026"
echo ""
echo "  管理命令:"
echo "    systemctl status reportgen-web   # 查看状态"
echo "    systemctl restart reportgen-web  # 重启服务"
echo "    journalctl -u reportgen-web -f   # 查看日志"
echo ""

# Quick health check
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/tasks/stats 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "  🏥 健康检查: API 正常 (HTTP $HTTP_CODE)"
else
    echo "  ⚠ 健康检查: API 返回 HTTP $HTTP_CODE"
fi
