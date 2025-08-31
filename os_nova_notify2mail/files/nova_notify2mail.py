#!/usr/bin/env python3
import pika
import json
import smtplib
import time
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from email.mime.text import MIMEText
from keystoneauth1 import loading, session
from keystoneclient.v3 import client as keystone_client

# ==== CONFIG FROM ENV ====
RABBITMQ_HOST = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_HOST", "controller.example.com")
RABBITMQ_PORT = int(os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_USER", "openstack")
RABBITMQ_PASS = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_PASS", "RABBIT_PASS")
RABBITMQ_VHOST = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_VHOST", "/nova_notify2mail")
QUEUE_NAME = os.getenv("NOVA_NOTIFY2MAIL_QUEUE_NAME", "nova_notifications")

SMTP_SERVER = os.getenv("NOVA_NOTIFY2MAIL_SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_PORT", "25"))
SMTP_FROM = os.getenv("NOVA_NOTIFY2MAIL_SMTP_FROM", "openstack-alerts@example.com")
DEFAULT_ADMIN_EMAIL = os.getenv("NOVA_NOTIFY2MAIL_DEFAULT_ADMIN", "cloud-admin@example.com")
SMTP_RETRIES = int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_RETRIES", "3"))
SMTP_RETRY_DELAY = int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_RETRY_DELAY", "5"))

OS_AUTH_URL = os.getenv("NOVA_NOTIFY2MAIL_OS_AUTH_URL", "http://controller:5000/v3")
OS_USERNAME = os.getenv("NOVA_NOTIFY2MAIL_OS_USERNAME", "admin")
OS_PASSWORD = os.getenv("NOVA_NOTIFY2MAIL_OS_PASSWORD", "ADMIN_PASS")
OS_PROJECT_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_PROJECT_NAME", "admin")
OS_USER_DOMAIN_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_USER_DOMAIN_NAME", "Default")
OS_PROJECT_DOMAIN_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_PROJECT_DOMAIN_NAME", "Default")
KEYSTONE_RETRIES = int(os.getenv("NOVA_NOTIFY2MAIL_KEYSTONE_RETRIES", "3"))
KEYSTONE_RETRY_DELAY = int(os.getenv("NOVA_NOTIFY2MAIL_KEYSTONE_RETRY_DELAY", "5"))

LOG_FILE = os.getenv("NOVA_NOTIFY2MAIL_LOG_FILE", "/var/log/nova_notify2mail.log")
LOG_LEVEL = getattr(logging, os.getenv("NOVA_NOTIFY2MAIL_LOG_LEVEL", "INFO").upper(), logging.INFO)
# =========================

# --- Setup logging ---
logger = logging.getLogger("NovaNotify2Mail")
logger.setLevel(LOG_LEVEL)

console_handler = logging.StreamHandler()
console_handler.setLevel(LOG_LEVEL)

file_handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", backupCount=7)
file_handler.setLevel(LOG_LEVEL)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# --- Functions ---
def send_email(subject, body, recipient):
    """Send an email via SMTP with retry logic."""
    for attempt in range(1, SMTP_RETRIES + 1):
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM
            msg["To"] = recipient

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                server.sendmail(SMTP_FROM, [recipient], msg.as_string())
            logger.info(f"Email sent to {recipient}")
            return
        except Exception as e:
            logger.warning(f"SMTP send failed (attempt {attempt}/{SMTP_RETRIES}): {e}")
            if attempt < SMTP_RETRIES:
                time.sleep(SMTP_RETRY_DELAY)
    logger.error(f"Failed to send email to {recipient} after {SMTP_RETRIES} attempts.")

def get_tenant_admin_emails(tenant_id):
    """Look up admin users for a given tenant/project in Keystone with retry logic."""
    for attempt in range(1, KEYSTONE_RETRIES + 1):
        try:
            loader = loading.get_plugin_loader('password')
            auth = loader.load_from_options(
                auth_url=OS_AUTH_URL,
                username=OS_USERNAME,
                password=OS_PASSWORD,
                project_name=OS_PROJECT_NAME,
                user_domain_name=OS_USER_DOMAIN_NAME,
                project_domain_name=OS_PROJECT_DOMAIN_NAME
            )
            sess = session.Session(auth=auth)
            keystone = keystone_client.Client(session=sess)

            users = keystone.users.list()
            admins = []
            for user in users:
                roles = keystone.roles.list(user=user.id, project=tenant_id)
                if any(r.name.lower() == "admin" for r in roles):
                    if getattr(user, "email", None):
                        admins.append(user.email)

            return admins
        except Exception as e:
            logger.warning(f"Keystone lookup failed (attempt {attempt}/{KEYSTONE_RETRIES}): {e}")
            if attempt < KEYSTONE_RETRIES:
                time.sleep(KEYSTONE_RETRY_DELAY)
    return []

def format_event(payload, event_type):
    """Create a friendly subject and body for the event."""
    instance = payload.get("instance_id", "unknown")
    name = payload.get("display_name", "unknown")
    state = payload.get("state", "unknown")
    fault = payload.get("fault", {})

    if event_type.endswith(".end"):
        status = "SUCCESS"
        reason = ""
    elif event_type.endswith(".error"):
        status = "FAILED"
        reason = fault.get("message", "Unknown error")
    else:
        status = "INFO"
        reason = ""

    subject = f"VM Creation {status}: {name} ({instance})"
    body_lines = [
        f"Event Type: {event_type}",
        f"Instance Name: {name}",
        f"Instance UUID: {instance}",
        f"State: {state}",
    ]
    if reason:
        body_lines.append(f"Reason: {reason}")

    return subject, "\n".join(body_lines)

def on_message(ch, method, properties, body):
    """Callback for incoming RabbitMQ messages."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Received non-JSON message, skipping")
        return

    event_type = payload.get("event_type", "")
    if event_type.startswith("instance.create."):
        data = payload.get("payload", {})
        tenant_id = data.get("tenant_id") or data.get("project_id")
        subject, body_text = format_event(data, event_type)

        recipients = []
        if tenant_id:
            recipients = get_tenant_admin_emails(tenant_id)

        if not recipients:
            recipients = [DEFAULT_ADMIN_EMAIL]

        for recipient in recipients:
            logger.info(f"Sending email to {recipient} for event {event_type}")
            send_email(subject, body_text, recipient)

def connect_and_consume():
    """Connect to RabbitMQ and start consuming, with reconnect logic."""
    while True:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    virtual_host=RABBITMQ_VHOST,
                    credentials=credentials,
                    heartbeat=60
                )
            )
            channel = connection.channel()

            # Declare persistent queue
            channel.queue_declare(queue=QUEUE_NAME, durable=True, auto_delete=False)

            # Bind to Nova's notification topics
            channel.queue_bind(exchange='nova', queue=QUEUE_NAME, routing_key='notifications.info')
            channel.queue_bind(exchange='nova', queue=QUEUE_NAME, routing_key='notifications.error')

            logger.info("Connected to RabbitMQ. Waiting for instance.create.* events.")
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=True)
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"RabbitMQ connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    logger.info("Nova Notify2Mail consumer starting...")
    connect_and_consume()
