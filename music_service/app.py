import configparser
import json
import time
import hashlib
import requests
import os
from flask import Flask, jsonify, request
from kafka import KafkaProducer
from functools import wraps
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from collections import defaultdict, Counter
from datetime import datetime

# FIXED: Read config from parent directory (root)
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
config = configparser.ConfigParser()
config.read(config_path)

# MongoDB Configuration
MONGODB_URI = "mongodb+srv://videoAppUser:uNnlvDPlnz2MbrmU@cluster0.ol102vh.mongodb.net/?appName=Cluster0"
MONGODB_DB = "BillboardSongs"
MONGODB_COLLECTION = "Songs"

# FIXED: Use the correct section names
if config.has_section('default'):
    bootstrap_servers = config.get('default', 'bootstrap.servers', fallback='localhost:9092')
else:
    if config.has_section('kafka'):
        bootstrap_servers = config.get('kafka', 'bootstrap.servers', fallback='localhost:9092')
    else:
        bootstrap_servers = 'localhost:9092'

# Get auth service URL with fallback
if config.has_section('music_service'):
    auth_service_url = config.get('music_service', 'auth_service_url', fallback='http://localhost:5002')
    api_keys_str = config.get('music_service', 'api_keys', fallback='music-api-key-1')
    admin_api_key = config.get('music_service', 'admin_api_key', fallback='admin-secret-key-123')
else:
    auth_service_url = 'http://localhost:5002'
    api_keys_str = 'music-api-key-1'
    admin_api_key = 'admin-secret-key-123'

app = Flask(__name__)

# Global variables for MongoDB connection
mongodb_client = None
songs_collection = None
producer = None
all_songs = []
top_100_songs = []

def init_mongodb():
    """Initialize MongoDB connection"""
    global mongodb_client, songs_collection
    
    try:
        mongodb_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
        # Send a ping to confirm successful connection
        mongodb_client.admin.command('ping')
        print("✅ Successfully connected to MongoDB!")
        
        # Get database and collection
        db = mongodb_client[MONGODB_DB]
        songs_collection = db[MONGODB_COLLECTION]
        
        # Test connection by counting documents
        week_count = songs_collection.estimated_document_count()
        print(f"📊 Found approximately {week_count} weekly charts in MongoDB")
        return True
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        mongodb_client = None
        songs_collection = None
        return False

def init_kafka():
    """Initialize Kafka producer"""
    global producer
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=[bootstrap_servers],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            api_version=(2, 0, 2)
        )
        print(f"✅ Music Producer connected to Kafka at {bootstrap_servers}")
        return True
    except Exception as e:
        print(f"⚠️ Kafka connection failed: {e}")
        producer = None
        return False

# Initialize connections
mongodb_initialized = init_mongodb()
kafka_initialized = init_kafka()

# Parse API keys
api_keys = set([key.strip() for key in api_keys_str.split(',')])

# Authentication decorators
def token_or_admin_required(f):
    """Decorator that accepts either JWT token or admin API key"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        api_key = request.headers.get('X-API-Key')
        admin_key = request.headers.get('X-Admin-Key')
        
        # Check if admin key is provided and valid
        if admin_key and admin_key == admin_api_key:
            request.user = {'username': 'admin', 'role': 'admin'}
            return f(*args, **kwargs)
        
        # Check for regular API key
        if api_key and api_key in api_keys:
            request.user = {'username': 'api_user', 'role': 'user'}
            return f(*args, **kwargs)
        
        # Check for JWT token
        if not token:
            return jsonify({'error': 'Authentication required. Provide Authorization token, X-API-Key, or X-Admin-Key'}), 401
        
        try:
            # Validate token with auth service
            headers = {'Authorization': token}
            response = requests.post(f"{auth_service_url}/auth/validate", headers=headers, timeout=5)
            
            if response.status_code != 200:
                return jsonify({'error': 'Invalid token'}), 401
            
            user_data = response.json()['user']
            request.user = user_data
            
        except requests.exceptions.RequestException:
            return jsonify({'error': 'Authentication service unavailable'}), 503
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
        return f(*args, **kwargs)
    
    return decorated

def admin_required(f):
    """Decorator that requires admin privileges (either JWT admin or admin API key)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for admin API key first
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key and admin_key == admin_api_key:
            request.user = {'username': 'admin_api', 'role': 'admin'}
            return f(*args, **kwargs)
        
        # Check if user attribute exists and is admin
        if not hasattr(request, 'user') or request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required. Provide X-Admin-Key header with admin API key'}), 403
        return f(*args, **kwargs)
    return decorated

def admin_or_token_required(f):
    """Decorator that accepts either admin API key or regular JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_key = request.headers.get('X-Admin-Key')
        token = request.headers.get('Authorization')
        
        # Check admin key first
        if admin_key and admin_key == admin_api_key:
            request.user = {'username': 'admin_api', 'role': 'admin'}
            return f(*args, **kwargs)
        
        # Check for JWT token
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        
        try:
            headers = {'Authorization': token}
            response = requests.post(f"{auth_service_url}/auth/validate", headers=headers, timeout=5)
            
            if response.status_code != 200:
                return jsonify({'error': 'Invalid token'}), 401
            
            user_data = response.json()['user']
            request.user = user_data
            
        except requests.exceptions.RequestException:
            return jsonify({'error': 'Authentication service unavailable'}), 503
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        
        return f(*args, **kwargs)
    
    return decorated

# Track endpoint usage
def track_endpoint_usage(endpoint_name):
    if producer is not None:
        usage_event = {
            'endpoint': endpoint_name,
            'timestamp': time.time(),
            'user': getattr(request, 'user', {}).get('username', 'anonymous'),
            'method': request.method,
            'path': request.path
        }
        producer.send('endpoint_usage', value=usage_event)

# Helper functions (keep the same as before)
def process_weekly_charts(weekly_charts, limit_weeks=100):
    """Process weekly charts to extract unique songs with their stats"""
    song_dict = {}
    
    for week in weekly_charts[:limit_weeks]:
        week_date = week.get('date', '1958-01-01')
        year = int(week_date.split('-')[0]) if '-' in week_date else 1958
        
        for song_entry in week.get('data', []):
            key = f"{song_entry.get('song', 'Unknown')}_{song_entry.get('artist', 'Unknown')}"
            
            if key not in song_dict:
                song_dict[key] = {
                    'id': hashlib.md5(key.encode()).hexdigest()[:10],
                    'title': song_entry.get('song', 'Unknown'),
                    'artist': song_entry.get('artist', 'Unknown'),
                    'year': year,
                    'best_position': song_entry.get('peak_position', 999),
                    'weeks_on_chart': song_entry.get('weeks_on_chart', 1),
                    'first_appearance': week_date,
                    'appearances': 1,
                    'year_data': {year: {
                        'appearances': 1,
                        'best_position': song_entry.get('peak_position', 999),
                        'weeks_on_chart': song_entry.get('weeks_on_chart', 1)
                    }}
                }
            else:
                if song_entry.get('peak_position', 999) < song_dict[key]['best_position']:
                    song_dict[key]['best_position'] = song_entry.get('peak_position', 999)
                
                if song_entry.get('weeks_on_chart', 1) > song_dict[key]['weeks_on_chart']:
                    song_dict[key]['weeks_on_chart'] = song_entry.get('weeks_on_chart', 1)
                
                song_dict[key]['appearances'] += 1
                
                if year in song_dict[key]['year_data']:
                    song_dict[key]['year_data'][year]['appearances'] += 1
                    if song_entry.get('peak_position', 999) < song_dict[key]['year_data'][year]['best_position']:
                        song_dict[key]['year_data'][year]['best_position'] = song_entry.get('peak_position', 999)
                else:
                    song_dict[key]['year_data'][year] = {
                        'appearances': 1,
                        'best_position': song_entry.get('peak_position', 999),
                        'weeks_on_chart': song_entry.get('weeks_on_chart', 1)
                    }
    
    return song_dict

def calculate_song_popularity(songs):
    """Calculate popularity score for a list of songs"""
    for song in songs:
        position_score = max(0, 100 - song['best_position'] + 1)
        weeks_score = min(song['weeks_on_chart'] * 2, 100)
        appearances_score = min(song['appearances'] * 5, 50)
        song['popularity'] = position_score + weeks_score + appearances_score
    
    return songs

def get_songs_by_century(century):
    """Get songs filtered by century (1900s or 2000s)"""
    global all_songs
    
    if not all_songs:
        return []
    
    if century == 1900:
        filtered_songs = [song for song in all_songs if 1958 <= song['year'] <= 1999]
    elif century == 2000:
        filtered_songs = [song for song in all_songs if 2000 <= song['year'] <= 2025]
    else:
        return []
    
    # Recalculate popularity within the century
    for song in filtered_songs:
        century_years = [year for year in song.get('year_data', {}).keys() 
                        if (century == 1900 and 1958 <= year <= 1999) or 
                           (century == 2000 and 2000 <= year <= 2025)]
        
        if century_years:
            best_position = min(song['year_data'][year]['best_position'] for year in century_years)
            total_appearances = sum(song['year_data'][year]['appearances'] for year in century_years)
            max_weeks = max(song['year_data'][year]['weeks_on_chart'] for year in century_years)
            
            position_score = max(0, 100 - best_position + 1)
            weeks_score = min(max_weeks * 2, 100)
            appearances_score = min(total_appearances * 5, 50)
            song['century_popularity'] = position_score + weeks_score + appearances_score
        else:
            song['century_popularity'] = song['popularity']
    
    filtered_songs.sort(key=lambda x: x['century_popularity'], reverse=True)
    return filtered_songs[:100]

def get_songs_by_year(year):
    """Get songs for a specific year"""
    global all_songs
    
    if not all_songs:
        return []
    
    year_songs = []
    for song in all_songs:
        if year in song.get('year_data', {}):
            year_info = song['year_data'][year]
            year_song = {
                'id': song['id'],
                'title': song['title'],
                'artist': song['artist'],
                'year': year,
                'best_position': year_info['best_position'],
                'weeks_on_chart': year_info['weeks_on_chart'],
                'appearances': year_info['appearances'],
                'overall_popularity': song['popularity']
            }
            
            position_score = max(0, 100 - year_info['best_position'] + 1)
            weeks_score = min(year_info['weeks_on_chart'] * 2, 100)
            appearances_score = min(year_info['appearances'] * 5, 50)
            year_song['year_popularity'] = position_score + weeks_score + appearances_score
            
            year_songs.append(year_song)
    
    year_songs.sort(key=lambda x: x['year_popularity'], reverse=True)
    return year_songs[:100]

def get_available_years():
    """Get list of available years in the dataset"""
    global all_songs
    
    if not all_songs:
        return []
    
    years = set()
    for song in all_songs:
        years.update(song.get('year_data', {}).keys())
    
    return sorted(list(years))

def load_and_process_music_data():
    """Load and process music data from MongoDB"""
    global mongodb_client, songs_collection
    
    try:
        if mongodb_client is None or songs_collection is None:
            print("❌ MongoDB not connected properly")
            return []
        
        # Get sample of weekly charts
        pipeline = [
            {"$match": {
                "date": {"$regex": "^(199|200|201|202)"}
            }},
            {"$sample": {"size": 100}},
            {"$project": {
                "date": 1,
                "data": 1,
                "_id": 0
            }}
        ]
        
        weekly_charts_cursor = songs_collection.aggregate(pipeline)
        weekly_charts = list(weekly_charts_cursor)
        
        print(f"✅ Retrieved {len(weekly_charts)} weekly charts from MongoDB")
        
        if not weekly_charts:
            print("❌ No weekly charts found in MongoDB")
            return []
        
        song_dict = process_weekly_charts(weekly_charts, limit_weeks=len(weekly_charts))
        songs = list(song_dict.values())
        print(f"🎵 Extracted {len(songs)} unique songs from weekly charts")
        
        if not songs:
            print("❌ No songs extracted from weekly charts")
            return []
        
        songs = calculate_song_popularity(songs)
        songs.sort(key=lambda x: x['popularity'], reverse=True)
        print(f"📊 Processed {len(songs)} songs, sorted by popularity")
        
        return songs[:500]
        
    except Exception as e:
        print(f"❌ Error loading music data from MongoDB: {e}")
        return generate_sample_songs()

def generate_sample_songs():
    """Generate sample songs for testing"""
    sample_songs = []
    
    # Add songs from different years/centuries
    for i in range(1, 101):
        if i <= 50:
            year = 1958 + (i % 42)
            century = 1900
        else:
            year = 2000 + ((i-50) % 26)
            century = 2000
        
        sample_songs.append({
            'id': f'{century}_{i}',
            'title': f'Sample Song {i} ({century}s)',
            'artist': f'Sample Artist {i}',
            'year': year,
            'best_position': i % 100 + 1,
            'weeks_on_chart': 1 + (i % 10),
            'appearances': 1 + (i % 5),
            'first_appearance': f'{year}-01-01',
            'popularity': 100 - (i % 50),
            'year_data': {
                year: {
                    'appearances': 1 + (i % 5),
                    'best_position': i % 100 + 1,
                    'weeks_on_chart': 1 + (i % 10)
                }
            }
        })
    
    return sample_songs

# Load the songs on startup
all_songs = load_and_process_music_data()
top_100_songs = all_songs[:100] if len(all_songs) > 0 else []

print(f"🎵 Loaded {len(all_songs)} songs (top 100 for users, all for admins)")

# ==================== PUBLIC ENDPOINTS (No auth required) ====================

@app.route('/health', methods=['GET'])
def health():
    """Public health check"""
    mongodb_status = mongodb_client is not None
    if mongodb_client is not None:
        try:
            mongodb_client.admin.command('ping')
            mongodb_status = True
        except:
            mongodb_status = False
    
    return jsonify({
        'status': 'healthy',
        'service': 'music-service',
        'songs_loaded': len(all_songs),
        'kafka_connected': producer is not None,
        'mongodb_connected': mongodb_status,
        'endpoints': {
            'public': ['/health', '/songs/top100', '/songs/century/<1900|2000>', '/songs/search'],
            'admin': ['/admin/* (requires X-Admin-Key)']
        }
    })

@app.route('/songs/top100', methods=['GET'])
def get_top100():
    """Get overall top 100 songs (public)"""
    return jsonify({
        'songs': top_100_songs,
        'count': len(top_100_songs),
        'message': 'Overall Top 100 songs from Billboard charts',
        'view': 'overall'
    })

@app.route('/songs/century/<int:century>', methods=['GET'])
def get_century_top100(century):
    """Get top 100 songs for a specific century (public)"""
    if century not in [1900, 2000]:
        return jsonify({'error': 'Invalid century. Use 1900 or 2000.'}), 400
    
    century_songs = get_songs_by_century(century)
    
    return jsonify({
        'songs': century_songs,
        'count': len(century_songs),
        'message': f'Top 100 songs of the {century}s',
        'view': f'{century}s',
        'year_range': '1958-1999' if century == 1900 else '2000-2025'
    })

@app.route('/songs/search', methods=['GET'])
def search_songs():
    """Search songs (public)"""
    query = request.args.get('q', '').lower()
    century = request.args.get('century', '')
    
    if not query or len(query) < 2:
        return jsonify({'error': 'Query too short'}), 400
    
    # Determine which songs to search in
    if century == '1900':
        search_pool = get_songs_by_century(1900)
    elif century == '2000':
        search_pool = get_songs_by_century(2000)
    else:
        search_pool = top_100_songs
    
    results = []
    for song in search_pool:
        if (query in song['title'].lower() or 
            query in song['artist'].lower() or
            query in str(song['year'])):
            results.append(song)
    
    return jsonify({
        'query': query,
        'century': century if century else 'all',
        'results': results[:20],
        'count': len(results)
    })

# ==================== ADMIN ENDPOINTS (Require admin API key) ====================

@app.route('/admin/endpoints', methods=['GET'])
@admin_required
def get_all_endpoints():
    """Get all available endpoints (admin only)"""
    endpoints = {
        'public_endpoints': {
            'GET /health': 'Service health check',
            'GET /songs/top100': 'Get overall top 100 songs',
            'GET /songs/century/1900': 'Get top 100 songs of 1900s',
            'GET /songs/century/2000': 'Get top 100 songs of 2000s',
            'GET /songs/search?q=<query>&century=<1900|2000>': 'Search songs (API only)',
            'POST /play': 'Record song play (requires auth)'
        },
        'admin_endpoints': {
            'GET /admin/endpoints': 'List all endpoints (this endpoint)',
            'GET /admin/all-songs': 'Get all songs in database',
            'GET /admin/song-analytics': 'Get song analytics',
            'GET /admin/system-stats': 'Get system statistics',
            'GET /admin/years': 'Get overview of all years',
            'GET /admin/songs/year/<year>': 'Get top 100 songs for specific year',
            'GET /admin/centuries/comparison': 'Compare centuries',
            'GET /admin/debug/data': 'Debug data endpoint',
            'GET /admin/debug/mongodb-structure': 'Debug MongoDB structure',
            'POST /admin/reload-songs': 'Reload songs from MongoDB'
        },
        'authentication': {
            'note': 'Admin endpoints require X-Admin-Key header with admin API key',
            'admin_api_key': admin_api_key
        }
    }
    return jsonify(endpoints)

@app.route('/admin/all-songs', methods=['GET'])
@admin_required
def get_all_songs():
    """Get all songs (admin only)"""
    return jsonify({
        'songs': all_songs,
        'count': len(all_songs),
        'message': 'All songs (admin access)'
    })

@app.route('/admin/song-analytics', methods=['GET'])
@admin_required
def get_song_analytics():
    """Get song analytics (admin only)"""
    analytics = {
        'total_songs': len(all_songs),
        'by_year': {},
        'by_artist': {},
        'top_songs': [],
        'top_artists': []
    }
    
    for song in all_songs:
        year = song.get('year', 1958)
        analytics['by_year'][year] = analytics['by_year'].get(year, 0) + 1
        
        artist = song.get('artist', 'Unknown')
        analytics['by_artist'][artist] = analytics['by_artist'].get(artist, 0) + 1
    
    if len(all_songs) > 0:
        analytics['top_songs'] = [{'title': s['title'], 'artist': s['artist'], 'popularity': s['popularity']} 
                                  for s in sorted(all_songs, key=lambda x: x['popularity'], reverse=True)[:10]]
    
    if analytics['by_artist']:
        sorted_artists = sorted(analytics['by_artist'].items(), key=lambda x: x[1], reverse=True)[:10]
        analytics['top_artists'] = [{'artist': a[0], 'song_count': a[1]} for a in sorted_artists]
    
    return jsonify(analytics)

@app.route('/admin/system-stats', methods=['GET'])
@admin_required
def get_system_stats():
    """Get system statistics (admin only)"""
    mongodb_weekly_charts = 0
    if songs_collection is not None:
        try:
            mongodb_weekly_charts = songs_collection.estimated_document_count()
        except:
            mongodb_weekly_charts = 0
    
    available_years = get_available_years()
    
    return jsonify({
        'service': 'music-service',
        'songs_loaded': len(all_songs),
        'top_100_loaded': len(top_100_songs),
        'available_years': available_years,
        'years_count': len(available_years),
        'century_1900_count': len(get_songs_by_century(1900)),
        'century_2000_count': len(get_songs_by_century(2000)),
        'kafka_connected': producer is not None,
        'mongodb_connected': mongodb_client is not None,
        'admin_api_key_enabled': True,
        'uptime': time.time() - app_start_time
    })

@app.route('/admin/years', methods=['GET'])
@admin_required
def get_years_overview():
    """Get overview of all years (admin only)"""
    years = get_available_years()
    
    year_stats = []
    for year in years:
        year_songs = get_songs_by_year(year)
        year_stats.append({
            'year': year,
            'song_count': len(year_songs),
            'top_song': year_songs[0] if year_songs else None
        })
    
    return jsonify({
        'years': year_stats,
        'total_years': len(years),
        'available_years': years
    })

@app.route('/admin/songs/year/<int:year>', methods=['GET'])
@admin_required
def get_year_top100(year):
    """Get top 100 songs for a specific year (admin only)"""
    year_songs = get_songs_by_year(year)
    
    if not year_songs:
        return jsonify({
            'error': f'No data available for year {year}',
            'available_years': get_available_years()
        }), 404
    
    return jsonify({
        'songs': year_songs,
        'count': len(year_songs),
        'year': year,
        'message': f'Top 100 songs of {year}',
        'available_years': get_available_years()
    })

@app.route('/admin/centuries/comparison', methods=['GET'])
@admin_required
def get_centuries_comparison():
    """Get comparison data between centuries (admin only)"""
    century_1900 = get_songs_by_century(1900)
    century_2000 = get_songs_by_century(2000)
    
    def calculate_stats(songs, century):
        if not songs:
            return {
                'century': century,
                'song_count': 0,
                'avg_popularity': 0,
                'top_artists': [],
                'year_range': []
            }
        
        popularity_key = 'century_popularity' if century == 1900 or century == 2000 else 'popularity'
        avg_popularity = sum(song.get(popularity_key, 0) for song in songs) / len(songs)
        
        artist_counts = Counter(song['artist'] for song in songs)
        top_artists = [{'artist': artist, 'count': count} for artist, count in artist_counts.most_common(5)]
        
        years = [song['year'] for song in songs]
        
        return {
            'century': century,
            'song_count': len(songs),
            'avg_popularity': round(avg_popularity, 2),
            'top_artists': top_artists,
            'year_range': [min(years), max(years)] if years else []
        }
    
    return jsonify({
        'century_1900': calculate_stats(century_1900, 1900),
        'century_2000': calculate_stats(century_2000, 2000),
        'comparison': {
            'total_songs': len(century_1900) + len(century_2000),
            'century_with_more_songs': 1900 if len(century_1900) > len(century_2000) else 2000
        }
    })

@app.route('/admin/debug/data', methods=['GET'])
@admin_required
def debug_data():
    """Debug endpoint (admin only)"""
    try:
        if mongodb_client is None or songs_collection is None:
            return jsonify({'error': 'MongoDB not connected'})
        
        sample_week = songs_collection.find_one({}, {"date": 1, "data": {"$slice": 1}})
        
        first_song_info = None
        if sample_week and 'data' in sample_week and len(sample_week['data']) > 0:
            first_song = sample_week['data'][0]
            first_song_info = {
                'song': first_song.get('song', 'Unknown'),
                'artist': first_song.get('artist', 'Unknown'),
                'peak_position': first_song.get('peak_position'),
                'weeks_on_chart': first_song.get('weeks_on_chart')
            }
        
        return jsonify({
            'mongodb_status': 'connected',
            'database': MONGODB_DB,
            'collection': MONGODB_COLLECTION,
            'sample_chart_date': sample_week.get('date') if sample_week else None,
            'first_song_in_sample': first_song_info,
            'processed_songs_count': len(all_songs)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/admin/debug/mongodb-structure', methods=['GET'])
@admin_required
def debug_mongodb_structure():
    """Show MongoDB data structure (admin only)"""
    try:
        if mongodb_client is None or songs_collection is None:
            return jsonify({'error': 'MongoDB not connected'})
        
        weeks = list(songs_collection.find().limit(3))
        
        simplified_weeks = []
        for week in weeks:
            simplified_week = {
                'date': week.get('date'),
                'total_songs_in_week': len(week.get('data', [])),
                'first_few_songs': []
            }
            
            for song in week.get('data', [])[:3]:
                simplified_week['first_few_songs'].append({
                    'song': song.get('song'),
                    'artist': song.get('artist'),
                    'peak_position': song.get('peak_position')
                })
            
            simplified_weeks.append(simplified_week)
        
        return jsonify({
            'mongodb_structure': 'Weekly charts with songs in data array',
            'sample_weeks': simplified_weeks,
            'total_weeks_in_db': songs_collection.estimated_document_count()
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/admin/reload-songs', methods=['POST'])
@admin_required
def reload_songs():
    """Reload songs from MongoDB (admin only)"""
    global all_songs, top_100_songs
    all_songs = load_and_process_music_data()
    top_100_songs = all_songs[:100] if len(all_songs) > 0 else []
    
    return jsonify({
        'message': 'Songs reloaded from MongoDB',
        'total_songs': len(all_songs),
        'top_100_songs': len(top_100_songs)
    })

# ==================== AUTHENTICATED ENDPOINTS ====================

@app.route('/play', methods=['POST'])
@admin_or_token_required
def record_play():
    """Record a song play (requires auth)"""
    track_endpoint_usage('record_play')
    data = request.get_json()
    song_title = data.get('song', 'Unknown')
    artist = data.get('artist', 'Unknown')
    
    song = next((s for s in top_100_songs if s['title'] == song_title and s['artist'] == artist), None)
    
    play_event = {
        'song': song_title,
        'artist': artist,
        'song_id': song['id'] if song else 'unknown',
        'timestamp': time.time(),
        'user': request.user.get('username', 'anonymous'),
        'action': 'play'
    }
    
    if producer is not None:
        producer.send('song_plays', value=play_event)
        producer.flush()
        print(f"🎵 Sent play event to Kafka: {song_title}")
    
    return jsonify({
        'message': 'Play recorded',
        'song': song_title,
        'artist': artist
    })

# ==================== TEST ENDPOINTS ====================

@app.route('/test', methods=['GET'])
def test():
    """Test endpoint (public)"""
    return jsonify({
        'message': 'Music service is running',
        'features': ['century_view', 'year_analysis', 'search', 'top_100', 'admin_api'],
        'admin_api_note': 'Use X-Admin-Key header with value: ' + admin_api_key,
        'test_endpoints': {
            'public': '/test, /health, /songs/top100',
            'admin': '/admin/endpoints (with X-Admin-Key)'
        }
    })

@app.route('/test/admin', methods=['GET'])
@admin_required
def test_admin():
    """Test admin endpoint"""
    return jsonify({
        'message': 'Admin access successful',
        'user': request.user,
        'admin_key_used': 'X-Admin-Key' in request.headers
    })

# Track app start time
app_start_time = time.time()

if __name__ == '__main__':
    print("🚀 Music Service starting on http://localhost:5000")
    print(f"🔐 Authentication: JWT tokens or admin API key")
    print(f"🔑 Admin API Key: {admin_api_key}")
    print(f"📡 Kafka: {bootstrap_servers}")
    print(f"🗄️ MongoDB: {MONGODB_DB}.{MONGODB_COLLECTION}")
    print(f"🎵 Loaded {len(all_songs)} songs")
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)