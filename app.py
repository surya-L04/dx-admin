import subprocess
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import serial
import serial.tools.list_ports
import threading
import time
import re

app = Flask(__name__)

PORT = "/dev/specter-repeater"
BAUD = 115200

state = {
    "connected": False,
    "version": "Inconnue",
    "uptime": None,
    "rx": None,
    "relay": None,
    "drop": None,
    "rssi": None,
    "snr": None,
    "repeat": "Inconnu",
    "radio": {"frequency": "—", "bandwidth": "—", "sf": "—", "cr": "—"},
    "identity": {"name": "—", "owner": "—", "lat": "—", "lon": "—"},
    "neighbours": [],
    "nodes": [],
    "rooms": []
}

ser = None
identity_pending = []
radio_command_result = None
ra_clients_result = []
config_result = {}
lock = threading.Lock()
serial_pause = False

LOG_FILE = Path("/home/lolo/dx-admin/logs/dx-admin.log")

def find_dx_port():
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x1A86 and p.pid == 0x7523:
            return p.device
    return None


def write_log(message):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + message + "\n")



def serial_reader():
    global ser, identity_pending, radio_command_result
    discover_type = None

    while True:
        try:
            if ser is None or not ser.is_open:
                dx_port = find_dx_port()
                if not dx_port:
                    time.sleep(2)
                    continue

                ser = serial.Serial(dx_port, BAUD, timeout=1)
                write_log("Connexion au répéteur")
                with lock:
                    state["connected"] = True

                ser.write(b"ver\r\n")
                time.sleep(0.2)
                ser.write(b"get repeat\r\n")
                time.sleep(0.1)
                ser.write(b"get radio\r\n")
                time.sleep(1)
                time.sleep(0.1)
                identity_pending.append("name")
                ser.write(b"get name\r\n")
                time.sleep(0.1)
                identity_pending.append("owner")
                ser.write(b"get owner.info\r\n")
                time.sleep(0.1)
                identity_pending.append("lat")
                ser.write(b"get lat\r\n")
                time.sleep(0.1)
                identity_pending.append("lon")
                ser.write(b"get lon\r\n")
                time.sleep(0.1)
                ser.write(b"get telemetry\r\n")

            line = ser.readline().decode(errors="replace").strip()

            if not line:
                continue

            if line.startswith("> client "):
                with lock:
                    ra_clients_result.append(line[2:])

            if line == "OK" or line.startswith("> ERR"):
                with lock:
                    if radio_command_result is not None:
                        radio_command_result = line

            if "SPECTER MeshCore" in line:
                with lock:
                    state["version"] = line

            mradio = re.match(r"^> ([0-9.]+),([0-9.]+),([0-9]+),([0-9]+)$", line)
            if mradio:
                with lock:
                    state["radio"] = {
                        "frequency": mradio.group(1),
                        "bandwidth": mradio.group(2),
                        "sf": mradio.group(3),
                        "cr": mradio.group(4)
                    }

            if line.startswith("> ") and identity_pending:
                val = line[2:]
                field = identity_pending[0]

                if field == "name" and "SPECTER MeshCore" not in val and val not in ("on", "off") and not re.match(r"^[0-9.]+,[0-9.]+,[0-9]+,[0-9]+$", val):
                    identity_pending.pop(0)
                    with lock:
                        state["identity"]["name"] = val

                elif field == "owner" and val not in ("on", "off") and not re.match(r"^[0-9.]+,[0-9.]+,[0-9]+,[0-9]+$", val) and not re.match(r"^-?[0-9]+\.[0-9]+$", val):
                    identity_pending.pop(0)
                    with lock:
                        state["identity"]["owner"] = val

                elif field == "lat" and re.match(r"^-?[0-9]+\.[0-9]+$", val) and abs(float(val)) <= 90:
                    identity_pending.pop(0)
                    with lock:
                        state["identity"]["lat"] = val

                elif field == "lon" and re.match(r"^-?[0-9]+\.[0-9]+$", val) and abs(float(val)) <= 180:
                    identity_pending.pop(0)
                    with lock:
                        state["identity"]["lon"] = val

            if line == "> on":
                with lock:
                    state["repeat"] = "ON"
                    config_result["repeat"] = "ON"

            elif line == "> off":
                with lock:
                    state["repeat"] = "OFF"
                    config_result["repeat"] = "OFF"

            dtype = re.match(r"^DISCOVER TYPE=(\d+)$", line)
            if dtype:
                discover_type = int(dtype.group(1))

            neighbour = re.match(
                r"^DISCOVER NEIGHBOUR pub=([0-9A-Fa-f]{8}) SNR=(-?\d+)$",
                line
            )
            if neighbour:
                pub = neighbour.group(1).upper()
                snr = int(neighbour.group(2))
                item = {"pub": pub, "snr": snr, "type": discover_type, "last_seen": time.strftime("%H:%M:%S")}

                with lock:
                    existing = next(
                        (n for n in state["neighbours"] if n["pub"] == pub),
                        None
                    )
                    if existing:
                        existing.update(item)
                    else:
                        state["neighbours"].append(item)

                    state["nodes"] = [n for n in state["neighbours"] if n.get("type") == 1]
                    state["rooms"] = [n for n in state["neighbours"] if n.get("type") == 3]

            telemetry = re.match(r"^> (rssi|snr)=(-?[0-9]+)$", line)
            if telemetry:
                with lock:
                    state[telemetry.group(1)] = int(telemetry.group(2))

            match = re.search(
                r"ALIVE uptime=(\d+)s rx=(\d+) relay=(\d+) drop=(\d+)",
                line
            )

            if match:
                with lock:
                    state["uptime"] = int(match.group(1))
                    state["rx"] = int(match.group(2))
                    state["relay"] = int(match.group(3))
                    state["drop"] = int(match.group(4))
                    state["connected"] = True

        except Exception as e:
            write_log("Erreur de communication avec le répéteur: " + repr(e))
            with lock:
                state["connected"] = False

            try:
                if ser:
                    ser.close()
            except Exception:
                pass

            ser = None
            time.sleep(2)


threading.Thread(target=serial_reader, daemon=True).start()


@app.route("/")
def index():
    with lock:
        s = state.copy()

    if s["uptime"] is not None:
        minutes = s["uptime"] // 60
        seconds = s["uptime"] % 60
        uptime = f"{minutes} min {seconds} s"
    else:
        uptime = "En attente..."

    status = "🟢 Connectée" if s["connected"] else "🔴 Déconnectée"

    return render_template("index.html", state=s, status=status, uptime=uptime, radio=s["radio"], identity=s["identity"])


@app.route("/api/mesh/refresh")
def mesh_refresh():
    return jsonify({"ok": True, "message": "Mesh disponible"})


@app.route("/api/mesh/neighbours")
def mesh_neighbours():
    with lock:
        return jsonify({
            "ok": True,
            "neighbours": list(state["neighbours"])
        })


@app.route("/api/mesh/nodes")
def mesh_nodes():
    with lock:
        return jsonify({"ok": True, "nodes": list(state["nodes"])})


@app.route("/api/mesh/rooms")
def mesh_rooms():
    with lock:
        return jsonify({"ok": True, "rooms": list(state["rooms"])})

@app.route("/api/mesh/discover")
def mesh_discover():
    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503
        ser.write(b"discover.neighbors\r\n")
    return jsonify({"ok": True, "message": "Découverte lancée"})



@app.route("/api/reboot", methods=["POST"])
def reboot():
    try:
        with lock:
            if ser is None or not ser.is_open:
                return jsonify({"ok": False, "message": "Répéteur non connecté"}), 503
            ser.write(b"reboot" + bytes([13, 10]))
        write_log("Commande de redémarrage envoyée")
        return jsonify({"ok": True})
    except Exception:
        write_log("Échec de la commande de redémarrage")
        return jsonify({"ok": False, "message": "Erreur de communication"}), 500

@app.route("/api/firmware/upload", methods=["POST"])
def firmware_upload():
    upload = request.files.get("firmware")

    if upload is None or not upload.filename:
        return jsonify({
            "ok": False,
            "message": "Aucun firmware sélectionné"
        }), 400

    filename = Path(upload.filename).name

    if not filename.lower().endswith(".bin"):
        return jsonify({
            "ok": False,
            "message": "Seuls les fichiers .bin sont acceptés"
        }), 400

    data = upload.read()

    if not data:
        return jsonify({
            "ok": False,
            "message": "Fichier firmware vide"
        }), 400

    if len(data) > 128 * 1024:
        return jsonify({
            "ok": False,
            "message": "Firmware trop volumineux (maximum 128 Ko)"
        }), 400

    if b"SPECTER MeshCore Repeater" not in data:
        return jsonify({
            "ok": False,
            "message": "Firmware SPECTER non reconnu"
        }), 400

    upload_dir = Path("/home/lolo/dx-admin/uploads/firmware")
    upload_dir.mkdir(parents=True, exist_ok=True)

    target = upload_dir / filename
    target.write_bytes(data)

    write_log(f"Firmware uploadé : {filename} ({len(data)} octets)")

    return jsonify({
        "ok": True,
        "message": "Firmware reçu et vérifié",
        "filename": filename,
        "size": len(data)
    })

@app.route("/api/firmware/prepare", methods=["POST"])
def firmware_prepare():
    firmware_dir = Path("/home/lolo/dx-admin/uploads/firmware")
    firmware = firmware_dir / "firmware.bin"
    target = "/dev/specter-2"

    if not firmware.is_file():
        return jsonify({
            "ok": False,
            "message": "Aucun firmware firmware.bin disponible"
        }), 404

    size = firmware.stat().st_size

    if size == 0 or size > 128 * 1024:
        return jsonify({
            "ok": False,
            "message": "Taille du firmware invalide"
        }), 400

    data = firmware.read_bytes()

    if b"SPECTER MeshCore Repeater" not in data:
        return jsonify({
            "ok": False,
            "message": "Firmware SPECTER non reconnu"
        }), 400

    if not Path(target).exists():
        return jsonify({
            "ok": False,
            "message": "La nouvelle DX-LR30 n'est pas détectée"
        }), 503

    return jsonify({
        "ok": True,
        "filename": firmware.name,
        "size": size,
        "target": target,
        "message": "Firmware prêt pour le flash"
    })

@app.route("/api/firmware/flash", methods=["POST"])
def firmware_flash():
    global ser, serial_pause

    firmware = Path("/home/lolo/dx-admin/uploads/firmware/firmware.bin")
    target = "/dev/specter-2"

    if not firmware.is_file():
        return jsonify({
            "ok": False,
            "message": "Firmware non trouvé"
        }), 404

    data = firmware.read_bytes()

    if len(data) == 0 or len(data) > 128 * 1024:
        return jsonify({
            "ok": False,
            "message": "Taille du firmware invalide"
        }), 400

    if b"SPECTER MeshCore Repeater" not in data:
        return jsonify({
            "ok": False,
            "message": "Firmware SPECTER non reconnu"
        }), 400

    if not Path(target).exists():
        return jsonify({
            "ok": False,
            "message": "Nouvelle DX-LR30 absente"
        }), 503

    try:
        serial_pause = True

        with lock:
            if ser is not None and ser.is_open:
                ser.close()
            ser = None

        cmd = [
            "/usr/bin/stm32flash",
            "-b", "57600",
            "-w", str(firmware),
            "-v",
            "-R",
            target
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180
        )

        output = (result.stdout + "\n" + result.stderr).strip()

        if result.returncode == 0:
            write_log("Flash firmware réussi sur /dev/specter-2")
            return jsonify({
                "ok": True,
                "message": "Firmware flashé avec succès",
                "target": target,
                "output": output
            })

        write_log("Échec du flash firmware sur /dev/specter-2")
        return jsonify({
            "ok": False,
            "message": "Échec du flash firmware",
            "target": target,
            "output": output
        }), 500

    except subprocess.TimeoutExpired:
        write_log("Timeout pendant le flash firmware")
        return jsonify({
            "ok": False,
            "message": "Timeout pendant le flash"
        }), 504

    except Exception:
        write_log("Erreur pendant le flash firmware")
        return jsonify({
            "ok": False,
            "message": "Erreur pendant le flash"
        }), 500

    finally:
        serial_pause = False

@app.route("/api/backup", methods=["POST"])
def backup():
    return jsonify({
        "ok": False,
        "message": "Sauvegarde firmware non encore exécutée"
    }), 501

@app.route("/api/logs")
def logs():
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-100:]
        return jsonify({"ok": True, "logs": lines})
    except Exception:
        return jsonify({"ok": False, "logs": []}), 500


@app.route("/api/diagnostic")
def diagnostic():
    with lock:
        return jsonify({
            "ok": True,
            "diagnostic": {
                "connected": state["connected"],
                "version": state["version"],
                "uptime": state["uptime"],
                "rx": state["rx"],
                "relay": state["relay"],
                "drop": state["drop"],
                "rssi": state["rssi"],
                "snr": state["snr"],
                "repeat": state["repeat"],
                "radio": dict(state["radio"]),
                "identity": dict(state["identity"]),
                "neighbours": len(state["neighbours"])
            }
        })


@app.route("/api/identity/update", methods=["POST"])
def identity_update():
    data = request.get_json(silent=True) or {}

    allowed = {
        "name": "set name ",
        "owner": "set owner.info ",
        "lat": "set lat ",
        "lon": "set lon ",
    }

    commands = []
    for field, prefix in allowed.items():
        if field in data:
            value = str(data[field]).strip()
            if value:
                commands.append(prefix + value)

    if not commands:
        return jsonify({"ok": False, "message": "Aucune valeur à modifier"}), 400

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        for command in commands:
            ser.write((command + "\r\n").encode())
            time.sleep(0.15)

    return jsonify({"ok": True, "message": "Modification envoyée"})


@app.route("/api/radio")
def radio_get():
    with lock:
        return jsonify({"ok": True, "radio": dict(state["radio"])})
@app.route("/api/config")
def config_get():
    with lock:
        return jsonify({"ok": True, "config": {**config_result, "radio": dict(state["radio"])}})


@app.route("/api/config/restore", methods=["POST"])
def config_restore():
    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename", ""))

    if not filename.startswith("config-") or not filename.endswith(".json"):
        return jsonify({"ok": False, "message": "Fichier de sauvegarde invalide"}), 400

    backup_dir = Path.home() / "dx-admin" / "backups"
    backup_file = backup_dir / filename

    if backup_file.parent != backup_dir or not backup_file.is_file():
        return jsonify({"ok": False, "message": "Sauvegarde introuvable"}), 404

    try:
        import json
        config = json.loads(backup_file.read_text())
        repeat = str(config["repeat"]).lower()
        radio = config["radio"]

        if repeat not in ("on", "off"):
            raise ValueError("Répéteur invalide")

        frequency = float(radio["frequency"])
        bandwidth = float(radio["bandwidth"])
        sf = int(radio["sf"])
        cr = int(radio["cr"])

        if frequency <= 0 or bandwidth <= 0 or not 5 <= sf <= 12 or not 5 <= cr <= 8:
            raise ValueError("Valeurs radio hors limites")

    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return jsonify({"ok": False, "message": "Sauvegarde invalide"}), 400

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ser.write((f"set repeat {repeat}\r\n").encode())
        time.sleep(0.2)
        ser.write((f"set radio {frequency:.3f},{bandwidth:.1f},{sf},{cr}\r\n").encode())

    return jsonify({
        "ok": True,
        "message": f"Configuration restaurée depuis {filename}"
    })


@app.route("/api/config/import", methods=["POST"])
def config_import():
    import json
    from datetime import datetime

    if "file" not in request.files:
        return jsonify({"ok": False, "message": "Aucun fichier reçu"}), 400

    uploaded = request.files["file"]

    if not uploaded.filename or not uploaded.filename.lower().endswith(".json"):
        return jsonify({"ok": False, "message": "Fichier JSON invalide"}), 400

    try:
        config = json.load(uploaded.stream)

        repeat = str(config["repeat"]).lower()
        radio = config["radio"]

        if repeat not in ("on", "off"):
            raise ValueError

        frequency = float(radio["frequency"])
        bandwidth = float(radio["bandwidth"])
        sf = int(radio["sf"])
        cr = int(radio["cr"])

        if frequency <= 0 or bandwidth <= 0 or not 5 <= sf <= 12 or not 5 <= cr <= 8:
            raise ValueError

    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return jsonify({"ok": False, "message": "Configuration JSON invalide"}), 400

    backup_dir = Path.home() / "dx-admin" / "backups"
    backup_dir.mkdir(exist_ok=True)

    backup_file = backup_dir / (
        f"config-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    backup_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False)
    )

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ser.write((f"set repeat {repeat}\\r\\n").encode())
        time.sleep(0.2)
        ser.write(
            (f"set radio {frequency:.3f},{bandwidth:.1f},{sf},{cr}\\r\\n").encode()
        )

    return jsonify({
        "ok": True,
        "message": "Configuration importée avec succès"
    })


@app.route("/api/config/backups")
def config_backups():
    backup_dir = Path.home() / "dx-admin" / "backups"
    backup_dir.mkdir(exist_ok=True)

    backups = sorted(
        [p.name for p in backup_dir.glob("config-*.json")],
        reverse=True
    )

    return jsonify({"ok": True, "backups": backups})


@app.route("/api/config/save", methods=["POST"])
def config_save():
    from datetime import datetime
    import json

    with lock:
        config = {
            "repeat": config_result.get("repeat", state["repeat"]),
            "radio": dict(state["radio"]),
        }

    backup_dir = Path.home() / "dx-admin" / "backups"
    backup_dir.mkdir(exist_ok=True)

    filename = backup_dir / f"config-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json"
    filename.write_text(json.dumps(config, indent=2, ensure_ascii=False))

    return jsonify({
        "ok": True,
        "message": f"Configuration sauvegardée : {filename.name}"
    })


@app.route("/api/telemetry")
def telemetry_get():
    with lock:
        return jsonify({
            "ok": True,
            "telemetry": {
                "uptime": state["uptime"],
                "rx": state["rx"],
                "relay": state["relay"],
                "drop": state["drop"],
                "rssi": state["rssi"],
                "snr": state["snr"]
                ,"version": state["version"]
            }
        })

@app.route("/api/admin/clients")
def admin_clients():
    global ra_clients_result
    with lock:
        ra_clients_result.clear()
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503
        ser.write(b"get ra.clients\r\n")

    time.sleep(0.5)

    with lock:
        clients = []
        for client in ra_clients_result:
            print("DEBUG RA CLIENT:", repr(client[:12]), "len=", len(client))
            parts = client.split()
            if len(parts) >= 3 and len(parts[2]) == 64:
                masked = parts[2][:8] + "…" + parts[2][-8:]
                parts[2] = masked
            clients.append(" ".join(parts))

        return jsonify({"ok": True, "clients": clients})


@app.route("/api/admin/password", methods=["POST"])
def admin_password():
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", ""))

    if len(password) < 8 or len(password) > 32:
        return jsonify({
            "ok": False,
            "message": "Le mot de passe doit contenir entre 8 et 32 caractères"
        }), 400

    if any(c in password for c in "\r\n"):
        return jsonify({
            "ok": False,
            "message": "Mot de passe invalide"
        }), 400

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({
                "ok": False,
                "message": "DX déconnectée"
            }), 503

        ser.write(("set password " + password + "\r\n").encode())

    time.sleep(0.8)

    return jsonify({
        "ok": True,
        "message": "Mot de passe Remote Admin modifié"
    })


@app.route("/api/admin/add-client", methods=["POST"])
def admin_add_client():
    data = request.get_json(silent=True) or {}
    pubkey = str(data.get("pubkey", "")).strip()

    if len(pubkey) != 64 or any(c not in "0123456789abcdefABCDEF" for c in pubkey):
        return jsonify({"ok": False, "message": "Clé publique invalide"}), 400

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ser.write(("ra.add " + pubkey + "\r\n").encode())

    time.sleep(0.8)

    with lock:
        return jsonify({"ok": True, "message": "Commande d'ajout envoyée"})


@app.route("/api/admin/remove-client", methods=["POST"])
def admin_remove_client():
    data = request.get_json(silent=True) or {}
    client_id = str(data.get("client", "")).strip()

    if not client_id.isdigit() or int(client_id) < 1 or int(client_id) > 4:
        return jsonify({"ok": False, "message": "Numéro de client invalide"}), 400

    client_num = int(client_id)

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ra_clients_result.clear()
        ser.write(b"get ra.clients\r\n")

    time.sleep(0.5)

    with lock:
        target = None
        for client in ra_clients_result:
            parts = client.split()
            if len(parts) >= 3 and parts[1].rstrip(":") == str(client_num):
                target = parts[2]
                break

        if not target or len(target) != 64:
            return jsonify({"ok": False, "message": "Client introuvable"}), 404

        ser.write(("ra.remove " + target + "\r\n").encode())

    time.sleep(0.8)

    return jsonify({"ok": True, "message": "Commande de suppression envoyée"})


@app.route("/api/admin/check-client", methods=["POST"])
def admin_check_client():
    data = request.get_json(silent=True) or {}
    client_id = str(data.get("client", "")).strip()

    if not client_id.isdigit() or int(client_id) < 1 or int(client_id) > 4:
        return jsonify({"ok": False, "message": "Numéro de client invalide"}), 400

    client_num = int(client_id)

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ra_clients_result.clear()
        ser.write(b"get ra.clients\r\n")

    time.sleep(0.5)

    with lock:
        for client in ra_clients_result:
            parts = client.split()
            if len(parts) >= 3 and parts[1].rstrip(":") == str(client_num):
                return jsonify({"ok": True, "exists": True})

        return jsonify({"ok": True, "exists": False})


@app.route("/api/repeater")
def repeater_get():
    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503
        ser.write(b"get repeat\r\n")
        return jsonify({"ok": True, "repeat": state["repeat"]})


@app.route("/api/repeater/update", methods=["POST"])
def repeater_update():
    data = request.get_json(silent=True) or {}
    action = str(data.get("repeat", "")).lower()

    if action not in ("on", "off"):
        return jsonify({"ok": False, "message": "Commande répéteur invalide"}), 400

    command = f"set repeat {action}"

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        ser.write((command + "\r\n").encode())

    return jsonify({
        "ok": True,
        "message": f"Répétition {action.upper()} demandée"
    })


@app.route("/api/radio/update", methods=["POST"])
def radio_update():
    global radio_command_result

    data = request.get_json(silent=True) or {}

    try:
        frequency = float(data["frequency"])
        bandwidth = float(data["bandwidth"])
        sf = int(data["sf"])
        cr = int(data["cr"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "Paramètres radio invalides"}), 400

    if frequency <= 0 or bandwidth <= 0 or not 5 <= sf <= 12 or not 5 <= cr <= 8:
        return jsonify({"ok": False, "message": "Valeurs radio hors limites"}), 400

    command = f"set radio {frequency:.3f},{bandwidth:.1f},{sf},{cr}"

    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        radio_command_result = "pending"
        ser.write((command + "\r\n").encode())

    deadline = time.time() + 3.0

    while time.time() < deadline:
        with lock:
            result = radio_command_result

        if result == "OK":
            return jsonify({
                "ok": True,
                "message": "Configuration radio enregistrée. La DX redémarre.",
            })

        if result and result.startswith("> ERR"):
            return jsonify({
                "ok": False,
                "message": "Le firmware a refusé la configuration : " + result
            }), 400

        time.sleep(0.05)

    with lock:
        radio_command_result = None

    return jsonify({
        "ok": False,
        "message": "Aucune confirmation du firmware reçue dans le délai imparti."
    }), 504


@app.route("/api/identity")
def identity_get():
    with lock:
        return jsonify({"ok": True, "identity": dict(state["identity"])})

@app.route("/api/identity/refresh")
def identity_refresh():
    with lock:
        if ser is None or not ser.is_open:
            return jsonify({"ok": False, "message": "DX déconnectée"}), 503

        identity_pending.clear()
        identity_pending.append("name")
        ser.write(b"get name\r\n")
        time.sleep(0.1)
        identity_pending.append("owner")
        ser.write(b"get owner.info\r\n")
        time.sleep(0.1)
        identity_pending.append("lat")
        ser.write(b"get lat\r\n")
        time.sleep(0.1)
        identity_pending.append("lon")
        ser.write(b"get lon\r\n")

    return jsonify({"ok": True, "message": "Identification actualisée"})


app.run(host="0.0.0.0", port=8085)
