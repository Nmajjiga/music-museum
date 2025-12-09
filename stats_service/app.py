import json
import os
from collections import defaultdict
from threading import Thread
from flask import Flask, jsonify, request
from kafka import KafkaConsumer
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092').split(',')
ADMIN_API_KEY = os.getenv('ADMIN_API_KEY')

# Statistics storage
stats = {
    'api_requests': defaultdict(int),
    'song_plays': defaultdict(int),
    'endpoint_usage': defaultdict(lambda: defaultdict(int)),
    'service_usage': defaultdict(int)
}

def consume_kafka_events():
    """Consume events from Kafka topics"""
    consumer = KafkaConsumer(
        'api_requests',
        'song_plays',
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True
    )
    
    for message in consumer:
        topic = message.topic
        event = message.value
        
        if topic == 'api_requests':
            stats['api_requests']['total'] += 1
            endpoint = event.get('endpoint', 'unknown')
            stats['endpoint_usage'][endpoint]['total'] += 1
            stats['service_usage'][event.get('service', 'unknown')] += 1
            
        elif topic == 'song_plays':
            stats['song_plays']['total'] += 1
            song_id = event.get('song_id', 'unknown')
            stats['song_plays'][song_id] += 1

# Start Kafka consumer in background thread
kafka_thread = Thread(target=consume_kafka_events, daemon=True)
kafka_thread.start()

# Admin endpoints
@app.route('/admin/statistics', methods=['GET'])
def get_statistics():
    """Get usage statistics (protected by admin API key)"""
    api_key = request.headers.get('X-Admin-API-Key')
    if api_key != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    return jsonify({
        'api_requests': dict(stats['api_requests']),
        'song_plays': dict(stats['song_plays']),
        'endpoint_usage': {
            k: dict(v) for k, v in stats['endpoint_usage'].items()
        },
        'service_usage': dict(stats['service_usage'])
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'stats-service'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)