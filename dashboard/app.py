import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import os

# Configuration
MUSIC_URL = os.getenv('MUSIC_SERVICE_URL', 'http://localhost:5000')
STATS_URL = os.getenv('STATS_SERVICE_URL', 'http://localhost:5001')
AUTH_URL = os.getenv('AUTH_SERVICE_URL', 'http://localhost:5002')

st.set_page_config(
    page_title="Music Museum Dashboard",
    page_icon="",
    layout="wide"
)

# Initialize session state
if 'token' not in st.session_state:
    st.session_state.token = None
if 'user' not in st.session_state:
    st.session_state.user = None
if 'role' not in st.session_state:
    st.session_state.role = None
if 'songs' not in st.session_state:
    st.session_state.songs = []
if 'century_data' not in st.session_state:
    st.session_state.century_data = {'1900': [], '2000': []}

def login(username, password):
    """Authenticate user with auth service"""
    try:
        response = requests.post(
            f"{AUTH_URL}/auth/login",
            json={'username': username, 'password': password},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.token = data['token']
            st.session_state.user = data['user']['username']
            st.session_state.role = data['user']['role']
            return True
        else:
            return False
    except:
        return False

def logout():
    """Logout user"""
    st.session_state.token = None
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.songs = []
    st.session_state.century_data = {'1900': [], '2000': []}
    st.rerun()

def make_request(url, method='GET', params=None):
    """Make HTTP request with auth token"""
    if not st.session_state.token:
        return None
    
    headers = {'Authorization': st.session_state.token}
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=params, timeout=10)
        return response
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None

def check_services():
    """Check service availability"""
    services = {}
    for service, url in [('music', MUSIC_URL), ('stats', STATS_URL), ('auth', AUTH_URL)]:
        try:
            resp = requests.get(f"{url}/health", timeout=3)
            services[service] = resp.status_code == 200
        except:
            services[service] = False
    return services

# Login page
if not st.session_state.token:
    st.title("🎵 Music Museum Dashboard")
    
    services = check_services()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Login")
        
        # Service status
        st.write("**Service Status:**")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Auth", "✅" if services['auth'] else "❌")
        with col_b:
            st.metric("Music", "✅" if services['music'] else "❌")
        with col_c:
            st.metric("Stats", "✅" if services['stats'] else "❌")
        
        if not services['auth']:
            st.error("Auth service unavailable. Please start auth service on port 5002.")
        
        username = st.text_input("Username", value="admin")
        password = st.text_input("Password", type="password", value="admin123")
        
        if st.button("Login", type="primary", use_container_width=True):
            if login(username, password):
                st.success(f"Welcome {st.session_state.user}!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Login failed. Check credentials and service status.")
        
        st.markdown("---")
        st.markdown("**Demo Accounts:**")
        st.code("Admin: admin / admin123")
        st.code("User: user / user123")
        st.markdown("*Start auth service on port 5002 for login*")
    
    st.stop()

# Main dashboard
with st.sidebar:
    st.title(f"Welcome, {st.session_state.user}!")
    st.caption(f"Role: {st.session_state.role}")
    
    if st.session_state.role == 'admin':
        pages = ["Top Songs", "Century View", "Search", "Statistics", "Admin Panel", "System Health"]
    else:
        pages = ["Top Songs", "Century View", "Search", "Statistics"]
    page = st.radio("Navigate", pages, label_visibility="collapsed")
    
    st.divider()
    
    # Service status
    services = check_services()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Auth", "✅" if services['auth'] else "❌")
    with col2:
        st.metric("Music", "✅" if services['music'] else "❌")
    with col3:
        st.metric("Stats", "✅" if services['stats'] else "❌")
    
    if st.button("Logout", type="secondary", use_container_width=True):
        logout()

# Page: Top Songs
if page == "Top Songs":
    st.title("Top 100 Billboard Songs")
    
    if st.button("Load Songs", type="primary"):
        with st.spinner("Loading..."):
            response = make_request(f"{MUSIC_URL}/songs/top100")
            if response and response.status_code == 200:
                data = response.json()
                st.session_state.songs = data.get('songs', [])
                st.success(f"Loaded {len(st.session_state.songs)} songs")
            else:
                st.error("Failed to load songs")
    
    if st.session_state.songs:
        songs_df = pd.DataFrame(st.session_state.songs)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total", len(songs_df))
        with col2:
            st.metric("Artists", songs_df['artist'].nunique())
        with col3:
            st.metric("Avg Peak", f"{songs_df['peak_position'].mean():.1f}")
        
        # Display top 5 songs
        for idx, song in enumerate(st.session_state.songs[:5]):
            with st.expander(f"#{idx+1}: {song['title']}"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f"**Artist:** {song['artist']}")
                    st.write(f"**Peak:** #{song['peak_position']}")
                with col_b:
                    st.write(f"**Weeks:** {song['weeks_on_chart']}")
                    st.write(f"**This Week:** #{song['this_week']}")

# Page: Century View
elif page == "Century View":
    st.title("Century Filtering")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Load 1900s Songs", use_container_width=True):
            response = make_request(f"{MUSIC_URL}/songs/century/1900")
            if response and response.status_code == 200:
                data = response.json()
                st.session_state.century_data['1900'] = data.get('songs', [])
                st.success(f"Loaded {len(st.session_state.century_data['1900'])} 1900s songs")
            else:
                st.error("Failed to load 1900s songs")
    
    with col2:
        if st.button("Load 2000s Songs", use_container_width=True):
            response = make_request(f"{MUSIC_URL}/songs/century/2000")
            if response and response.status_code == 200:
                data = response.json()
                st.session_state.century_data['2000'] = data.get('songs', [])
                st.success(f"Loaded {len(st.session_state.century_data['2000'])} 2000s songs")
            else:
                st.error("Failed to load 2000s songs")
    
    tab1, tab2 = st.tabs(["1900s (1958-1999)", "2000s (2000-present)"])
    
    with tab1:
        if st.session_state.century_data['1900']:
            songs_df = pd.DataFrame(st.session_state.century_data['1900'])
            st.subheader(f"1900s Songs: {len(songs_df)} unique")
            st.write(f"**Sample Songs:**")
            for song in st.session_state.century_data['1900'][:3]:
                st.write(f"- {song['title']} by {song['artist']} (Peak: #{song['peak_position']})")
        else:
            st.info("Load 1900s songs to see data")
    
    with tab2:
        if st.session_state.century_data['2000']:
            songs_df = pd.DataFrame(st.session_state.century_data['2000'])
            st.subheader(f"2000s Songs: {len(songs_df)} unique")
            st.write(f"**Sample Songs:**")
            for song in st.session_state.century_data['2000'][:3]:
                st.write(f"- {song['title']} by {song['artist']} (Peak: #{song['peak_position']})")
        else:
            st.info("Load 2000s songs to see data")

# Page: Search
elif page == "Search":
    st.title("Search Songs")
    
    query = st.text_input("Search by title or artist:")
    
    if query and len(query) >= 2:
        response = make_request(f"{MUSIC_URL}/songs/search", params={'q': query})
        if response and response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                st.success(f"Found {len(results)} results")
                for song in results[:5]:
                    st.write(f"**{song['title']}** - *{song['artist']}*")
                    st.write(f"Peak: #{song['peak_position']} | Weeks: {song['weeks_on_chart']}")
                    st.divider()
            else:
                st.info("No results found")

# Page: Statistics
elif page == "Statistics":
    st.title("Usage Statistics")
    
    if st.button("Load Statistics", type="primary"):
        response = make_request(f"{STATS_URL}/admin/statistics")
        if response and response.status_code == 200:
            stats = response.json()
            st.session_state.stats = stats
            st.success("Statistics loaded")
        else:
            st.error("Failed to load statistics")
    
    if hasattr(st.session_state, 'stats') and st.session_state.stats:
        stats = st.session_state.stats
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Events", stats['summary']['total_events'])
        col2.metric("Unique Users", stats['summary']['unique_users'])
        col3.metric("Unique Endpoints", stats['summary']['unique_endpoints'])
        col4.metric("Uptime (hrs)", f"{stats['summary']['uptime_hours']:.1f}")

# Page: Admin
elif page == "Admin" and st.session_state.role == 'admin':
    st.title("Admin Panel")
    
    if st.button("Reload All Songs", type="primary"):
        response = make_request(f"{MUSIC_URL}/admin/reload", method='POST')
        if response and response.status_code == 200:
            st.success("Songs reloaded successfully")
        else:
            st.error("Failed to reload songs")
    
    if st.button("Reset Statistics", type="secondary"):
        response = make_request(f"{STATS_URL}/test/reset", method='POST')
        if response and response.status_code == 200:
            st.success("Statistics reset")
        else:
            st.error("Failed to reset statistics")

elif page == "System Health" and st.session_state.role == 'admin':
    st.title("System Health Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Check All Services", type="primary"):
            with st.spinner("Checking services..."):
                # Check auth service
                auth_response = requests.get(f"{AUTH_URL}/health", timeout=5)
                auth_ok = auth_response.status_code == 200
                
                # Check music service  
                music_response = requests.get(f"{MUSIC_URL}/health", timeout=5)
                music_ok = music_response.status_code == 200
                
                # Check stats service
                stats_response = requests.get(f"{STATS_URL}/health", timeout=5)
                stats_ok = stats_response.status_code == 200
                
                st.success("Health checks completed")
                
                # Display results
                status_col1, status_col2, status_col3 = st.columns(3)
                with status_col1:
                    st.metric("Auth Service", "✅" if auth_ok else "❌")
                with status_col2:
                    st.metric("Music Service", "✅" if music_ok else "❌")
                with status_col3:
                    st.metric("Stats Service", "✅" if stats_ok else "❌")
    
    with col2:
        if st.button("Test Admin Access", type="secondary"):
            response = make_request(f"{AUTH_URL}/auth/test/admin")
            if response and response.status_code == 200:
                st.success("✅ Admin access confirmed")
                st.json(response.json())
            else:
                st.error("❌ Admin access failed")
    
    # System metrics
    st.subheader("Admin Tools")
    
    tab1, tab2, tab3 = st.tabs(["User Management", "System Logs", "Security"])
    
    with tab1:
        if st.button("List All Users"):
            response = make_request(f"{AUTH_URL}/auth/admin/users")
            if response and response.status_code == 200:
                users_data = response.json()
                st.write(f"**Total Users:** {users_data['count']}")
                for user in users_data['users']:
                    with st.expander(f"👤 {user['username']} ({user['role']})"):
                        st.write(f"**Role:** {user['role']}")
                        st.write(f"**Permissions:** {', '.join(user['permissions'])}")
                        st.write(f"**Created:** {user['created_at']}")
            else:
                st.error("Failed to fetch users")
    
    with tab2:
        if st.button("View System Logs"):
            st.info("System logs would be displayed here")
            st.code("""
            [2025-01-15 10:30:45] INFO: Admin user 'admin' accessed statistics
            [2025-01-15 10:31:12] INFO: User 'user' loaded 1900s songs
            [2025-01-15 10:32:05] INFO: Stats service processed 150 events
            """)
    
    with tab3:
        st.write("**Security Settings**")
        if st.button("Reset Statistics Database"):
            response = make_request(f"{STATS_URL}/admin/reset", method='POST')
            if response and response.status_code == 200:
                st.success("✅ Statistics reset successfully")
                st.json(response.json())
            else:
                st.error("❌ Failed to reset statistics")
        
        if st.button("Reset User Database"):
            response = make_request(f"{AUTH_URL}/auth/admin/reset", method='POST')
            if response and response.status_code == 200:
                st.success("✅ Users reset to initial state")
                st.json(response.json())
            else:
                st.error("❌ Failed to reset users")