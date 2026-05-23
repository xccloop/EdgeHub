"""HTTP REST + WebSocket API server for external tool access (Claude Code, etc.)"""

import json
import threading
import logging

logging.getLogger('werkzeug').setLevel(logging.WARNING)

from flask import Flask, request, jsonify

from app.backend.parser import AppState
from app.backend.tcp_client import TcpWorker

flask_app = Flask("EpollAPI")
flask_app.config['SECRET_KEY'] = 'epoll-tuning'

_WS_AVAILABLE = False
_socketio = None
try:
    from flask_socketio import SocketIO, emit
    _socketio = SocketIO(cors_allowed_origins="*")
    _socketio.init_app(flask_app)
    _WS_AVAILABLE = True
except (ValueError, ImportError, Exception):
    _socketio = None

_app_state: AppState = None
_tcp_worker: TcpWorker = None


def init_api(state: AppState, worker: TcpWorker):
    global _app_state, _tcp_worker
    _app_state = state
    _tcp_worker = worker

    worker.param_updated.connect(_on_param_updated)
    worker.log_received.connect(_on_log_received)
    worker.connection_changed.connect(_on_connection_changed)

    if _WS_AVAILABLE and _socketio:
        t = threading.Thread(target=lambda: _socketio.run(
            flask_app, host='0.0.0.0', port=9527,
            allow_unsafe_werkzeug=True, debug=False,
            use_reloader=False, log_output=False), daemon=True)
    else:
        t = threading.Thread(target=lambda: flask_app.run(
            host='0.0.0.0', port=9527, debug=False,
            use_reloader=False), daemon=True)
    t.start()


def _on_param_updated(name, param):
    if _WS_AVAILABLE and _socketio:
        _socketio.emit('param_update', {
            'name': name, 'value': param.value,
            'min': param.min_val, 'max': param.max_val,
            'description': param.description
        })


def _on_log_received(ts, text):
    if _WS_AVAILABLE and _socketio:
        _socketio.emit('log', {'ts': ts, 'text': text})


def _on_connection_changed(connected, addr):
    if _WS_AVAILABLE and _socketio:
        _socketio.emit('connection', {'connected': connected, 'address': addr})


# ── REST Endpoints ──

@flask_app.route('/api/status')
def api_status():
    return jsonify({
        'connected': _app_state.connected if _app_state else False,
        'address': _app_state.conn_addr if _app_state else '',
        'status': _app_state.status if _app_state else 'Not initialized',
        'websocket': _WS_AVAILABLE,
    })


@flask_app.route('/api/params')
def api_params():
    if not _app_state:
        return jsonify({})
    return jsonify({
        name: {'value': p.value, 'min': p.min_val, 'max': p.max_val, 'description': p.description}
        for name, p in _app_state.parameters.items()
    })


@flask_app.route('/api/params/<name>')
def api_param(name):
    if not _app_state or name not in _app_state.parameters:
        return jsonify({'error': 'not found'}), 404
    p = _app_state.parameters[name]
    return jsonify({'name': name, 'value': p.value, 'min': p.min_val, 'max': p.max_val, 'description': p.description})


@flask_app.route('/api/connect', methods=['POST'])
def api_connect():
    data = request.get_json(silent=True) or {}
    host = data.get('host', '')
    port = data.get('port', 9000)
    if not host:
        return jsonify({'error': 'host required'}), 400
    if _tcp_worker:
        _tcp_worker.connect_to(host, int(port))
    return jsonify({'status': 'connecting', 'host': host, 'port': port})


@flask_app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    if _tcp_worker:
        _tcp_worker.disconnect()
    return jsonify({'status': 'disconnected'})


@flask_app.route('/api/command', methods=['POST'])
def api_command():
    data = request.get_json(silent=True) or {}
    cmd = data.get('command', '')
    if not cmd:
        return jsonify({'error': 'command required'}), 400
    if _tcp_worker:
        _tcp_worker.send(cmd)
    return jsonify({'status': 'sent', 'command': cmd})


# ── WebSocket (if available) ──

if _WS_AVAILABLE:

    @_socketio.on('connect')
    def ws_connect():
        emit('welcome', {'message': 'Connected to Epoll tuning API'})

    @_socketio.on('command')
    def ws_command(data):
        cmd = data.get('command', '')
        if cmd and _tcp_worker:
            _tcp_worker.send(cmd)

    @_socketio.on('disconnect')
    def ws_disconnect():
        pass
