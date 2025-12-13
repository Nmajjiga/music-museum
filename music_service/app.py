from flask import Flask, request, jsonify
import requests
import time
import os
from functools import wraps
from datetime import datetime
import hashlib
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
STATS_SERVICE_URL = os.getenv('STATS_SERVICE_URL', 'http://localhost:5001')
AUTH_SERVICE_URL = os.getenv('AUTH_SERVICE_URL', 'http://localhost:5002')
DATA_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json"

# Pre-loaded century data
songs_1900s = []  # Top 100 songs from late 1900s
songs_2000s = []  # Top 100 songs from 2000s
all_songs = []
data_loaded_time = None

def load_all_songs():
    """Load and process all songs from Billboard data"""
    global songs_1900s, songs_2000s, all_songs, data_loaded_time
    
    try:
        print("Loading Billboard data from GitHub...")
        response = requests.get(DATA_URL, timeout=30)
        data = response.json()
        
        # Process all songs
        all_songs_dict = {}
        century_1999_dict = {}
        century_2000s_dict = {}
        
        for chart in data:
            date = chart.get('date', '')
            if not date:
                continue
                
            year = int(date.split('-')[0]) if '-' in date else 0
            
            for song_entry in chart.get('data', []):
                title = song_entry.get('song', 'Unknown')
                artist = song_entry.get('artist', 'Unknown')
                key = f"{title}|{artist}"
                
                song_obj = {
                    'id': hashlib.md5(key.encode()).hexdigest()[:8],
                    'title': title,
                    'artist': artist,
                    'peak_position': song_entry.get('peak_position', 100),
                    'weeks_on_chart': song_entry.get('weeks_on_chart', 1),
                    'this_week': song_entry.get('this_week', 100),
                    'last_week': song_entry.get('last_week'),
                    'first_seen': date,
                    'year': year
                }
                
                # Add to master dictionary
                if key not in all_songs_dict:
                    all_songs_dict[key] = song_obj
                
                # Add to century dictionaries
                if 1958 <= year <= 1999 and key not in century_1999_dict:
                    century_1999_dict[key] = song_obj
                elif year >= 2000 and key not in century_2000s_dict:
                    century_2000s_dict[key] = song_obj
        
        # Convert to lists
        all_songs = list(all_songs_dict.values())
        
        # Process 1900s songs
        songs_1900s = list(century_1999_dict.values())
        songs_1900s.sort(key=lambda x: x.get('peak_position', 100))
        songs_1900s = songs_1900s[:100]
        
        # Process 2000s songs
        songs_2000s = list(century_2000s_dict.values())
        songs_2000s.sort(key=lambda x: x.get('peak_position', 100))
        songs_2000s = songs_2000s[:100]
        
        # Sort main list
        all_songs.sort(key=lambda x: x.get('this_week', 100))
        data_loaded_time = datetime.now()
        
        print(f"Loaded {len(all_songs)} total songs")
        print(f"1900s songs: {len(songs_1900s)}")
        print(f"2000s songs: {len(songs_2000s)}")
        return True
        
    except Exception as e:
        print(f"Error loading songs: {e}")
        # Sample data
        all_songs = [
            {'id': '1', 'title': 'Smooth', 'artist': 'Santana', 'peak_position': 1, 'year': 1999},
            {'id': '2', 'title': 'Believe', 'artist': 'Cher', 'peak_position': 1, 'year': 1999}
        ]
        songs_1900s = all_songs[:]
        songs_2000s = [
            {'id': '3', 'title': 'Flowers', 'artist': 'Miley Cyrus', 'peak_position': 1, 'year': 2023},
            {'id': '4', 'title': 'Anti-Hero', 'artist': 'Taylor Swift', 'peak_position': 1, 'year': 2022}
        ]
        data_loaded_time = datetime.now()
        return False

def track_usage(endpoint, user='anonymous'):
    """Track usage via stats service"""
    try:
        event = {
            'endpoint': endpoint,
            'user': user,
            'service': 'music-service',
            'method': request.method,
            'timestamp': datetime.now().isoformat()
        }
        requests.post(f"{STATS_SERVICE_URL}/record", json=event, timeout=1)
    except:
        pass

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        
        # Validate with auth service
        try:
            headers = {'Authorization': token}
            response = requests.post(
                f"{AUTH_SERVICE_URL}/auth/validate",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                request.current_user = response.json()['user']
                return f(*args, **kwargs)
        except Exception as e:
            print(f"Auth service error: {e}")
        
        return jsonify({'error': 'Invalid token'}), 401
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'current_user') or request.current_user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# ============ ENDPOINTS ============

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'music-service',
        'total_songs': len(all_songs),
        '1900s_songs': len(songs_1900s),
        '2000s_songs': len(songs_2000s)
    })

@app.route('/songs/top100', methods=['GET'])
@token_required
def get_top100():
    user = request.current_user.get('username', 'anonymous')
    track_usage('/songs/top100', user)
    return jsonify({
        'songs': all_songs[:100],
        'count': min(100, len(all_songs))
    })

@app.route('/songs/century/<int:century>', methods=['GET'])
@token_required
def get_century_songs(century):
    """Get top 100 songs for a specific century"""
    user = request.current_user.get('username', 'anonymous')
    track_usage(f'/songs/century/{century}', user)
    
    if century == 1900:
        target_songs = songs_1900s
        era = '1900s (1958-1999)'
    elif century == 2000:
        target_songs = songs_2000s
        era = '2000s (2000-present)'
    else:
        return jsonify({'error': 'Invalid century'}), 400
    
    return jsonify({
        'songs': target_songs,
        'count': len(target_songs),
        'century': century,
        'era': era,
        'message': f'Top {len(target_songs)} songs from {era}'
    })

@app.route('/songs/search', methods=['GET'])
@token_required
def search_songs():
    user = request.current_user.get('username', 'anonymous')
    track_usage('/songs/search', user)
    
    query = request.args.get('q', '').lower()
    if len(query) < 2:
        return jsonify({'error': 'Query too short'}), 400
    
    results = [
        song for song in all_songs
        if query in song['title'].lower() or query in song['artist'].lower()
    ][:20]
    
    return jsonify({'results': results, 'count': len(results)})

@app.route('/admin/reload', methods=['POST'])
@token_required
@admin_required
def reload_songs():
    user = request.current_user.get('username', 'anonymous')
    track_usage('/admin/reload', user)
    
    success = load_all_songs()
    return jsonify({
        'message': 'Songs reloaded successfully' if success else 'Reload failed',
        'total_songs': len(all_songs),
        '1900s_songs': len(songs_1900s),
        '2000s_songs': len(songs_2000s)
    })

@app.route('/admin/status', methods=['GET'])
@token_required
@admin_required
def get_status():
    track_usage('/admin/status', request.current_user.get('username', 'anonymous'))
    return jsonify({
        'total_songs': len(all_songs),
        '1900s_songs': len(songs_1900s),
        '2000s_songs': len(songs_2000s),
        'features': ['century_filtering', 'search']
    })

@app.route('/test/token', methods=['GET'])
def get_test_token():
    """For testing only - use auth service for real tokens"""
    return jsonify({
        'note': 'Use /auth/login endpoint for real tokens'
    })

# ============ STARTUP ============
load_all_songs()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"Music Service on port {port}")
    print(f"Health: http://localhost:{port}/health")
    print(f"1900s: http://localhost:{port}/songs/century/1900")
    print(f"2000s: http://localhost:{port}/songs/century/2000")
    app.run(host='0.0.0.0', port=port, debug=False)