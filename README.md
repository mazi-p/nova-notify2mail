# nova-notify2mail

## 📌 Overview
`nova-notify2mail` is a lightweight Python service that listens to **OpenStack Nova** notifications via RabbitMQ and sends **email alerts** when VM creation succeeds or fails.

It is designed to:
- Run inside a **dedicated LXC container** or VM
- Integrate with **OpenStack-Ansible** via a custom role
- Be fully configurable via **environment variables**
- Automatically reconnect to RabbitMQ and retry SMTP/Keystone lookups
- Log all activity to a rotating log file

---

## 🚀 Features
- **Persistent RabbitMQ queue** — no lost messages on restart
- **Friendly email formatting** — clear subject and body
- **Tenant admin lookup** — sends alerts to the project’s admin(s)
- **Fallback email** — if no tenant admin email is found
- **Retry logic** — for RabbitMQ, SMTP, and Keystone
- **Daily log rotation** — keeps 7 days of logs

---

## 🛠 Requirements
Inside the container:
- Python 3.6+
- `pika`
- `keystoneauth1`
- `python-keystoneclient`

These are pinned in `requirements.txt` for reproducibility.

---

## ⚙️ Configuration

All configuration is done via **environment variables**.
Defaults are in `os_nova_notify2mail/defaults/main.yml`.

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVA_NOTIFY2MAIL_RABBITMQ_HOST` | `controller.example.com` | RabbitMQ host |
| `NOVA_NOTIFY2MAIL_RABBITMQ_PORT` | `5672` | RabbitMQ port |
| `NOVA_NOTIFY2MAIL_RABBITMQ_USER` | `openstack` | RabbitMQ username |
| `NOVA_NOTIFY2MAIL_RABBITMQ_PASS` | `RABBIT_PASS` | RabbitMQ password |
| `NOVA_NOTIFY2MAIL_RABBITMQ_VHOST` | `/` | RabbitMQ vhost |
| `NOVA_NOTIFY2MAIL_QUEUE_NAME` | `nova_notifications` | Persistent queue name |
| `NOVA_NOTIFY2MAIL_SMTP_SERVER` | `smtp.example.com` | SMTP server |
| `NOVA_NOTIFY2MAIL_SMTP_PORT` | `25` | SMTP port |
| `NOVA_NOTIFY2MAIL_SMTP_FROM` | `openstack-alerts@example.com` | From address |
| `NOVA_NOTIFY2MAIL_DEFAULT_ADMIN` | `cloud-admin@example.com` | Fallback recipient |
| `NOVA_NOTIFY2MAIL_OS_AUTH_URL` | `http://controller:5000/v3` | Keystone URL |
| `NOVA_NOTIFY2MAIL_OS_USERNAME` | `admin` | Keystone admin username |
| `NOVA_NOTIFY2MAIL_OS_PASSWORD` | `ADMIN_PASS` | Keystone admin password |
| `NOVA_NOTIFY2MAIL_OS_PROJECT_NAME` | `admin` | Keystone admin project |
| `NOVA_NOTIFY2MAIL_OS_USER_DOMAIN_NAME` | `Default` | Keystone user domain |
| `NOVA_NOTIFY2MAIL_OS_PROJECT_DOMAIN_NAME` | `Default` | Keystone project domain |
| `NOVA_NOTIFY2MAIL_LOG_FILE` | `/var/log/nova_notify2mail.log` | Log file path |
| `NOVA_NOTIFY2MAIL_LOG_LEVEL` | `INFO` | Log level |

---

## 📦 Deployment

### Option 1 — Manual inside LXC
```bash
apt update && apt install python3-pip -y
pip3 install -r /opt/nova-notify2mail/requirements.txt

# Copy script and service
cp os_nova_notify2mail/files/nova_notify2mail.py /opt/nova-notify2mail/
cp os_nova_notify2mail/files/nova-notify2mail.service /etc/systemd/system/

# Create log file
touch /var/log/nova_notify2mail.log
chown root:root /var/log/nova_notify2mail.log

# Set environment variables in a systemd drop-in
mkdir -p /etc/systemd/system/nova-notify2mail.service.d
cat <<EOF > /etc/systemd/system/nova-notify2mail.service.d/env.conf
[Service]
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_HOST=controller.example.com"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_USER=openstack"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_PASS=RABBIT_PASS"
Environment="NOVA_NOTIFY2MAIL_SMTP_SERVER=smtp.example.com"
EOF

systemctl daemon-reload
systemctl enable --now nova-notify2mail
```

### Option 2 — Via OpenStack-Ansible role

1. Place the role
   Copy `os_nova_notify2mail/` into `/etc/ansible/roles/os_nova_notify2mail`.

2. Add container definition
   Place `conf.d/nova_notify2mail.yml` into `/etc/openstack_deploy/conf.d/`.

3. Create the container
```bash
openstack-ansible lxc-containers-create.yml --limit nova_notify2mail_container
```

4. Deploy the role
```bash
openstack-ansible playbooks/deploy_nova_notify2mail.yml
```

---

## 🧪 Testing
1. Create a VM in OpenStack.
2. Check `/var/log/nova_notify2mail.log` for `instance.create.end` or `instance.create.error` events.
3. Verify that the correct email is sent to the tenant admin or fallback address.

---

## 🔍 Troubleshooting
- **No emails sent**: Check RabbitMQ credentials and that Nova notifications are enabled in `nova.conf`.
- **Keystone lookup fails**: Verify admin credentials and API endpoint.
- **Service not starting**: Run `systemctl status nova-notify2mail` inside the container.
- **No logs**: Ensure the log file path is writable by the service user.

---

## 📜 License
MIT License — feel free to modify and adapt.
