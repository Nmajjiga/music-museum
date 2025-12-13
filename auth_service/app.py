from flask import Flask, request, jsonify
import jwt
import datetime
import os
from functools import wraps
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-key-change-me')

# Initialize with only two users
users = {}

def initialize_users():
    """Initialize the two required users"""
    global users
    users = {
        'admin': {
            'password': 'admin123',
            'role': 'admin',
            'created_at': datetime.datetime.utcnow().isoformat(),
            'permissions': ['admin:read', 'admin:write', 'user:read', 'stats:full']
        },
        'user': {
            'password': 'user123', 
            'role': 'user',
            'created_at': datetime.datetime.utcnow().isoformat(),
            'permissions': ['user:read', 'stats:basic']
        }
    }
    print(f"✅ Initialized {len(users)} users: {', '.join(users.keys())}")

# Initialize users on startup
initialize_users()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing', 'code': 'AUTH_001'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            
            # Validate user exists and token hasn't been tampered with
            username = data.get('username')
            if username not in users:
                return jsonify({'error': 'User no longer exists', 'code': 'AUTH_002'}), 401
                
            request.current_user = data
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired', 'code': 'AUTH_003'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token', 'code': 'AUTH_004'}), 401
        except Exception as e:
            return jsonify({'error': 'Token validation failed', 'code': 'AUTH_005'}), 401
        
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'current_user') or request.current_user['role'] != 'admin':
            return jsonify({'error': 'Admin access required', 'code': 'AUTH_006'}), 403
        
        # Additional admin validation
        if request.current_user['username'] != 'admin':
            return jsonify({'error': 'Invalid admin credentials', 'code': 'AUTH_007'}), 403
            
        return f(*args, **kwargs)
    return decorated

def has_permission(permission):
    """Check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required', 'code': 'AUTH_008'}), 401
            
            username = request.current_user['username']
            if username not in users:
                return jsonify({'error': 'User not found', 'code': 'AUTH_009'}), 401
            
            user_permissions = users[username].get('permissions', [])
            if permission not in user_permissions:
                return jsonify({'error': f'Permission denied: {permission}', 'code': 'AUTH_010'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.route('/auth/login', methods=['POST'])
def login():
    """Login endpoint - only allows admin and user"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required', 'code': 'AUTH_011'}), 400
    
    # Only allow admin and user
    if username not in ['admin', 'user']:
        return jsonify({'error': 'Invalid username', 'code': 'AUTH_012'}), 401
    
    user = users.get(username)
    if not user or user['password'] != password:
        return jsonify({'error': 'Invalid credentials', 'code': 'AUTH_013'}), 401
    
    # Generate JWT token
    token_payload = {
        'username': username,
        'role': user['role'],
        'permissions': user.get('permissions', []),
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    
    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {
            'username': username,
            'role': user['role'],
            'permissions': user.get('permissions', [])
        },
        'expires_in': '24 hours'
    })

@app.route('/auth/validate', methods=['POST'])
@token_required
def validate_token():
    """Validate token endpoint"""
    return jsonify({
        'valid': True,
        'user': request.current_user,
        'permissions': users.get(request.current_user['username'], {}).get('permissions', [])
    })

@app.route('/auth/admin/users', methods=['GET'])
@token_required
@admin_required
@has_permission('admin:read')
def get_users():
    """Admin-only: Get all users"""
    user_list = []
    for username, info in users.items():
        user_list.append({
            'username': username,
            'role': info['role'],
            'created_at': info.get('created_at'),
            'permissions': info.get('permissions', [])
        })
    
    return jsonify({
        'users': user_list,
        'count': len(user_list),
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

@app.route('/auth/admin/user/<username>', methods=['GET'])
@token_required
@admin_required
@has_permission('admin:read')
def get_user(username):
    """Admin-only: Get specific user details"""
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    user_info = users[username]
    return jsonify({
        'username': username,
        'role': user_info['role'],
        'permissions': user_info.get('permissions', []),
        'created_at': user_info.get('created_at')
    })

@app.route('/auth/admin/reset', methods=['POST'])
@token_required
@admin_required
@has_permission('admin:write')
def reset_users():
    """Admin-only: Reset users to initial state"""
    initialize_users()
    return jsonify({
        'message': 'Users reset to initial state',
        'users': list(users.keys()),
        'reset_by': request.current_user['username']
    })

@app.route('/auth/permissions', methods=['GET'])
@token_required
def get_permissions():
    """Get current user's permissions"""
    username = request.current_user['username']
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'username': username,
        'permissions': users[username].get('permissions', []),
        'role': users[username]['role']
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'auth-service',
        'users_configured': len(users),
        'allowed_users': list(users.keys()),
        'admin_enabled': 'admin' in users,
        'version': '1.2'
    })

@app.route('/auth/test/admin', methods=['GET'])
@token_required
@admin_required
def test_admin():
    """Test admin access"""
    return jsonify({
        'message': 'Admin access confirmed',
        'user': request.current_user,
        'permissions': users.get(request.current_user['username'], {}).get('permissions', []),
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

@app.route('/auth/test/user', methods=['GET'])
@token_required
def test_user():
    """Test user access"""
    return jsonify({
        'message': 'User access confirmed',
        'user': request.current_user,
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5002))
    print(f"Auth Service on port {port}")
    print(f"Users: {', '.join(users.keys())}")
    print(f"Health: http://localhost:{port}/health")
    print(f"Login: POST http://localhost:{port}/auth/login")
    print(f"Admin test: GET http://localhost:{port}/auth/test/admin (requires admin token)")
    print(f"User test: GET http://localhost:{port}/auth/test/user (requires any token)")
    app.run(host='0.0.0.0', port=port, debug=False)