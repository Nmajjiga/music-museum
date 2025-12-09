import json
import os
import time
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092').split(',')
API_KEYS = set(os.getenv('API_KEYS', '').split(','))
DATA_PATH = os.getenv('DATA_PATH', 'data/all.json')

# Kafka Producer
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Load song data
with open(DATA_PATH, 'r') as f:
    songs_data = json.load(f)
    songs = {song['id']: song for song in songs_data}

# Helper functions
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key not in API_KEYS:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated

def send_kafka_event(topic, event_data):
    """Send event to Kafka topic"""
    try:
        producer.send(topic, event_data)
        producer.flush()
    except Exception as e:
        app.logger.error(f"Failed to send Kafka event: {e}")

# Middleware for tracking requests
@app.before_request
def track_request():
    if request.endpoint and request.endpoint != 'static':
        event = {
            'service': 'music-service',
            'endpoint': request.endpoint,
            'method': request.method,
            'path': request.path,
            'timestamp': time.time(),
            'ip': request.remote_addr,
            'user_agent': request.user_agent.string
        }
        send_kafka_event('api_requests', event)

# API Endpoints
@app.route('/songs', methods=['GET'])
@require_api_key
def get_songs():
    """Get paginated list of songs"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    start = (page - 1) * per_page
    end = start + per_page
    
    songs_list = list(songs.values())[start:end]
    return jsonify({
        'page': page,
        'per_page': per_page,
        'total': len(songs),
        'songs': songs_list
    })

@app.route('/songs/top100', methods=['GET'])
@require_api_key
def get_top100():
    """Get top 100 most popular songs"""
    # Sort by popularity (assuming 'popularity' field exists)
    sorted_songs = sorted(
        songs.values(), 
        key=lambda x: x.get('popularity', 0), 
        reverse=True
    )[:100]
    return jsonify({'songs': sorted_songs})

@app.route('/songs/<song_id>', methods=['GET'])
@require_api_key
def get_song(song_id):
    """Get specific song by ID"""
    song = songs.get(song_id)
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    return jsonify(song)

@app.route('/play', methods=['POST'])
@require_api_key
def record_play():
    """Record a song play event"""
    data = request.get_json()
    song_id = data.get('song_id')
    
    if not song_id or song_id not in songs:
        return jsonify({'error': 'Invalid song ID'}), 400
    
    # Send play event to Kafka
    play_event = {
        'song_id': song_id,
        'timestamp': time.time(),
        'user_id': request.headers.get('X-User-ID', 'anonymous'),
        'service': 'music-service'
    }
    send_kafka_event('song_plays', play_event)
    
    return jsonify({'message': 'Play recorded', 'song_id': song_id})

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'music-service'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)