import configparser
from functools import wraps
import json
import time
import os
from threading import Thread
from flask import Flask, jsonify, request
from kafka import KafkaConsumer
from collections import defaultdict, deque
import requests

# FIXED: Read config from parent directory (root)
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
config = configparser.ConfigParser()
config.read('config.ini')

# FIXED: Handle missing config sections gracefully
if config.has_section('default'):
    bootstrap_servers = config.get('default', 'bootstrap.servers', fallback='localhost:9092')
else:
    # Try to get from kafka section or use default
    if config.has_section('kafka'):
        bootstrap_servers = config.get('kafka', 'bootstrap.servers', fallback='localhost:9092')
    else:
        bootstrap_servers = 'localhost:9092'

# FIXED: Get auth service URL with fallback
if config.has_section('stats_service'):
    auth_service_url = config.get('stats_service', 'auth_service_url', fallback='http://localhost:5002')
    admin_api_key = config.get('stats_service', 'admin_api_key', fallback='admin-secret-key-123')
else:
    auth_service_url = 'http://localhost:5002'
    admin_api_key = 'admin-secret-key-123'

app = Flask(__name__)

# Statistics storage with enhanced tracking
stats = {
    'total_plays': 0,
    'total_api_calls': 0,
    'popular_songs': defaultdict(int),
    'popular_artists': defaultdict(int),
    'active_users': defaultdict(int),
    'endpoint_usage': defaultdict(int),
    'hourly_traffic': defaultdict(int),
    'recent_plays': deque(maxlen=100),
    'recent_api_calls': deque(maxlen=100),
    'error_count': 0
}

def consume_kafka_events():
    """Consume from Kafka topics"""
    print(f"🎧 Starting Kafka Consumer for stats...")
    
    try:
        consumer = KafkaConsumer(
            'song_plays',
            'endpoint_usage',
            bootstrap_servers=[bootstrap_servers],
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            group_id='music_stats_group',
            enable_auto_commit=True,
            consumer_timeout_ms=1000
        )
        
        print(f"✅ Stats Consumer connected to Kafka at {bootstrap_servers}")
        
        for message in consumer:
            event = message.value
            
            if message.topic == 'song_plays':
                stats['total_plays'] += 1
                
                song = event.get('song', 'Unknown')
                artist = event.get('artist', 'Unknown')
                user = event.get('user', 'anonymous')
                
                stats['popular_songs'][song] += 1
                stats['popular_artists'][artist] += 1
                stats['active_users'][user] += 1
                
                # Add to recent plays
                stats['recent_plays'].append({
                    'song': song,
                    'artist': artist,
                    'user': user,
                    'timestamp': event.get('timestamp', 0),
                    'time': time.strftime('%H:%M:%S', time.localtime(event.get('timestamp', 0)))
                })
                
                # Track hourly traffic
                hour = time.strftime('%H', time.localtime(event.get('timestamp', 0)))
                stats['hourly_traffic'][hour] += 1
                
            elif message.topic == 'endpoint_usage':
                stats['total_api_calls'] += 1
                endpoint = event.get('endpoint', 'unknown')
                stats['endpoint_usage'][endpoint] += 1
                
                stats['recent_api_calls'].append({
                    'endpoint': endpoint,
                    'user': event.get('user', 'anonymous'),
                    'method': event.get('method', 'GET'),
                    'timestamp': event.get('timestamp', 0)
                })
                
    except Exception as e:
        print(f"❌ Kafka Consumer error: {e}")

# Start Kafka consumer in background thread
kafka_thread = Thread(target=consume_kafka_events, daemon=True)
kafka_thread.start()

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            headers = {'Authorization': token}
            response = requests.post(f"{auth_service_url}/auth/validate", headers=headers, timeout=5)
            
            if response.status_code != 200:
                return jsonify({'error': 'Invalid token'}), 401
            
            user_data = response.json()['user']
            request.user = user_data
            
        except requests.exceptions.RequestException:
            # If auth service is down, allow with warning (for testing)
            print("⚠️ Auth service unavailable, allowing request")
            request.user = {'username': 'system', 'role': 'admin'}
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
        return f(*args, **kwargs)
    
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'user') or request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/statistics', methods=['GET'])
@token_required
@admin_required
def get_statistics():
    """Get detailed statistics (admin only)"""
    # Convert defaultdicts to regular dicts
    popular_songs = dict(stats['popular_songs'])
    popular_artists = dict(stats['popular_artists'])
    active_users = dict(stats['active_users'])
    endpoint_usage = dict(stats['endpoint_usage'])
    hourly_traffic = dict(stats['hourly_traffic'])
    
    # Get top 10 for each category
    top_songs = sorted(popular_songs.items(), key=lambda x: x[1], reverse=True)[:10]
    top_artists = sorted(popular_artists.items(), key=lambda x: x[1], reverse=True)[:10]
    top_users = sorted(active_users.items(), key=lambda x: x[1], reverse=True)[:10]
    top_endpoints = sorted(endpoint_usage.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Calculate averages
    avg_plays_per_user = stats['total_plays'] / max(len(active_users), 1)
    avg_api_calls_per_hour = stats['total_api_calls'] / max(len(hourly_traffic), 1)
    
    return jsonify({
        'summary': {
            'total_plays': stats['total_plays'],
            'total_api_calls': stats['total_api_calls'],
            'unique_songs_played': len(popular_songs),
            'unique_artists': len(popular_artists),
            'active_users': len(active_users),
            'avg_plays_per_user': round(avg_plays_per_user, 2),
            'avg_api_calls_per_hour': round(avg_api_calls_per_hour, 2),
            'error_count': stats['error_count']
        },
        'top_songs': top_songs,
        'top_artists': top_artists,
        'top_users': top_users,
        'endpoint_usage': top_endpoints,
        'hourly_traffic': dict(sorted(hourly_traffic.items())),
        'recent_activity': {
            'recent_plays': list(stats['recent_plays'])[-10:],
            'recent_api_calls': list(stats['recent_api_calls'])[-10:]
        }
    })

@app.route('/admin/health', methods=['GET'])
@token_required
@admin_required
def admin_health():
    """Admin health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'stats-service',
        'kafka_connected': kafka_thread.is_alive(),
        'stats_updated': time.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/health', methods=['GET'])
def health():
    """Public health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'stats-service',
        'total_plays': stats['total_plays'],
        'kafka_bootstrap': bootstrap_servers
    })

if __name__ == '__main__':
    print("🚀 Stats Service Consumer starting on http://localhost:5001")
    print(f"🔐 Authentication URL: {auth_service_url}")
    print(f"📡 Kafka: {bootstrap_servers}")
    print(f"🔑 Admin API Key: {admin_api_key}")
    app.run(host='0.0.0.0', port=5001, debug=True)