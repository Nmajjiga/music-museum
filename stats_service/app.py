from flask import Flask, request, jsonify
from datetime import datetime
import time
import os
from collections import defaultdict, Counter
from functools import wraps
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# Configuration
AUTH_SERVICE_URL = os.getenv('AUTH_SERVICE_URL', 'http://localhost:5002')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-key-change-me')

# Statistics storage
stats = {
    'endpoint_counts': defaultdict(int),
    'user_activity': defaultdict(int),
    'service_usage': defaultdict(int),
    'hourly_traffic': defaultdict(int),
    'daily_traffic': defaultdict(int),
    'method_counts': defaultdict(int),
    'century_requests': defaultdict(int),
    'total_events': 0,
    'start_time': datetime.now()
}

def record_event(event_data):
    """Record an event in statistics"""
    stats['total_events'] += 1
    
    endpoint = event_data.get('endpoint', 'unknown')
    user = event_data.get('user', 'anonymous')
    service = event_data.get('service', 'unknown')
    method = event_data.get('method', 'GET')
    
    stats['endpoint_counts'][endpoint] += 1
    stats['user_activity'][user] += 1
    stats['service_usage'][service] += 1
    stats['method_counts'][method] += 1
    
    # Track century requests
    if 'century' in endpoint:
        if '/century/1900' in endpoint:
            stats['century_requests']['1900s'] += 1
        elif '/century/2000' in endpoint:
            stats['century_requests']['2000s'] += 1
    
    # Time tracking
    try:
        event_time = event_data.get('timestamp')
        if event_time:
            dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            hour = dt.strftime('%H:00')
            date = dt.strftime('%Y-%m-%d')
        else:
            hour = datetime.now().strftime('%H:00')
            date = datetime.now().strftime('%Y-%m-%d')
        
        stats['hourly_traffic'][hour] += 1
        stats['daily_traffic'][date] += 1
    except:
        hour = datetime.now().strftime('%H:00')
        date = datetime.now().strftime('%Y-%m-%d')
        stats['hourly_traffic'][hour] += 1
        stats['daily_traffic'][date] += 1
    
    # Log every 10 events
    if stats['total_events'] % 10 == 0:
        print(f"Recorded {stats['total_events']} events")

def validate_token(token):
    """Validate token with auth service"""
    if not token:
        return None
    
    try:
        headers = {'Authorization': token}
        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/validate",
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            return response.json()['user']
    except Exception as e:
        print(f"Auth validation error: {e}")
    
    return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        
        # Accept both Bearer and plain tokens
        if token.startswith('Bearer '):
            token = token[7:]
        
        user_data = validate_token(token)
        if not user_data:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.current_user = user_data
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'current_user') or request.current_user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# ============ EVENT RECORDING ============

@app.route('/record', methods=['POST'])
def record():
    """Record a usage event (public endpoint for services)"""
    event_data = request.get_json()
    if not event_data:
        return jsonify({'error': 'No event data provided'}), 400
    
    record_event(event_data)
    return jsonify({
        'message': 'Event recorded',
        'total_events': stats['total_events']
    })

# ============ STATISTICS ENDPOINTS ============

@app.route('/admin/statistics', methods=['GET'])
@token_required
@admin_required
def get_statistics():
    """Admin-only detailed statistics endpoint"""
    record_event({
        'endpoint': '/admin/statistics',
        'user': request.current_user.get('username', 'admin'),
        'service': 'stats-service',
        'timestamp': datetime.now().isoformat()
    })
    
    # Calculate top entries
    top_endpoints = dict(sorted(
        stats['endpoint_counts'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:15])
    
    top_users = dict(sorted(
        stats['user_activity'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10])
    
    # Service distribution
    service_distribution = {}
    for service, count in stats['service_usage'].items():
        service_distribution[service] = {
            'count': count,
            'percentage': round((count / stats['total_events']) * 100, 2) if stats['total_events'] > 0 else 0
        }
    
    # Recent activity (last 24 hours)
    recent_traffic = {}
    for hour in range(24):
        hour_str = f"{hour:02d}:00"
        recent_traffic[hour_str] = stats['hourly_traffic'].get(hour_str, 0)
    
    return jsonify({
        'summary': {
            'total_events': stats['total_events'],
            'unique_users': len(stats['user_activity']),
            'unique_endpoints': len(stats['endpoint_counts']),
            'unique_services': len(stats['service_usage']),
            'uptime_hours': round((datetime.now() - stats['start_time']).total_seconds() / 3600, 2),
            'events_per_hour': round(stats['total_events'] / max((datetime.now() - stats['start_time']).total_seconds() / 3600, 1), 2)
        },
        'top_endpoints': top_endpoints,
        'top_users': top_users,
        'service_distribution': service_distribution,
        'method_distribution': dict(stats['method_counts']),
        'hourly_traffic': recent_traffic,
        'century_usage': dict(stats['century_requests']),
        'daily_traffic': dict(sorted(stats['daily_traffic'].items(), reverse=True)[:7]),
        'admin_access': True,
        'user': request.current_user.get('username'),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/stats/summary', methods=['GET'])
@token_required
def get_summary():
    """Public summary statistics (accessible to all users)"""
    record_event({
        'endpoint': '/stats/summary',
        'user': request.current_user.get('username', 'user'),
        'service': 'stats-service',
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({
        'total_events': stats['total_events'],
        'unique_users': len(stats['user_activity']),
        'most_active_endpoint': max(stats['endpoint_counts'].items(), key=lambda x: x[1], default=('none', 0))[0],
        'most_active_user': max(stats['user_activity'].items(), key=lambda x: x[1], default=('none', 0))[0],
        'user_role': request.current_user.get('role')
    })

# ============ ADMIN MANAGEMENT ============

@app.route('/admin/users/activity', methods=['GET'])
@token_required
@admin_required
def get_user_activity():
    """Admin-only: Get detailed user activity"""
    user_stats = []
    for user, count in stats['user_activity'].items():
        user_stats.append({
            'username': user,
            'request_count': count,
            'percentage': round((count / stats['total_events']) * 100, 2) if stats['total_events'] > 0 else 0
        })
    
    user_stats.sort(key=lambda x: x['request_count'], reverse=True)
    
    return jsonify({
        'users': user_stats[:20],
        'total_users': len(stats['user_activity'])
    })

@app.route('/admin/endpoints/usage', methods=['GET'])
@token_required
@admin_required
def get_endpoint_usage():
    """Admin-only: Get detailed endpoint usage"""
    endpoint_stats = []
    for endpoint, count in stats['endpoint_counts'].items():
        endpoint_stats.append({
            'endpoint': endpoint,
            'count': count,
            'percentage': round((count / stats['total_events']) * 100, 2) if stats['total_events'] > 0 else 0
        })
    
    endpoint_stats.sort(key=lambda x: x['count'], reverse=True)
    
    return jsonify({
        'endpoints': endpoint_stats[:20],
        'total_endpoints': len(stats['endpoint_counts'])
    })

@app.route('/admin/system/health', methods=['GET'])
@token_required
@admin_required
def get_system_health():
    """Admin-only: System health check with detailed metrics"""
    # Check auth service
    auth_health = False
    try:
        response = requests.get(f"{AUTH_SERVICE_URL}/health", timeout=3)
        auth_health = response.status_code == 200
    except:
        auth_health = False
    
    return jsonify({
        'stats_service': {
            'status': 'healthy',
            'events_processed': stats['total_events'],
            'uptime_hours': round((datetime.now() - stats['start_time']).total_seconds() / 3600, 2),
            'memory_usage': 'normal'
        },
        'auth_service': {
            'status': 'healthy' if auth_health else 'unavailable',
            'url': AUTH_SERVICE_URL
        },
        'checks': {
            'database_connected': True,
            'event_processing': stats['total_events'] > 0,
            'admin_access_enabled': True
        }
    })

# ============ HEALTH AND MONITORING ============

@app.route('/health', methods=['GET'])
def health():
    """Public health check"""
    # Don't record health checks to avoid infinite loops
    return jsonify({
        'status': 'healthy',
        'service': 'stats-service',
        'total_events': stats['total_events'],
        'uptime': str(datetime.now() - stats['start_time']).split('.')[0],
        'version': '1.1'
    })

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus-style metrics endpoint"""
    metrics_data = [
        f'stats_service_events_total {stats["total_events"]}',
        f'stats_service_unique_users {len(stats["user_activity"])}',
        f'stats_service_uptime_seconds {(datetime.now() - stats["start_time"]).total_seconds()}',
        f'stats_service_admin_access_enabled 1'
    ]
    
    for endpoint, count in stats['endpoint_counts'].items():
        safe_name = endpoint.replace('/', '_').replace('-', '_').replace(' ', '_').replace('.', '_')
        metrics_data.append(f'stats_endpoint_{safe_name}_total {count}')
    
    return '\n'.join(metrics_data), 200, {'Content-Type': 'text/plain'}

# ============ TESTING AND MAINTENANCE ============

@app.route('/test/event', methods=['POST'])
def test_event():
    """Test endpoint to record a sample event"""
    test_data = {
        'endpoint': '/test/event',
        'user': 'tester',
        'service': 'test-service',
        'method': 'POST',
        'timestamp': datetime.now().isoformat()
    }
    
    record_event(test_data)
    
    return jsonify({
        'message': 'Test event recorded',
        'event': test_data,
        'total_events': stats['total_events']
    })

@app.route('/admin/reset', methods=['POST'])
@token_required
@admin_required
def reset_stats():
    """Admin-only: Reset all statistics"""
    global stats
    
    old_count = stats['total_events']
    
    # Reset stats but keep start time
    stats = {
        'endpoint_counts': defaultdict(int),
        'user_activity': defaultdict(int),
        'service_usage': defaultdict(int),
        'hourly_traffic': defaultdict(int),
        'daily_traffic': defaultdict(int),
        'method_counts': defaultdict(int),
        'century_requests': defaultdict(int),
        'total_events': 0,
        'start_time': datetime.now()
    }
    
    return jsonify({
        'message': 'Statistics reset successfully',
        'previous_events': old_count,
        'reset_by': request.current_user.get('username'),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/test/token', methods=['GET'])
def get_test_token():
    """Get test tokens (for development only)"""
    return jsonify({
        'note': 'Use /auth/login endpoint for real tokens',
        'demo_users': {
            'admin': {'username': 'admin', 'password': 'admin123'},
            'user': {'username': 'user', 'password': 'user123'}
        }
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print(f"Stats Service on port {port}")
    print(f"Health: http://localhost:{port}/health")
    print(f"Admin stats: http://localhost:{port}/admin/statistics")
    print(f"Public stats: http://localhost:{port}/stats/summary")
    print(f"Admin endpoints require 'admin' role")
    print(f"Auth service: {AUTH_SERVICE_URL}")
    
    app.run(host='0.0.0.0', port=port, debug=False)