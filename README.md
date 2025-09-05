# nova-notify2mail

## 📌 Overview
`nova-notify2mail` is a lightweight Python service that listens to **OpenStack Nova** notifications via RabbitMQ and sends **email alerts** when VM creation succeeds or fails.

It is designed to:
- Run inside a **dedicated LXC container** or VM
- Integrate seamlessly with **OpenStack-Ansible** (OSA)
- Reuse existing OSA variables and secrets (RabbitMQ, Keystone)
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
Defaults are in `os_nova_notify2mail/defaults/main.yml` and many are **sourced from OSA’s existing variables** in `/etc/openstack_deploy/user_secrets.yml` and `/etc/openstack_deploy/user_variables.yml`.

---

## 📦 Deployment

### nova-notify2mail OpenStack-Ansible Role

This repository installs and configures `nova-notify2mail` as an OpenStack‑Ansible role.
It includes a **pre-install script** to generate a ready-to-deploy `env.conf` from your existing OpenStack‑Ansible configuration, so there’s no Jinja parsing at runtime.

---

#### Prerequisites

- **OpenStack-Ansible control host** (OSA deploy node)
- **Nova** services should used the Versioned Notifications provided by **oslo.messaging**
- **Required config files**:
  - `/etc/openstack_deploy/user_secrets.yml`
  - `/etc/openstack_deploy/openstack_user_config.yml`
- **LXC/LXD** container runtime (standard in OSA)
- **Root privileges** to copy files into system paths

---

#### Repository Layout

- roles/nova-notify2mail/ # The Ansible role
- playbooks/ # Playbooks to run the role
- env.d/ # Optional OSA environment overrides
- pre-install.sh # Pre-flight script


---

#### Using `pre-install.sh`

The script:

1. **Extracts**:
   - RabbitMQ password (`nova_oslomsg_rpc_password`)
   - Keystone admin password (`keystone_auth_admin_password`)
   - RabbitMQ host IP (from `rabbitmq_all` in inventory)
   - Internal LB VIP (`internal_lb_vip_address`)
   - Builds `OS_AUTH_URL` as `http://<internal_lb_vip_address>:5000/v3`

2. **Writes**:
   - `roles/nova-notify2mail/files/env.conf` with all required `NOVA_NOTIFY2MAIL_*` variables

3. **Copies**:
   - Role → `/etc/ansible/roles/nova-notify2mail`
   - Playbooks → `/opt/openstack-ansible/playbooks/`
   - env.d → `/etc/openstack_deploy/env.d/`

##### Steps

```bash
cd /path/to/this/repo
chmod +x pre-install.sh
./pre-install.sh
````

##### verify:

```bash
ls -l /etc/ansible/roles/nova-notify2mail/files/env.conf
ls -l /opt/openstack-ansible/playbooks | grep notify2mail
ls -l /etc/openstack_deploy/env.d
```

---
#### Running with OpenStack-Ansible

##### Minimal playbook example:

```bash
# /opt/openstack-ansible/playbooks/nova-notify2mail-install.yml
- hosts: nova-notify2mail_container
  gather_facts: false
  roles:
    - nova-notify2mail
```

##### run it:

```bash
cd /opt/openstack-ansible/playbooks
openstack-ansible nova-notify2mail-install.yml
```

---
#### Verifying the Deployment

Check drop-in:

```bash
lxc exec <container> -- systemctl cat nova-notify2mail
```

Check environment variables:

```bash
lxc exec <container> -- systemctl show nova-notify2mail --property=Environment
```

---
#### Example Files
`nova-notify2mail.service`

Place this in `roles/nova-notify2mail/files/nova-notify2mail.service`:

```ini
[Unit]
Description=Nova Notify to Mail Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/nova-notify2mail/nova_notify2mail.py
Restart=always
RestartSec=5
# Drop-in env.conf will be loaded automatically from:
# /etc/systemd/system/nova-notify2mail.service.d/env.conf

[Install]
WantedBy=multi-user.target
```
---
##### Sample `env.conf`

This is what `pre-install.sh` will generate in `roles/nova-notify2mail/files/env.conf`:

```ini
[Service]
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_HOST=172.29.238.226"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_PORT=5671"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_USER=nova"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_PASS=supersecret"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_VHOST=nova"
Environment="NOVA_NOTIFY2MAIL_QUEUE_NAME=versioned_notify2mail"
Environment="NOVA_NOTIFY2MAIL_EXCHANGE=nova"
Environment="NOVA_NOTIFY2MAIL_RABBITMQ_SSL=1"
Environment="NOVA_NOTIFY2MAIL_LOG_FILE=/var/log/nova_notify2mail.log"
Environment="NOVA_NOTIFY2MAIL_LOG_LEVEL=INFO"
Environment="NOVA_NOTIFY2MAIL_OS_AUTH_URL=http://172.29.236.101:5000/v3"
Environment="NOVA_NOTIFY2MAIL_OS_USERNAME=admin"
Environment="NOVA_NOTIFY2MAIL_OS_PASSWORD=keystonepass"
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
```


##### Notes:

  - Always run systemctl daemon-reload and systemctl restart nova-notify2mail inside the container after changes to env.conf or the service unit.
  - The role’s handler will do this automatically when run via Ansible.
  - If you change RabbitMQ or Keystone credentials, re-run pre-install.sh before re-deploying.


---

## 🧪 Testing
1. Create a VM in OpenStack.
2. In the `aio1-nova-notify2mail-container-########` check `/var/log/nova_notify2mail.log` for `instance.create.end` or `instance.create.error` events payload.
3. In the `aio1-nova-notify2mail-container-########` check `/var/log/nova_notify2mail.log` for mock Email logs or set the right config to send Email.

---

## 🔍 Troubleshooting
- **No emails sent**: Check RabbitMQ credentials and that Nova notifications are enabled in `nova.conf`.
- **Keystone lookup fails**: Verify admin credentials and API endpoint.
- **Service not starting**: Run `systemctl status nova-notify2mail` inside the container.
- **No logs**: Ensure the log file path is writable by the service user.
