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
  static_url_path='/css')

app.secret_key = os.urandom(24).hex()

ESP32_IP = 'IP ADDRESS'

last_esp32_data = {
  'voltage': 0.0,
  'current': 0.0,
  'power': 0.0,
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
      last_esp32_data.update(response.json())
    else:
      print(f'Error fetching initial data from ESP32: HTTP {response.status_code}')
  except (requests.exceptions.ConnectionError, json.JSONDecodeError, requests.exceptions.Timeout) as e:
    print(f'Error connecting to ESP32 for initial data: {e}. Using defaults data.')

  return render_template('dashboard.html', data=last_esp32_data, esp32_ip=ESP32_IP)

@app.route('/logout')
def logout():
  session.pop('logged_in', None)
  return redirect(url_for('login'))
  

if __name__ == "__main__":
  app.run(debug=True, port=4545)