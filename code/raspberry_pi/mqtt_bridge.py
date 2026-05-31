import json
import logging
import os
import queue
import socket
import threading
import time
from dataclasses import dataclass

from smarthome_config import (
    AWS_ENABLED,
    AWS_ENDPOINT,
    AWS_PORT,
    AWS_CLIENT_ID_PREFIX,
    CA_CERT,
    DEVICE_CERT,
    PRIVATE_KEY,
    LOCAL_MQTT_ENABLED,
    LOCAL_MQTT_HOST,
    LOCAL_MQTT_PORT,
    MQTT_KEEPALIVE,
    MQTT_QUEUE_SIZE,
    MQTT_RECONNECT_MAX,
    MQTT_RECONNECT_MIN,
)

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    mqtt = None
    MQTT_AVAILABLE = False


log = logging.getLogger("mqtt_bridge")


@dataclass
class MqttCommand:
    source: str
    topic: str
    payload: str
    timestamp: float


@dataclass
class _PublishItem:
    topic: str
    payload: str
    qos: int
    retain: bool
    local: bool
    aws: bool


def _safe_id_part(text):
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text)


def make_client_id(role, cloud=False):
    host = _safe_id_part(socket.gethostname() or "pi")
    role = _safe_id_part(role)
    pid = os.getpid()
    if cloud:
        prefix = _safe_id_part(AWS_CLIENT_ID_PREFIX)
    else:
        prefix = "smarthome-local"
    return f"{prefix}-{role}-{host}-{pid}"[:120]


def mqtt_payload(payload):
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


class DualMqttBridge:
    """
    Nonblocking MQTT bridge for local Mosquitto + AWS IoT.

    Callbacks only enqueue inbound commands. Publishing is handled by a worker
    thread so UART, camera, and recognition loops are never blocked by cloud
    reconnects or DNS/TLS stalls.
    """

    def __init__(self, role, subscribe_topics=()):
        self.role = role
        self.subscribe_topics = tuple(subscribe_topics)
        self.local_client = None
        self.aws_client = None
        self.local_connected = False
        self.aws_connected = False
        self._outbox = queue.Queue(maxsize=MQTT_QUEUE_SIZE)
        self._commands = queue.Queue(maxsize=100)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._publish_worker, daemon=True)
        self._lock = threading.Lock()

    @property
    def available(self):
        return MQTT_AVAILABLE

    @property
    def connected(self):
        return self.local_connected or self.aws_connected

    def status(self):
        return {
            "mqtt_connected": self.connected,
            "local_mqtt_connected": self.local_connected,
            "aws_mqtt_connected": self.aws_connected,
        }

    def start(self):
        if not MQTT_AVAILABLE:
            log.warning("paho-mqtt is not installed; MQTT disabled")
            return

        self._worker.start()
        self._start_local()
        self._start_aws()

    def stop(self):
        self._stop.set()
        for client in (self.local_client, self.aws_client):
            if client is None:
                continue
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                log.exception("MQTT client shutdown failed")

    def publish(self, topic, payload, qos=1, retain=False, local=True, aws=True):
        item = _PublishItem(
            topic=topic,
            payload=mqtt_payload(payload),
            qos=int(qos),
            retain=bool(retain),
            local=bool(local),
            aws=bool(aws),
        )
        self._put_drop_oldest(self._outbox, item, "publish")

    def get_command(self, timeout=0.0):
        try:
            return self._commands.get(timeout=timeout)
        except queue.Empty:
            return None

    def _new_client(self, client_id):
        kwargs = {"client_id": client_id, "userdata": {"role": self.role}}
        if hasattr(mqtt, "CallbackAPIVersion"):
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION1
        client = mqtt.Client(**kwargs)
        client.reconnect_delay_set(min_delay=MQTT_RECONNECT_MIN, max_delay=MQTT_RECONNECT_MAX)
        client.max_inflight_messages_set(20)
        client.max_queued_messages_set(MQTT_QUEUE_SIZE)
        client.on_message = self._on_message
        return client

    def _start_local(self):
        if not LOCAL_MQTT_ENABLED:
            log.info("Local MQTT disabled")
            return

        client = self._new_client(make_client_id(self.role, cloud=False))
        client.on_connect = self._on_local_connect
        client.on_disconnect = self._on_local_disconnect
        self.local_client = client

        try:
            client.connect_async(LOCAL_MQTT_HOST, LOCAL_MQTT_PORT, MQTT_KEEPALIVE)
            client.loop_start()
            log.info("Local MQTT starting at %s:%s", LOCAL_MQTT_HOST, LOCAL_MQTT_PORT)
        except Exception as exc:
            log.error("Local MQTT startup failed; local control code still runs: %s", exc)

    def _start_aws(self):
        if not AWS_ENABLED:
            log.info("AWS MQTT disabled")
            return

        missing = [path for path in (CA_CERT, DEVICE_CERT, PRIVATE_KEY) if not os.path.exists(path)]
        if missing:
            log.error("AWS MQTT disabled because cert files are missing: %s", missing)
            return

        client = self._new_client(make_client_id(self.role, cloud=True))
        client.on_connect = self._on_aws_connect
        client.on_disconnect = self._on_aws_disconnect
        self.aws_client = client

        try:
            client.tls_set(ca_certs=CA_CERT, certfile=DEVICE_CERT, keyfile=PRIVATE_KEY)
            client.connect_async(AWS_ENDPOINT, AWS_PORT, MQTT_KEEPALIVE)
            client.loop_start()
            log.info("AWS MQTT starting at %s:%s", AWS_ENDPOINT, AWS_PORT)
        except Exception as exc:
            log.error("AWS MQTT startup failed; local MQTT will keep working: %s", exc)

    def _subscribe_commands(self, client, source):
        for topic in self.subscribe_topics:
            try:
                client.subscribe(topic, qos=1)
                log.info("%s subscribed: %s", source, topic)
            except Exception:
                log.exception("%s subscribe failed for %s", source, topic)

    def _on_local_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.local_connected = True
            log.info("Connected to LOCAL MQTT")
            self._subscribe_commands(client, "LOCAL")
        else:
            log.error("LOCAL MQTT connect failed rc=%s", rc)

    def _on_local_disconnect(self, client, userdata, rc):
        self.local_connected = False
        if rc:
            log.warning("LOCAL MQTT disconnected rc=%s; paho will reconnect", rc)
        else:
            log.info("LOCAL MQTT disconnected cleanly")

    def _on_aws_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.aws_connected = True
            log.info("Connected to AWS IoT MQTT")
            self._subscribe_commands(client, "AWS")
        else:
            log.error("AWS MQTT connect failed rc=%s", rc)

    def _on_aws_disconnect(self, client, userdata, rc):
        self.aws_connected = False
        if rc:
            log.warning("AWS MQTT disconnected rc=%s; paho will reconnect", rc)
        else:
            log.info("AWS MQTT disconnected cleanly")

    def _on_message(self, client, userdata, msg):
        source = "aws" if client is self.aws_client else "local"
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        command = MqttCommand(
            source=source,
            topic=msg.topic,
            payload=payload,
            timestamp=time.time(),
        )
        self._put_drop_oldest(self._commands, command, "command")

    def _publish_worker(self):
        while not self._stop.is_set():
            try:
                item = self._outbox.get(timeout=0.2)
            except queue.Empty:
                continue

            if item.local and self.local_client is not None and self.local_connected:
                self._publish_one(self.local_client, "LOCAL", item)
            if item.aws and self.aws_client is not None and self.aws_connected:
                self._publish_one(self.aws_client, "AWS", item)

    def _publish_one(self, client, source, item):
        try:
            info = client.publish(item.topic, item.payload, qos=item.qos, retain=item.retain)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                log.warning("%s publish queued with rc=%s topic=%s", source, info.rc, item.topic)
        except Exception:
            log.exception("%s publish failed topic=%s", source, item.topic)

    @staticmethod
    def _put_drop_oldest(q, item, label):
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            q.get_nowait()
        except queue.Empty:
            pass

        try:
            q.put_nowait(item)
            log.warning("MQTT %s queue was full; dropped oldest item", label)
        except queue.Full:
            log.error("MQTT %s queue is full; dropped newest item", label)
