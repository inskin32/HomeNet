import socket
import threading
import os
import json

# --- NODE CONFIGURATION ---
BROWSER_PORT = 8080
MY_P2P_PORT = int(input("Enter your P2P port (e.g. 9001): "))
FRIEND_PORT = input("Enter a friend node's port (leave empty if you are the first): ")

SITES_FOLDER = f"sites_node_{MY_P2P_PORT}"
os.makedirs(SITES_FOLDER, exist_ok=True)

# Create an example website if the folder is empty
example_site = os.path.join(SITES_FOLDER, f"node{MY_P2P_PORT}.homenet.html")
if not os.path.exists(example_site):
    with open(example_site, "w", encoding="utf-8") as f:
        f.write(f"<h1>Welcome to HomeNet!</h1><p>This website is hosted by the node running on port {MY_P2P_PORT}.</p>")

# List of known peer nodes (IP, Port)
PEERS = set()
if FRIEND_PORT:
    PEERS.add(("127.0.0.1", int(FRIEND_PORT)))

# --- P2P ENGINE (Communicates with other HomeNet users) ---
def handle_peer(conn):
    try:
        data = conn.recv(4096).decode('utf-8')
        message = json.loads(data)
        msg_type = message.get("type")

        # 1. Someone is searching for a .homenet website
        if msg_type == "SEARCH_SITE":
            domain = message.get("domain")
            file_path = os.path.join(SITES_FOLDER, f"{domain}.html")

            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                response = {"found": True, "html": content}
            else:
                response = {"found": False}

            conn.sendall(json.dumps(response).encode('utf-8'))

        # 2. Exchange contact information (Gossip protocol)
        elif msg_type == "PING":
            sender_port = message.get("port")
            PEERS.add(("127.0.0.1", sender_port))
            conn.sendall(json.dumps({"status": "OK", "peers": list(PEERS)}).encode('utf-8'))

    except Exception:
        pass
    finally:
        conn.close()

def start_p2p_network():
    p2p_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    p2p_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    p2p_server.bind(("0.0.0.0", MY_P2P_PORT))
    p2p_server.listen(10)

    print(f"[HomeNet P2P] Node listening on port {MY_P2P_PORT}")
    print(f"[HomeNet P2P] Place your .homenet.html files in the folder: {SITES_FOLDER}/")

    # If you entered a friend's port, introduce yourself to the network
    for ip, port in list(PEERS):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, port))
            s.sendall(json.dumps({"type": "PING", "port": MY_P2P_PORT}).encode('utf-8'))
            s.close()
        except:
            print(f"[HomeNet P2P] Unable to reach friend on port {port}")

    while True:
        conn, _ = p2p_server.accept()
        threading.Thread(target=handle_peer, args=(conn,), daemon=True).start()

# --- BROWSER PROXY (Connects your browser to HomeNet) ---
def search_network(domain):
    # First, check if the website is hosted on your own computer
    local_file = os.path.join(SITES_FOLDER, f"{domain}.html")
    if os.path.exists(local_file):
        with open(local_file, "r", encoding="utf-8") as f:
            return f.read()

    # Otherwise, ask all connected friend nodes!
    for ip, port in list(PEERS):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.sendall(json.dumps({"type": "SEARCH_SITE", "domain": domain}).encode('utf-8'))

            raw_response = s.recv(65536).decode('utf-8')
            s.close()

            response = json.loads(raw_response)
            if response.get("found"):
                return response.get("html")
        except:
            continue

    return "<h1>404 - Website not found on HomeNet</h1><p>No online node is hosting this address.</p>"

def handle_browser(client_socket):
    try:
        request = client_socket.recv(4096).decode('utf-8', errors='ignore')
        if not request:
            return

        lines = request.splitlines()
        parts = lines.pop(0).split(' ')
        if len(parts) < 2:
            return

        url = parts.pop(1)
        domain = url.replace("http://", "").replace("https://", "").split('/').pop(0).split(':').pop(0).lower()

        if domain.endswith(".homenet"):
            html = search_network(domain)
            body = html.encode('utf-8')

            header = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            client_socket.sendall(header.encode('utf-8') + body)
        else:
            msg = b"<h1>403 - Only .homenet domains are allowed</h1>"
            client_socket.sendall(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: "
                + str(len(msg)).encode()
                + b"\r\n\r\n"
                + msg
            )

    except:
        pass
    finally:
        client_socket.close()

# Start the P2P engine in the background and launch the browser proxy
threading.Thread(target=start_p2p_network, daemon=True).start()

proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
proxy.bind(("127.0.0.1", BROWSER_PORT))
proxy.listen(10)

print(f"[Browser Proxy] Running on 127.0.0.1:{BROWSER_PORT}")

while True:
    c, _ = proxy.accept()
    threading.Thread(target=handle_browser, args=(c,), daemon=True).start()