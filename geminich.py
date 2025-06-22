from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests
import json
import os
import datetime # Untuk timestamp jika menyimpan ke file JSON

# --- KONFIGURASI FLASK DAN LOKASI FILE ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'html'),
    static_folder=os.path.join(BASE_DIR, 'css'), # Arahkan Flask ke folder CSS Anda
    static_url_path='/css' # URL path untuk mengakses file-file di folder static
)
app.secret_key = 'supersecretkey_anda_disini' # Ganti dengan kunci rahasia yang kuat!
# Dibutuhkan untuk session (login)

# --- KONFIGURASI ESP32 ---
ESP32_IP = "192.168.1.100" # Ganti dengan IP Address ESP32 Anda
# --- AKHIR KONFIGURASI ---

# Variabel global untuk menyimpan data terakhir dari ESP32 dan pengaturan target
last_esp32_data = {
    "bus_voltage": 0.0, "shunt_voltage": 0.0, "load_voltage": 0.0, "current_mA": 0.0,
    "target_voltage": 7.0, "target_current": 500.0, "relay_status": "OFF"
}

# --- KREDENSIAL LOGIN (Untuk Contoh Sederhana) ---
VALID_USERNAME = "user"
VALID_PASSWORD = "password"

# ==============================================================================
#                      FUNGSI UNTUK MANAJEMEN DATA JSON LOKAL (Opsional)
# ==============================================================================

def save_data_to_json(filename, data_to_save):
    """Menyimpan data ke file JSON."""
    filepath = os.path.join(BASE_DIR, filename)
    try:
        with open(filepath, 'a') as f: # Mode 'a' untuk append
            json.dump(data_to_save, f)
            f.write('\n') # Tambahkan newline untuk setiap entri
        print(f"Data saved to {filename}")
    except Exception as e:
        print(f"Error saving data to {filename}: {e}")

# ==============================================================================
#                               ROUTES
# ==============================================================================

# --- Route Halaman Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard')) # Redirect ke dashboard jika sukses
        else:
            # Render ulang halaman login dengan pesan error
            return render_template('login.html', error="Invalid Username or Password"), 401
    return render_template('login.html')

# --- Route Halaman Dashboard (Membutuhkan Login) ---
@app.route('/') # Atau @app.route('/dashboard') jika ingin URLnya berbeda
def dashboard():
    # Periksa status login
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    global last_esp32_data
    try:
        response = requests.get(f"http://{ESP32_IP}/data", timeout=2)
        if response.status_code == 200:
            last_esp32_data.update(response.json())
        else:
            print(f"Error fetching initial data from ESP32: HTTP {response.status_code}")
    except (requests.exceptions.ConnectionError, json.JSONDecodeError, requests.exceptions.Timeout) as e:
        print(f"Could not connect to ESP32 for initial data: {e}. Using defaults.")
    
    return render_template('dashboard.html', data=last_esp32_data, esp32_ip=ESP32_IP)

# --- Route Logout ---
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# ==============================================================================
#                  API ROUTES: INTERAKSI DENGAN ESP32 (WEB MENGIRIM/MENERIMA)
# ==============================================================================

# Fungsi: Web Mengirim Data (Pengaturan Output Buck-Boost)
@app.route('/update_output_params', methods=['POST'])
def update_output_params():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    if request.is_json:
        data = request.get_json()
        target_voltage = data.get('voltage')
        target_current = data.get('current')

        if target_voltage is None: 
            return jsonify({"error": "Missing voltage parameter"}), 400
        
        try:
            target_voltage = float(target_voltage)
            target_current = float(target_current)
        except (ValueError, TypeError):
             return jsonify({"error": "Invalid voltage or current format"}), 400

        try:
            # Kirim data ke ESP32 sebagai form data (sesuai ESP32 WebServer.arg())
            esp32_response = requests.post(
                f"http://{ESP32_IP}/set_output_params",
                data={'voltage': target_voltage, 'current': target_current},
                timeout=2
            )
            if esp32_response.status_code == 200:
                print(f"Output parameters sent to ESP32: Voltage={target_voltage}V, Current={target_current}mA")
                last_esp32_data['target_voltage'] = target_voltage
                last_esp32_data['target_current'] = target_current
                
                # Opsional: Simpan perintah ke command.json
                command_log = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": "set_output",
                    "voltage": target_voltage,
                    "current": target_current,
                    "status": "success"
                }
                save_data_to_json('command.json', command_log)

                return jsonify({"message": "Parameters updated successfully"}), 200
            else:
                return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "Could not connect to ESP32. Check IP address and network."}), 500
        except requests.exceptions.Timeout:
            return jsonify({"error": "Timeout connecting to ESP32."}), 500
    return jsonify({"error": "Request must be JSON"}), 400

# Fungsi: Web Mengirim Data (Kontrol Relay)
@app.route('/control_relay', methods=['POST'])
def control_relay():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    if request.is_json:
        data = request.get_json()
        status = data.get('status')

        if status not in ['on', 'off']:
            return jsonify({"error": "Invalid relay status. Must be 'on' or 'off'."}), 400

        try:
            esp32_response = requests.post(
                f"http://{ESP32_IP}/control_relay",
                data={'status': status},
                timeout=2
            )
            if esp32_response.status_code == 200:
                last_esp32_data['relay_status'] = status.upper()
                
                # Opsional: Simpan perintah ke command.json
                command_log = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": "control_relay",
                    "status": status.upper(),
                    "result": "success"
                }
                save_data_to_json('command.json', command_log)

                return jsonify({"message": f"Relay set to {status.upper()}"}), 200
            else:
                return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "Could not connect to ESP32. Check IP address and network."}), 500
        except requests.exceptions.Timeout:
            return jsonify({"error": "Timeout connecting to ESP32."}), 500
    return jsonify({"error": "Request must be JSON"}), 400

# Fungsi: Web Menerima Data (Data Live dari ESP32)
# Ini adalah endpoint yang akan dipanggil oleh JavaScript di frontend secara berkala.
@app.route('/get_live_data', methods=['GET'])
def get_live_data():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    global last_esp32_data
    try:
        esp32_response = requests.get(f"http://{ESP32_IP}/data", timeout=2)
        if esp32_response.status_code == 200:
            esp32_current_data = esp32_response.json()
            last_esp32_data.update(esp32_current_data)
            
            # Opsional: Simpan data sensor ke sensordata.json
            sensor_log = {
                "timestamp": datetime.datetime.now().isoformat(),
                "data": esp32_current_data
            }
            save_data_to_json('sensordata.json', sensor_log)

            return jsonify(last_esp32_data), 200
        else:
            return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
    except (requests.exceptions.ConnectionError, json.JSONDecodeError, requests.exceptions.Timeout) as e:
        print(f"Error fetching live data: {e}. Using last known data.")
        # Tetap kirim data terakhir yang diketahui jika ESP32 tidak merespons
        return jsonify(last_esp32_data), 200
    except Exception as e:
        print(f"An unexpected error occurred in /get_live_data: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# ==============================================================================
#                  API ROUTES: INTERAKSI DENGAN ESP32 (SENSOR MENGIRIM/MENERIMA)
# ==============================================================================

# Fungsi: Sensor Mengirim Data (ESP32 POST data monitoring ke Flask) - ALTERNATIF
# Jika Anda ingin ESP32 yang secara aktif mengirim data ke Flask (push method)
# Daripada Flask yang menarik data dari ESP32 (pull method)
# Ini bisa jadi alternatif dari /get_live_data jika beban ESP32 tinggi.
@app.route('/sensor_data_post', methods=['POST'])
def sensor_data_post():
    if not session.get('logged_in'): # Anda bisa memutuskan apakah ini butuh login atau tidak
        pass # Atau return jsonify({"error": "Unauthorized"}), 401

    if request.is_json:
        sensor_data = request.get_json()
        print(f"Received sensor data from ESP32: {sensor_data}")
        
        global last_esp32_data
        last_esp32_data.update(sensor_data) # Update data global dengan yang diterima
        
        # Opsional: Simpan ke sensordata.json
        sensor_log = {
            "timestamp": datetime.datetime.now().isoformat(),
            "data": sensor_data
        }
        save_data_to_json('sensordata.json', sensor_log)

        return jsonify({"status": "success", "message": "Data received"}), 200
    return jsonify({"status": "error", "message": "Invalid JSON"}), 400

# Fungsi: Sensor Menerima Data (ESP32 GET konfigurasi dari Flask) - ALTERNATIF
# Jika Anda ingin ESP32 mendapatkan setting target dari Flask, bukan hanya Flask yang push ke ESP32
# Ini bisa berguna jika ESP32 perlu mengambil setting saat booting atau reset.
@app.route('/get_esp32_config', methods=['GET'])
def get_esp32_config():
    # Ini tidak memerlukan login di sisi web karena ESP32 yang akan memanggil
    # Anda bisa menambahkan API Key untuk otentikasi ESP32 jika perlu
    
    config = {
        "target_voltage": last_esp32_data['target_voltage'],
        "target_current": last_esp32_data['target_current'],
        "relay_status_default": last_esp32_data['relay_status'] # Jika ingin ESP32 sync status relay
    }
    return jsonify(config), 200


# --- JALANKAN APLIKASI FLASK ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)