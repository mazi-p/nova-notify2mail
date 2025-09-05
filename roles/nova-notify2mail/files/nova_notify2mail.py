#!/usr/bin/env python3
import pika
import json
import time
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import requests
import smtplib
from email.mime.text import MIMEText

# ==== ENV CONFIG ====
RABBITMQ_HOST = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_HOST", "controller.example.com")
RABBITMQ_PORT = int(os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_USER", "openstack")
RABBITMQ_PASS = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_PASS", "RABBIT_PASS")
RABBITMQ_VHOST = os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_VHOST", "nova")
QUEUE_NAME = os.getenv("NOVA_NOTIFY2MAIL_QUEUE_NAME", "versioned_notify2mail")
EXCHANGE_NAME = os.getenv("NOVA_NOTIFY2MAIL_EXCHANGE", "nova")
ROUTING_KEYS = [
    "versioned_notifications.info",
    "versioned_notifications.error"
]

LOG_FILE = os.getenv("NOVA_NOTIFY2MAIL_LOG_FILE", "/var/log/nova_notify2mail.log")
LOG_LEVEL = getattr(logging, os.getenv("NOVA_NOTIFY2MAIL_LOG_LEVEL", "DEBUG").upper(), logging.DEBUG)

# Keystone auth
KEYSTONE_URL = os.getenv("NOVA_NOTIFY2MAIL_OS_AUTH_URL", "http://keystone.example.com:5000/v3")
OS_USERNAME = os.getenv("NOVA_NOTIFY2MAIL_OS_USERNAME", "admin")
OS_PASSWORD = os.getenv("NOVA_NOTIFY2MAIL_OS_PASSWORD", "secret")
OS_PROJECT_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_PROJECT_NAME", "admin")
OS_USER_DOMAIN_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_USER_DOMAIN_NAME", "Default")
OS_PROJECT_DOMAIN_NAME = os.getenv("NOVA_NOTIFY2MAIL_OS_PROJECT_DOMAIN_NAME", "Default")

# SMTP config
SMTP_SERVER = os.getenv("NOVA_NOTIFY2MAIL_SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("NOVA_NOTIFY2MAIL_SMTP_USERNAME", "alert@example.com")
SMTP_PASSWORD = os.getenv("NOVA_NOTIFY2MAIL_SMTP_PASSWORD", "changeme")
SMTP_FROM = os.getenv("NOVA_NOTIFY2MAIL_SMTP_FROM", "Nova Alerts <alert@example.com>")
SMTP_USE_TLS = bool(int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_USE_TLS", "1")))
SMTP_USE_SSL = bool(int(os.getenv("NOVA_NOTIFY2MAIL_SMTP_USE_SSL", "0")))
DEFAULT_SMTP_TO = os.getenv("NOVA_NOTIFY2MAIL_SMTP_TO", "ops-team@example.com")

# ==== LOGGING ====
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

# ==== Keystone helpers ====
def get_token():
    auth_url = f"{KEYSTONE_URL}/auth/tokens"
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": OS_USERNAME,
                        "domain": {"name": OS_USER_DOMAIN_NAME},
                        "password": OS_PASSWORD
                    }
                }
            },
            "scope": {
                "project": {
                    "name": OS_PROJECT_NAME,
                    "domain": {"name": OS_PROJECT_DOMAIN_NAME}
                }
            }
        }
    }
    resp = requests.post(auth_url, json=payload)
    resp.raise_for_status()
    return resp.headers["X-Subject-Token"]

def get_user_email(user_id):
    try:
        token = get_token()
        url = f"{KEYSTONE_URL}/users/{user_id}"
        headers = {"X-Auth-Token": token}
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("user", {}).get("email")
    except Exception as e:
        logger.warning(f"Could not fetch email for user {user_id}: {e}")
        return None

# ==== Mail sender ====
def send_mail(subject, body, to_addrs):
    """
    Send an email via SMTP with the given subject and body to the given recipient(s).
    to_addrs can be a string or a list.
    """
    logger.info("=== MOCK EMAIL ===")
    logger.info(f"To: {to_addrs}")
    logger.info(f"Subject: {subject}")
    logger.info("Body:")
    logger.info(body)
    logger.info("==================")
#    try:
#        if isinstance(to_addrs, str):
#            recipients = [addr.strip() for addr in to_addrs.split(",")]
#        else:
#            recipients = list(to_addrs)
#
#        msg = MIMEText(body, "plain", "utf-8")
#        msg["Subject"] = subject
#        msg["From"] = SMTP_FROM
#        msg["To"] = ", ".join(recipients)
#
#        if SMTP_USE_SSL:
#            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
#        else:
#            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
#
#        server.ehlo()
#
#        if SMTP_USE_TLS and not SMTP_USE_SSL:
#            server.starttls()
#            server.ehlo()
#
#        if SMTP_USERNAME and SMTP_PASSWORD:
#            server.login(SMTP_USERNAME, SMTP_PASSWORD)
#
#        server.sendmail(SMTP_FROM, recipients, msg.as_string())
#        server.quit()
#        logger.info(f"Email sent to {', '.join(recipients)} with subject: {subject}")
#
#    except Exception as e:
#        logger.error(f"Failed to send email: {e}")


# ==== Message handler ====
def on_message(ch, method, properties, body):
    try:
        outer = json.loads(body)
    except json.JSONDecodeError:
        logger.info("Non‑JSON message received")
        logger.info(body)
        return

    if "oslo.message" in outer:
        try:
            inner = json.loads(outer["oslo.message"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse oslo.message as JSON")
            return
    else:
        inner = outer

    event_type = inner.get("event_type", "")
    if event_type not in ("instance.create.end", "instance.create.error"):
        return

    payload_data = (
        inner.get("payload", {}).get("nova_object.data", {})
        if isinstance(inner.get("payload"), dict)
        else {}
    )

    logger.info(f"=== Filtered Nova Notification ({event_type}) ===")
    logger.info(json.dumps(inner, indent=2))

    if event_type == "instance.create.end":
        fault = payload_data.get("fault")
        state = payload_data.get("state")
        if fault is None and state == "active":
            user_id = payload_data.get("user_id")
            user_email = get_user_email(user_id)
            host_name = payload_data.get("host_name")
            uuid = payload_data.get("uuid")
            power_state = payload_data.get("power_state")
            ip_list = payload_data.get("ip_addresses", [])
            ip_addr = None
            if ip_list:
                ip_data = ip_list[0].get("nova_object.data", {})
                ip_addr = ip_data.get("address")
            subject = f"Nova VM Creation Success: {payload_data.get('display_name')}"
            body_text = (
                f"User ID: {user_id}\n"
                f"User Email: {user_email or 'N/A'}\n"
                f"Host Name: {host_name}\n"
                f"UUID: {uuid}\n"
                f"Power State: {power_state}\n"
                f"IP Address: {ip_addr or 'N/A'}"
            )
            send_mail(subject, body_text, to_addrs=user_email or DEFAULT_SMTP_TO)

    elif event_type == "instance.create.error":
        user_id = payload_data.get("user_id")
        user_email = get_user_email(user_id)
        host_name = payload_data.get("host_name")
        uuid = payload_data.get("uuid")
        fault_data = payload_data.get("fault", {}).get("nova_object.data", {})
        exception = fault_data.get("exception")
        exception_message = fault_data.get("exception_message")
        subject = f"Nova VM Creation Failed: {payload_data.get('display_name')}"
        body_text = (
            f"User ID: {user_id}\n"
            f"User Email: {user_email or 'N/A'}\n"
            f"Host Name: {host_name}\n"
            f"UUID: {uuid}\n"
            f"Exception: {exception}\n"
            f"Message: {exception_message}"
        )
        send_mail(subject, body_text, to_addrs=user_email or DEFAULT_SMTP_TO)


# ==== RabbitMQ connection loop ====
def connect_and_consume():
    while True:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            ssl_enabled = bool(int(os.getenv("NOVA_NOTIFY2MAIL_RABBITMQ_SSL", "0")))
            ssl_options = None
            if ssl_enabled:
                import ssl
                context = ssl._create_unverified_context()
                ssl_options = pika.SSLOptions(context, RABBITMQ_HOST)

            params = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=60,
                ssl_options=ssl_options
            )

            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            for rk in ROUTING_KEYS:
                channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=rk)
                logger.info(f"Bound queue '{QUEUE_NAME}' to '{EXCHANGE_NAME}' with routing key '{rk}'")

            logger.info(f"Connected to '{EXCHANGE_NAME}' exchange, listening for {', '.join(ROUTING_KEYS)}")
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

