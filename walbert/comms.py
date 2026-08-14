"""
Network communication module for Walbert-to-Walbert interaction.
Handles UDP discovery and TCP request/response messaging.
"""
import socket
import threading
import json
import logging
import time
from typing import List, Optional, Dict, Any

logger = logging.getLogger('walbert.comms')


class NetworkManager:
    def __init__(self, config):
        self.config = config
        self.host = "0.0.0.0"
        self.port = config.walbert_port
        self.udp_port = config.udp_port
        self.broadcast_addr = "<broadcast>"
        self.known_peers: Dict[str, int] = {}  # ip:port
        self.peer_last_seen: Dict[str, float] = {}  # ip:timestamp
        self.received_messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._udp_thread = None
        self._tcp_thread = None

    def _get_local_ip(self) -> Optional[str]:
        """Get the first non-loopback IPv4 address of the machine."""
        try:
            # Try connecting to a public DNS server to get the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            pass

        # Fallback: use socket.gethostbyname_ex for all IPs
        try:
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]
            for ip in ip_list:
                if not ip.startswith('127.'):
                    return ip
        except Exception:
            pass

        logger.warning("Could not determine local IP address, using 0.0.0.0")
        return "0.0.0.0"

    def start(self):
        """Start UDP discovery and TCP listener threads."""
        if self._running:
            logger.warning("NetworkManager is already running")
            return

        self._running = True
        self._udp_thread = threading.Thread(target=self._listen_udp, daemon=True)
        self._tcp_thread = threading.Thread(target=self._listen_tcp, daemon=True)

        self._udp_thread.start()
        self._tcp_thread.start()

        # Give threads a moment to start
        time.sleep(0.1)
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

    def _announce(self, retries: int = 3):
        """Broadcast presence via UDP using the actual network IP."""
        local_ip = self._get_local_ip()
        if not local_ip or local_ip == "0.0.0.0":
            logger.warning("Cannot announce with invalid IP address")
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = f"WALBERT_PEER:{local_ip}:{self.port}"

        for attempt in range(retries):
            try:
                sock.sendto(payload.encode(), (self.broadcast_addr, self.udp_port))
                logger.info(f"Announced presence as {local_ip}:{self.port} (attempt {attempt + 1}/{retries})")
                break
            except Exception as e:
                if attempt == retries - 1:
                    logger.warning(f"UDP broadcast failed after {retries} attempts: {e}")
                time.sleep(0.5)
        sock.close()

    def _listen_udp(self):
        """Listen for UDP discovery announcements."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SOL_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.udp_port))
        except OSError as e:
            logger.error(f"UDP bind failed: {e}")
            return

        sock.settimeout(1.0)
        while self._running:
            try:
                data, addr = sock.recvfrom(1024)
                msg = data.decode().strip()
                if msg.startswith("WALBERT_PEER:"):
                    parts = msg.split(":")
                    if len(parts) == 3:
                        peer_ip = parts[1]
                        peer_port = int(parts[2])
                        with self._lock:
                            if peer_ip != self._get_local_ip():
                                self.known_peers[peer_ip] = peer_port
                                self.peer_last_seen[peer_ip] = time.time()
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
        try:
            server.bind((self.host, self.port))
        except OSError as e:
            logger.error(f"TCP bind failed: {e}")
            return

        server.listen(5)
        server.settimeout(1.0)

        while self._running:
            try:
                client, addr = server.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client, addr),
                    daemon=True
                ).start()
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

            # Process request and send response
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

    def send_to_peer(self, peer_ip: str, message: str, port: Optional[int] = None, retries: int = 3) -> Optional[str]:
        """Send a raw message string to a specific peer and wait for response."""
        target_port = port or self.known_peers.get(peer_ip)
        if not target_port:
            logger.warning(f"No known port for peer {peer_ip}, using default {self.port}")
            target_port = self.port

        for attempt in range(retries):
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
                if attempt == retries - 1:
                    logger.error(f"Failed to send to {peer_ip}:{target_port} after {retries} attempts: {e}")
                    return None
                time.sleep(1)
            finally:
                sock.close()
        return None

    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """Get and clear all pending received messages."""
        with self._lock:
            pending = self.received_messages.copy()
            self.received_messages.clear()
        return pending

    def get_peer_list(self) -> List[str]:
        """Get list of all known peer IP addresses."""
        with self._lock:
            return list(self.known_peers.keys())

    def cleanup_peers(self, timeout: int = 30):
        """Remove peers that haven't been seen for `timeout` seconds."""
        current_time = time.time()
        with self._lock:
            stale_peers = [
                ip for ip, last_seen in self.peer_last_seen.items()
                if current_time - last_seen > timeout
            ]
            for ip in stale_peers:
                self.known_peers.pop(ip, None)
                self.peer_last_seen.pop(ip, None)
                logger.info(f"Removed stale peer: {ip}")