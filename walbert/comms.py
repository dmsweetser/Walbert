"""
Network communication module for Walbert-to-Walbert interaction.
Uses TCP-based IP scanning and handshake negotiation for peer discovery.
Fixed to avoid blocking the main thread on startup.
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
        self.known_peers: Dict[str, int] = {}  # ip:port
        self.peer_last_seen: Dict[str, float] = {}  # ip:timestamp
        self.received_messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._tcp_thread = None
        self._scan_thread = None
        self.local_ip = self._get_local_ip()
        self.network_prefix = self._get_network_prefix()
        self.handshake_message = "WALBERT_HANDSHAKE"
        self.handshake_response = "WALBERT_CONFIRM"
        self.scan_interval = 60  # seconds

    def _get_local_ip(self) -> Optional[str]:
        """Get the first non-loopback IPv4 address of the machine."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            pass
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

    def _get_network_prefix(self) -> str:
        """Extract network prefix (first 3 octets) from local IP."""
        if not self.local_ip or self.local_ip == "0.0.0.0":
            return ""
        parts = self.local_ip.split('.')
        return '.'.join(parts[:3])

    def start(self):
        """Start TCP listener and network scanning threads (non-blocking)."""
        if self._running:
            logger.warning("NetworkManager is already running")
            return

        self._running = True
        self._tcp_thread = threading.Thread(target=self._listen_tcp, daemon=True)
        self._tcp_thread.start()

        # Start the scan thread (it will run the initial scan asynchronously)
        self._scan_thread = threading.Thread(target=self._periodic_scan, daemon=True)
        self._scan_thread.start()

        logger.info(f"NetworkManager started on port {self.port}")

    def stop(self):
        """Stop network listeners."""
        self._running = False
        if self._tcp_thread:
            self._tcp_thread.join(timeout=2)
        if self._scan_thread:
            self._scan_thread.join(timeout=2)
        logger.info("NetworkManager stopped")

    def _periodic_scan(self):
        """Run network scan periodically."""
        while self._running:
            self._scan_network()
            # Sleep for scan_interval, but check _running every second
            for _ in range(self.scan_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _scan_network(self, timeout: float = 0.5, max_threads: int = 20):
        """Scan the local network for Walbert peers using TCP handshake."""
        if not self.network_prefix:
            logger.warning("Cannot scan network: no valid local IP")
            return

        discovered_peers = {}
        semaphore = threading.Semaphore(max_threads)

        def scan_ip(ip: str):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect((ip, self.port))

                # Send handshake
                sock.sendall(self.handshake_message.encode() + b"\n")
                response = sock.recv(1024).decode().strip()

                if response == self.handshake_response:
                    with self._lock:
                        discovered_peers[ip] = self.port
                    logger.info(f"Discovered Walbert peer at {ip}:{self.port}")
                sock.close()
            except Exception:
                pass
            finally:
                semaphore.release()

        # Scan all IPs in the subnet (skip network and broadcast addresses)
        for i in range(1, 255):
            ip = f"{self.network_prefix}.{i}"
            if ip == self.local_ip:
                continue  # Skip self

            semaphore.acquire()
            threading.Thread(target=scan_ip, args=(ip,), daemon=True).start()

        # Wait for all threads to complete
        for _ in range(254):
            try:
                semaphore.acquire(timeout=1)
            except:
                break

        # Update known peers
        with self._lock:
            for ip, port in discovered_peers.items():
                self.known_peers[ip] = port
                self.peer_last_seen[ip] = time.time()

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
            logger.info(f"Received from {addr}: {raw_message}")

            # Handle handshake
            if raw_message == self.handshake_message:
                client.sendall(self.handshake_response.encode() + b"\n")
                logger.info(f"Responded to handshake from {addr}")
                # Add to peers if not already present
                with self._lock:
                    if addr[0] not in self.known_peers:
                        self.known_peers[addr[0]] = self.port
                        self.peer_last_seen[addr[0]] = time.time()
                        logger.info(f"Added peer from handshake: {addr[0]}:{self.port}")
                return

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