from flask import Flask, render_template, url_for, jsonify, redirect
import json
import os

app = Flask(__name__, template_folder='html', static_folder='style')
COMMS_FILE = 'command.json'
STATS_FILE = 'sensordata.json'

@app.route('/')
def login():
  return render_template('login.html')

if __name__ == "__main__":
  app.run(debug=True, port=4545)