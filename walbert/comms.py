"""
Network communication module for Walbert-to-Walbert interaction.
Handles UDP discovery and TCP request/response messaging.
"""
import socket
import threading
import json
import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger('walbert.comms')

class NetworkManager:
    def __init__(self, config):
        self.config = config
        self.host = "0.0.0.0"
        self.port = config.walbert_port
        self.udp_port = config.udp_port
        self.broadcast_addr = "<broadcast>"
        self.known_peers: Dict[str, int] = {}  # ip:port
        self.received_messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._udp_thread = None
        self._tcp_thread = None

    def start(self):
        """Start UDP discovery and TCP listener threads."""
        self._running = True
        self._udp_thread = threading.Thread(target=self._listen_udp, daemon=True)
        self._udp_thread.start()
        self._tcp_thread = threading.Thread(target=self._listen_tcp, daemon=True)
        self._tcp_thread.start()
        self._announce()
        logger.info(f"NetworkManager started on port {self.port}")

    def stop(self):
        """Stop network listeners."""
        self._running = False
        if self._udp_thread:
            self._udp_thread.join(timeout=2)
        if self._tcp_thread:
            self._tcp_thread.join(timeout=2)
        logger.info("NetworkManager stopped")

    def _announce(self):
        """Broadcast presence via UDP."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({"type": "announce", "host": "0.0.0.0", "port": self.port})
        try:
            sock.sendto(payload.encode(), (self.broadcast_addr, self.udp_port))
        except Exception as e:
            logger.warning(f"UDP broadcast failed: {e}")
        finally:
            sock.close()

    def get_peer_list(self) -> List[str]:
        """Return list of discovered peer IPs."""
        with self._lock:
            return list(self.known_peers.keys())

    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """Return and clear pending incoming messages."""
        with self._lock:
            msgs = self.received_messages.copy()
            self.received_messages.clear()
            return msgs

    def _listen_udp(self):
        """Listen for UDP discovery announcements."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", self.udp_port))
        sock.settimeout(1.0)

        while self._running:
            try:
                data, addr = sock.recvfrom(1024)
                msg = json.loads(data.decode())
                if msg["type"] == "announce":
                    peer_ip = addr[0]
                    peer_port = msg["port"]
                    with self._lock:
                        self.known_peers[peer_ip] = peer_port
                    logger.info(f"Discovered peer: {peer_ip}:{peer_port}")
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"UDP listen error: {e}")
        sock.close()

    def _listen_tcp(self):
        """Listen for TCP request/response messages."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        server.settimeout(1.0)

        while self._running:
            try:
                client, addr = server.accept()
                threading.Thread(target=self._handle_client, args=(client, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"TCP accept error: {e}")
        server.close()

    def _handle_client(self, client: socket.socket, addr: tuple):
        """Handle incoming TCP request/response."""
        try:
            client.settimeout(10.0)
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            if not data:
                return

            raw_message = data.decode().strip()
            logger.info(f"Received request from {addr}: {raw_message}")

            # Store incoming message for agent processing
            with self._lock:
                self.received_messages.append({
                    "peer_ip": addr[0],
                    "data": raw_message,
                    "timestamp": time.time()
                })

            # Process request (placeholder for actual logic)
            response = {
                "status": "ok",
                "message": "Request received and processed by Walbert",
                "timestamp": time.time()
            }

            client.sendall(json.dumps(response).encode() + b"\n")
        except Exception as e:
            logger.error(f"Client handling error: {e}")
        finally:
            client.close()

    def send_to_peer(self, peer_ip: str, message: str, port: Optional[int] = None) -> Optional[str]:
        """Send a raw message string to a specific peer and wait for response."""
        target_port = port or self.known_peers.get(peer_ip, self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        try:
            sock.connect((peer_ip, target_port))
            sock.sendall(message.encode() + b"\n")
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break
            response = response_data.decode().strip()
            logger.info(f"Received response from {peer_ip}:{target_port}")
            return response
        except Exception as e:
            logger.error(f"Failed to send to {peer_ip}:{target_port} - {e}")
            return None
        finally:
            sock.close()

    def get_peer_list(self) -> List[str]:
        """Return list of discovered peer IPs."""
        with self._lock:
            return list(self.known_peers.keys())

    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """Return and clear pending incoming messages."""
        with self._lock:
            msgs = self.received_messages.copy()
            self.received_messages.clear()
            return msgs