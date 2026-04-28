#!/usr/bin/env python3
"""
FaceLock Daemon for Linux/Ubuntu
Listens for face authentication requests via Unix socket
"""

import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path
from threading import Thread
from typing import Optional

# Add parent directory to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.camera_handler import CameraHandler
from modules.database import Database
from modules.face_authenticator import FaceAuthenticator
from modules.face_detector import FaceDetector
from modules.face_encoder import FaceEncoder

# Configuration
SOCKET_PATH = "/tmp/facelock_daemon.sock"
DB_PATH = "/etc/facelock/facelock.db"
LOG_PATH = "/var/log/facelock_daemon.log"
PID_FILE = "/run/facelock_daemon.pid"
AUTH_TIMEOUT = 10

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("FaceLock-Daemon")


class FaceLockDaemon:
    """Daemon that listens for face authentication requests"""
    
    def __init__(self, socket_path: str, db_path: str):
        self.socket_path = socket_path
        self.db_path = db_path
        self.running = False
        self.server_socket = None
        
        # Initialize modules
        try:
            self.camera = CameraHandler()
            self.face_detector = FaceDetector()
            self.face_encoder = FaceEncoder()
            self.face_auth = FaceAuthenticator()
            self.database = Database(db_path)
            logger.info("✓ All modules initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize modules: {e}")
            raise
    
    def setup_socket(self):
        """Create Unix domain socket"""
        try:
            # Remove existing socket
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            
            # Create socket
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)
            
            # Set permissions (readable/writable by all users for PAM)
            os.chmod(self.socket_path, 0o666)
            
            logger.info(f"✓ Socket created at {self.socket_path}")
        except Exception as e:
            logger.error(f"Failed to create socket: {e}")
            raise
    
    def handle_client(self, conn: socket.socket, addr) -> None:
        """Handle incoming authentication request"""
        try:
            # Receive request with timeout
            conn.settimeout(AUTH_TIMEOUT)
            data = conn.recv(1024).decode('utf-8').strip()
            
            logger.debug(f"Received request: {data}")
            
            # Parse request: AUTH_REQUEST:<username>
            if not data.startswith("AUTH_REQUEST:"):
                logger.warning(f"Invalid request format: {data}")
                conn.send(b"AUTH_FAILED")
                return
            
            username = data[13:]  # Skip "AUTH_REQUEST:"
            
            if not username:
                logger.warning("Empty username in request")
                conn.send(b"AUTH_FAILED")
                return
            
            # Perform face authentication
            response = self.authenticate_user(username)
            conn.send(response.encode('utf-8'))
            
        except socket.timeout:
            logger.warning(f"Socket timeout for request")
            conn.send(b"AUTH_FAILED")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            conn.send(b"AUTH_FAILED")
        finally:
            conn.close()
    
    def authenticate_user(self, username: str) -> str:
        """
        Authenticate user via facial recognition
        
        Returns:
            String: "AUTH_SUCCESS:<username>" or "AUTH_FAILED"
        """
        try:
            # Capture frame
            frame = self.camera.capture_frame()
            if frame is None:
                logger.debug(f"Failed to capture frame for {username}")
                return "AUTH_FAILED"
            
            # Detect face
            faces = self.face_detector.detect_faces(frame)
            if not faces:
                logger.debug(f"No face detected for {username}")
                return "AUTH_FAILED"
            
            # Get primary face (largest)
            face_rect = max(faces, key=lambda f: f[2] * f[3])
            
            # Extract face encoding
            face_encoding = self.face_encoder.encode_face(frame, face_rect)
            if face_encoding is None:
                logger.debug(f"Failed to encode face for {username}")
                return "AUTH_FAILED"
            
            # Check against database
            match, matched_user = self.face_auth.verify_face(face_encoding, self.database)
            
            if match and matched_user.lower() == username.lower():
                logger.info(f"✓ Face authentication successful for {username}")
                return f"AUTH_SUCCESS:{username}"
            else:
                logger.warning(f"Face authentication failed for {username} (matched: {matched_user})")
                return "AUTH_FAILED"
                
        except Exception as e:
            logger.error(f"Authentication error for {username}: {e}")
            return "AUTH_FAILED"
    
    def run(self):
        """Main daemon loop"""
        self.running = True
        logger.info("✓ FaceLock Daemon started, listening for requests...")
        
        try:
            while self.running:
                try:
                    conn, _ = self.server_socket.accept()
                    # Handle each request in a separate thread
                    thread = Thread(target=self.handle_client, args=(conn, None))
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cleanup and shutdown"""
        self.running = False
        logger.info("Shutting down...")
        
        try:
            if self.server_socket:
                self.server_socket.close()
            
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            
            logger.info("✓ Daemon shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle signals"""
        logger.info(f"Received signal {signum}")
        self.shutdown()
        sys.exit(0)


def daemonize():
    """Daemonize the process"""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Exit parent
        
        # Decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)
        
        # Second fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Exit second parent
        
        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        
        with open('/dev/null', 'r') as stdin:
            os.dup2(stdin.fileno(), sys.stdin.fileno())
        
        # Keep stdout/stderr for logging
        
    except OSError as e:
        logger.error(f"Failed to daemonize: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="FaceLock Daemon for Linux")
    parser.add_argument('--foreground', action='store_true', 
                       help='Run in foreground (don\'t daemonize)')
    parser.add_argument('--db', default=DB_PATH, 
                       help=f'Path to database (default: {DB_PATH})')
    parser.add_argument('--socket', default=SOCKET_PATH,
                       help=f'Socket path (default: {SOCKET_PATH})')
    args = parser.parse_args()
    
    # Verify database exists
    if not os.path.exists(args.db):
        logger.error(f"Database not found: {args.db}")
        logger.error("Please enroll at least one face first")
        sys.exit(1)
    
    # Daemonize unless --foreground
    if not args.foreground:
        logger.info("Daemonizing...")
        daemonize()
    
    # Write PID file
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Could not write PID file: {e}")
    
    # Create and run daemon
    try:
        daemon = FaceLockDaemon(args.socket, args.db)
        daemon.setup_socket()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, daemon.signal_handler)
        signal.signal(signal.SIGINT, daemon.signal_handler)
        
        # Run
        daemon.run()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
