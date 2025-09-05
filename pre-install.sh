#!/usr/bin/env bash
set -euo pipefail

# --- CONFIG ---
REPO_DIR="$(pwd)"  # run from repo root
ROLE_NAME="nova-notify2mail"
ROLE_DIR="/etc/ansible/roles/${ROLE_NAME}"
PLAYBOOKS_DIR="/opt/openstack-ansible/playbooks"
ENV_D_DIR="/etc/openstack_deploy/env.d"
SECRETS_FILE="/etc/openstack_deploy/user_secrets.yml"
INVENTORY_FILE="/etc/openstack_deploy/openstack_inventory.json" 
USER_CONFIG="/etc/openstack_deploy/openstack_user_config.yml"
ENV_FILE_ROLE="${ROLE_DIR}/files/env.conf"

echo "[INFO] Preparing role directory..."
mkdir -p "${ROLE_DIR}/files"

# --- 1. Extract required values ---
echo "[INFO] Extracting Nova RabbitMQ password..."
RABBIT_PASS=$(grep -E '^nova_oslomsg_rpc_password:' "$SECRETS_FILE" | awk '{print $2}')

echo "[INFO] Extracting Keystone admin password..."
KEYSTONE_PASS=$(grep -E '^keystone_auth_admin_password:' "$SECRETS_FILE" | awk '{print $2}')

echo "[INFO] Extracting RabbitMQ host IP..."
RABBIT_HOST=$(grep -A2 'aio1-rabbit-mq-container' "$INVENTORY_FILE" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')

echo "[INFO] Extracting internal LB VIP address..."
INTERNAL_LB_IP=$(grep -E 'internal_lb_vip_address:' "$USER_CONFIG" | awk '{print $2}')

# Build OS_AUTH_URL
OS_AUTH_URL="http://${INTERNAL_LB_IP}:5000/v3"

# --- 2. Build env.conf in role directory ---
echo "[INFO] Writing env.conf to ${ENV_FILE_ROLE}..."
cat > "$ENV_FILE_ROLE" <<EOF
[Service]
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_HOST=${RABBIT_HOST}"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_PORT=5671"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_USER=nova"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_PASS=${RABBIT_PASS}"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_VHOST=nova"
Environment="NOVA_NOTIFY2MAIL_QUEUE_NAME=versioned_notify2mail"
Environment="NOVA_NOTIFY2MAIL_EXCHANGE=nova"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_SSL=1"
Environment="NOVA_NOTIFY2MAIL_LOG_FILE=/var/log/nova_notify2mail.log"
Environment="NOVA_NOTIFY2MAIL_LOG_LEVEL=INFO"
Environment="NOVA_NOTIFY2MAIL_OS_AUTH_URL=${OS_AUTH_URL}"
Environment="NOVA_NOTIFY2MAIL_OS_USERNAME=admin"
Environment="NOVA_NOTIFY2MAIL_OS_PASSWORD=${KEYSTONE_PASS}"
Environment="NOVA_NOTIFY2MAIL_OS_PROJECT_NAME=admin"
Environment="NOVA_NOTIFY2MAIL_OS_USER_DOMAIN_NAME=Default"
Environment="NOVA_NOTIFY2MAIL_OS_PROJECT_DOMAIN_NAME=Default"
Environment="NOVA_NOTIFY2MAIL_SMTP_SERVER=smtp.yourmailserver.com"
Environment="NOVA_NOTIFY2MAIL_SMTP_PORT=587"
Environment="NOVA_NOTIFY2MAIL_SMTP_USERNAME=alert@example.com"
Environment="NOVA_NOTIFY2MAIL_SMTP_PASSWORD=CHANGEME_SMTP_PASS"
Environment="NOVA_NOTIFY2MAIL_SMTP_FROM=Nova Alerts <alert@example.com>"
Environment="NOVA_NOTIFY2MAIL_SMTP_TO=ops-team@example.com"
Environment="NOVA_NOTIFY2MAIL_SMTP_USE_TLS=1"
Environment="NOVA_NOTIFY2MAIL_SMTP_USE_SSL=0"
EOF

# --- 3. Copy repo contents into correct locations ---
echo "[INFO] Copying role into ${ROLE_DIR}..."
mkdir -p "${ROLE_DIR}"
cp -R "${REPO_DIR}/roles/${ROLE_NAME}/"* "${ROLE_DIR}/"

echo "[INFO] Copying playbooks into ${PLAYBOOKS_DIR}..."
mkdir -p "${PLAYBOOKS_DIR}"
cp -R "${REPO_DIR}/playbooks/"* "${PLAYBOOKS_DIR}/"

echo "[INFO] Copying env.d into ${ENV_D_DIR}..."
mkdir -p "${ENV_D_DIR}"
cp -R "${REPO_DIR}/env.d/"* "${ENV_D_DIR}/"

echo "[INFO] Pre‑installation complete."
echo "       You can now run your Ansible playbook and it will deploy the updated env.conf."

