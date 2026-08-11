# Deploying Agent Reach Web on OracleVM (Always-Free VPS)

This guide walks you through deploying the full Agent Reach Web stack on an Oracle Cloud Always Free VM so it stays online 24/7.

---

## Prerequisites

- An Oracle Cloud account with an Always-Free ARM or AMD VM (Ubuntu 22.04+ recommended)
- SSH access to your VM
- A domain name (optional, but recommended for HTTPS)

---

## Step 1: SSH Into Your VM

```bash
ssh -i ~/.ssh/your-key ubuntu@YOUR_VM_IP
```

---

## Step 2: Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip nodejs npm git curl

# Install Node.js 20+ (if default is too old)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## Step 3: Clone the Project

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/agent-reach-web.git
cd agent-reach-web
```

---

## Step 4: Install Agent Reach

```bash
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
deactivate
```

---

## Step 5: Set Up the Backend

```bash
cd ~/agent-reach-web/backend

# Create a venv for the backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env
# Set:
#   CORS_ORIGINS=https://your-domain.com,http://YOUR_VM_IP:5173
#   AGENT_REACH_BIN=/home/ubuntu/.agent-reach-venv/bin/agent-reach
#   API_SECRET_KEY=<generate a random string>

deactivate
```

---

## Step 6: Build the Frontend

```bash
cd ~/agent-reach-web/frontend
npm install

# Point to your backend URL
echo 'VITE_API_BASE=http://YOUR_VM_IP:8000' > .env.production

npm run build
```

---

## Step 7: Set Up systemd Services

### Backend Service

```bash
sudo tee /etc/systemd/system/agent-reach-api.service > /dev/null << 'EOF'
[Unit]
Description=Agent Reach Web API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/agent-reach-web/backend
Environment="PATH=/home/ubuntu/agent-reach-web/backend/.venv/bin:/home/ubuntu/.agent-reach-venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/agent-reach-web/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### Frontend Service (serve static build)

```bash
# Install a simple static file server
sudo npm install -g serve

sudo tee /etc/systemd/system/agent-reach-web.service > /dev/null << 'EOF'
[Unit]
Description=Agent Reach Web Frontend
After=network.target

[Service]
Type=simple
User=ubuntu
ExecStart=/usr/bin/serve -s /home/ubuntu/agent-reach-web/frontend/dist -l 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-reach-api agent-reach-web
sudo systemctl start agent-reach-api agent-reach-web

# Check status
sudo systemctl status agent-reach-api
sudo systemctl status agent-reach-web
```

---

## Step 8: Open Firewall Ports

```bash
# Oracle VM uses iptables
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo netfilter-persistent save

# ALSO: Go to Oracle Cloud Console → Networking → Virtual Cloud Networks
# → Your VCN → Security Lists → Add Ingress Rules for ports 8000 and 3000
```

---

## Step 9: Access Your Console

- **Frontend**: `http://YOUR_VM_IP:3000`
- **Backend API**: `http://YOUR_VM_IP:8000/docs`

---

## Optional: HTTPS with Nginx + Certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

# Configure Nginx as reverse proxy
sudo tee /etc/nginx/sites-available/agent-reach > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 120s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/agent-reach /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

---

## Useful Commands

```bash
# View logs
sudo journalctl -u agent-reach-api -f
sudo journalctl -u agent-reach-web -f

# Restart services
sudo systemctl restart agent-reach-api
sudo systemctl restart agent-reach-web

# Update Agent Reach
source ~/.agent-reach-venv/bin/activate
pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip
sudo systemctl restart agent-reach-api
```
