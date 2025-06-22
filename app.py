from flask import Flask, render_template, url_for, jsonify, redirect, request, session
import requests
import json
import os
import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
  __name__, 
  template_folder=os.path.join(BASE_DIR, 'html'), 
  static_folder=os.path.join(BASE_DIR, 'style'),
  static_url_path='/style')

app.secret_key = os.urandom(24).hex() 

ESP32_IP = 'IP_ADDRESS_ANDA' # Ganti dengan IP Address ESP32 yang sebenarnya!

# PERBAIKAN: last_esp32_data, hapus 'target_current'
last_esp32_data = {
  'bus_voltage': 0.0,       
  'shunt_voltage': 0.0,     
  'load_voltage': 0.0,      
  'current_mA': 0.0,        
  'power_W': 0.0,           
  'target_voltage': 3.0,    # Default untuk slider voltage
  'relay_status': 'OFF'     
}

VALID_USERNAME = 'sosokAdmin'
VALID_PASSWORD = 'admin1234'

def saveToJson(filename, data_to_save):
  filepath = os.path.join(BASE_DIR, filename)
  try:
    with open(filepath, 'a') as f:
      json.dump(data_to_save, f)
      f.write('\n')
    print(f'Data saved to {filename}')
  except Exception as e:
    print(f'Error saving data to {filename}: {e}')

@app.route('/login', methods=['GET', 'POST'])
def login():
  error = None
  if request.method == 'POST':
    username = request.form.get('username')
    password = request.form.get('password')

    if username == VALID_USERNAME and password == VALID_PASSWORD:
      session['logged_in'] = True
      return redirect(url_for('dashboard'))
    else:
      return render_template('login.html', error='Invalid Credentials, please try again.'), 401
  return render_template('login.html', error=error)

@app.route('/')
def dashboard():
  if not session.get('logged_in'):
    return redirect(url_for('login'))
  
  global last_esp32_data
  try:
    response = requests.get(f'http://{ESP32_IP}/data', timeout=2)
    if response.status_code == 200:
      esp32_data_from_json = response.json()
      last_esp32_data.update(esp32_data_from_json)
      print(f'Initial data fetched: {last_esp32_data}')
    else:
      print(f'Error fetching initial data from ESP32: HTTP {response.status_code}')
  except (requests.exceptions.ConnectionError, json.JSONDecodeError, requests.exceptions.Timeout) as e:
    print(f'Error connecting to ESP32 for initial data: {e}. Using defaults data.')
    
  return render_template('dashboard.html', data=last_esp32_data, esp32_ip=ESP32_IP)

@app.route('/logout')
def logout():
  session.pop('logged_in', None)
  return redirect(url_for('login'))
  
# --- ROUTE API: MENGAMBIL DATA LIVE DARI ESP32 ---
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
            
            sensor_log = {
                "timestamp": datetime.datetime.now().isoformat(),
                "data": esp32_current_data
            }
            # saveToJson('sensordata.json', sensor_log) 

            return jsonify(last_esp32_data), 200
        else:
            return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
    except (requests.exceptions.ConnectionError, json.JSONDecodeError, requests.exceptions.Timeout) as e:
        print(f"Error fetching live data: {e}. Using last known data.")
        return jsonify(last_esp32_data), 200 
    except Exception as e:
        print(f"An unexpected error occurred in /get_live_data: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

# --- ROUTE API: MENGATUR OUTPUT BUCK-BOOST (Hanya Voltage) ---
@app.route('/update_output_params', methods=['POST'])
def update_output_params():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    if request.is_json:
        data = request.get_json()
        target_voltage = data.get('voltage')
        # Hapus target_current dari sini

        if target_voltage is None: 
            return jsonify({"error": "Missing voltage parameter"}), 400
        
        try:
            target_voltage = float(target_voltage)
            # Hapus konversi float untuk target_current
        except (ValueError, TypeError):
             return jsonify({"error": "Invalid voltage format"}), 400 # Ubah pesan error

        try:
            # Kirim hanya target_voltage ke ESP32
            esp32_response = requests.post(
                f"http://{ESP32_IP}/set_output_params",
                data={'voltage': target_voltage}, # Hanya kirim voltage
                timeout=2
            )
            if esp32_response.status_code == 200:
                last_esp32_data['target_voltage'] = target_voltage
                # Hapus last_esp32_data['target_current']
                command_log = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": "set_output",
                    "voltage": target_voltage,
                    "status": "success"
                }
                # saveToJson('command.json', command_log)
                return jsonify({"message": "Target voltage updated successfully!"}), 200
            else:
                return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "Could not connect to ESP32. Check IP address and network."}), 500
        except requests.exceptions.Timeout:
            return jsonify({"error": "Timeout connecting to ESP32."}), 500
    return jsonify({"error": "Request must be JSON"}), 400

# --- ROUTE API: KONTROL RELAY --- (Tidak berubah)
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
                command_log = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "type": "control_relay",
                    "status": status.upper(),
                    "result": "success"
                }
                # saveToJson('command.json', command_log)
                return jsonify({"message": f"Relay set to {status.upper()}"}), 200
            else:
                return jsonify({"error": f"ESP32 returned status: {esp32_response.status_code}"}), 500
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "Could not connect to ESP32. Check IP address and network."}), 500
        except requests.exceptions.Timeout:
            return jsonify({"error": "Timeout connecting to ESP32."}), 500
    return jsonify({"error": "Request must be JSON"}), 400

if __name__ == "__main__":
  app.run(debug=True, port=4545)