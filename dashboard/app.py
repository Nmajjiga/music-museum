import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import sys
import os

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to read config, but use defaults if not available
try:
    import configparser
    config = configparser.ConfigParser()
    config.read('../config.ini')
    
    if config.has_section('dashboard'):
        MUSIC_SERVICE_URL = config.get('dashboard', 'music_service_url', fallback='http://localhost:5000')
        STATS_SERVICE_URL = config.get('dashboard', 'stats_service_url', fallback='http://localhost:5001')
        AUTH_SERVICE_URL = config.get('dashboard', 'auth_service_url', fallback='http://localhost:5002')
        API_KEY = config.get('dashboard', 'api_key', fallback='music-api-key-1')
        ADMIN_API_KEY = config.get('dashboard', 'admin_api_key', fallback='admin-secret-key-123')
    else:
        MUSIC_SERVICE_URL = 'http://localhost:5000'
        STATS_SERVICE_URL = 'http://localhost:5001'
        AUTH_SERVICE_URL = 'http://localhost:5002'
        API_KEY = 'music-api-key-1'
        ADMIN_API_KEY = 'admin-secret-key-123'
except:
    # Use defaults if config fails
    MUSIC_SERVICE_URL = 'http://localhost:5000'
    STATS_SERVICE_URL = 'http://localhost:5001'
    AUTH_SERVICE_URL = 'http://localhost:5002'
    API_KEY = 'music-api-key-1'
    ADMIN_API_KEY = 'admin-secret-key-123'

st.set_page_config(
    page_title="Music Museum",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
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
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'overall'
if 'current_year' not in st.session_state:
    st.session_state.current_year = None
if 'admin_api_key' not in st.session_state:
    st.session_state.admin_api_key = ADMIN_API_KEY
if 'service_status' not in st.session_state:
    st.session_state.service_status = {
        'music': False,
        'stats': False,
        'auth': False
    }

# Helper function to check service availability
def check_services():
    """Check if all services are running"""
    status = {
        'music': False,
        'stats': False,
        'auth': False
    }
    
    try:
        response = requests.get(f"{MUSIC_SERVICE_URL}/health", timeout=3)
        status['music'] = response.status_code == 200
    except:
        status['music'] = False
    
    try:
        response = requests.get(f"{STATS_SERVICE_URL}/health", timeout=3)
        status['stats'] = response.status_code == 200
    except:
        status['stats'] = False
    
    try:
        response = requests.get(f"{AUTH_SERVICE_URL}/health", timeout=3)
        status['auth'] = response.status_code == 200
    except:
        status['auth'] = False
    
    st.session_state.service_status = status
    return status

# Simplified login function
def simple_login(username, password):
    """Simple login for testing without auth service"""
    if username == 'admin' and password == 'admin123':
        st.session_state.user = 'admin'
        st.session_state.role = 'admin'
        st.session_state.token = 'demo-token-admin'
        return True
    elif username == 'user' and password == 'user123':
        st.session_state.user = 'user'
        st.session_state.role = 'user'
        st.session_state.token = 'demo-token-user'
        return True
    return False

def logout():
    """Logout user"""
    st.session_state.token = None
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.songs = []
    st.session_state.current_view = 'overall'
    st.session_state.current_year = None
    st.rerun()

def make_request(url, method='GET', data=None, requires_auth=True, use_admin_key=False):
    """Make HTTP request with error handling"""
    headers = {}
    
    if use_admin_key and st.session_state.admin_api_key:
        headers['X-Admin-Key'] = st.session_state.admin_api_key
    elif requires_auth and st.session_state.token:
        headers['Authorization'] = f"Bearer {st.session_state.token}"
    elif requires_auth and API_KEY:
        headers['X-API-Key'] = API_KEY
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=data, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            return None
        
        return response
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to service at {url}")
        return None
    except requests.exceptions.Timeout:
        st.error(f"Request timed out for {url}")
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None

def load_songs(view='overall', year=None):
    """Load songs based on the current view"""
    if view == 'overall':
        url = f"{MUSIC_SERVICE_URL}/songs/top100"
        response = make_request(url, requires_auth=False)
    elif view in ['1900', '2000']:
        url = f"{MUSIC_SERVICE_URL}/songs/century/{view}"
        response = make_request(url, requires_auth=False)
    elif view == 'year' and year:
        url = f"{MUSIC_SERVICE_URL}/admin/songs/year/{year}"
        response = make_request(url, use_admin_key=True)
    else:
        return False
    
    if response and response.status_code == 200:
        data = response.json()
        st.session_state.songs = data.get('songs', [])
        return True
    return False

# Login page
if not st.session_state.token:
    st.title("🎵 Music Museum Login")
    st.markdown("---")
    
    # Check services first
    status = check_services()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container():
            st.subheader("Login to Music Museum")
            
            # Service status indicator
            st.markdown("### Service Status")
            status_col1, status_col2, status_col3 = st.columns(3)
            with status_col1:
                st.metric("Music API", "✅" if status['music'] else "❌")
            with status_col2:
                st.metric("Stats API", "✅" if status['stats'] else "❌")
            with status_col3:
                st.metric("Auth API", "✅" if status['auth'] else "⚠️")
            
            if not status['music']:
                st.warning("⚠️ Music service is not running. Please start it on port 5000.")
            
            st.markdown("---")
            
            username = st.text_input("Username", value="admin")
            password = st.text_input("Password", type="password", value="admin123")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Login (Demo Mode)", type="primary", use_container_width=True):
                    if simple_login(username, password):
                        st.success("Logged in successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
            
            with col_b:
                if st.button("Try Auth Service", type="secondary", use_container_width=True):
                    if status['auth']:
                        try:
                            response = requests.post(
                                f"{AUTH_SERVICE_URL}/auth/login",
                                json={'username': username, 'password': password},
                                timeout=5
                            )
                            if response.status_code == 200:
                                data = response.json()
                                st.session_state.token = data['token']
                                st.session_state.user = data['user']['username']
                                st.session_state.role = data['user']['role']
                                st.success("Logged in via Auth Service!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Auth service login failed")
                        except:
                            st.error("Cannot connect to auth service")
                    else:
                        st.warning("Auth service not available")
            
            st.markdown("---")
            st.markdown("#### Demo Accounts")
            st.code("Admin: username=admin, password=admin123")
            st.code("User: username=user, password=user123")
            st.markdown("#### Admin Access:")
            st.markdown("- Use admin API key: `admin-secret-key-123`")
            st.markdown("- Admin endpoints require `X-Admin-Key` header")
    
    st.stop()

# Main application (user is logged in)
# Sidebar
with st.sidebar:
    st.title(f"Welcome, {st.session_state.user}!")
    st.caption(f"Role: {st.session_state.role}")
    
    # Admin API Key Section (for admins)
    if st.session_state.role == 'admin':
        st.markdown("### Admin API Key")
        admin_key = st.text_input(
            "Admin API Key",
            value=st.session_state.admin_api_key,
            type="password",
            help="Enter admin API key to access admin endpoints"
        )
        if admin_key != st.session_state.admin_api_key:
            st.session_state.admin_api_key = admin_key
            st.rerun()
        
        st.caption(f"Key: {st.session_state.admin_api_key[:8]}...")
        st.markdown("---")
    
    # Check service status
    status = check_services()
    
    # Navigation based on role
    if st.session_state.role == 'admin':
        pages = ["Song Explorer", "Century View", "Admin Dashboard", "Admin Tools"]
    else:
        pages = ["Song Explorer", "Century View"]
    
    selected_page = st.radio("Navigation", pages)
    
    st.markdown("---")
    
    # View selector (for Song Explorer/Century View)
    if selected_page in ["Song Explorer", "Century View"]:
        st.markdown("### Select View")
        view_options = ["Overall Top 100", "1900s Century", "2000s Century"]
        
        selected_view = st.radio("Music View", view_options, 
                                index=0 if st.session_state.current_view == 'overall' 
                                else 1 if st.session_state.current_view == '1900' 
                                else 2)
        
        # Map selection to view type
        if selected_view == "Overall Top 100":
            st.session_state.current_view = 'overall'
        elif selected_view == "1900s Century":
            st.session_state.current_view = '1900'
        elif selected_view == "2000s Century":
            st.session_state.current_view = '2000'
    
    # System status
    st.markdown("### System Status")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Music API", "✅" if status['music'] else "❌")
    with col2:
        st.metric("Stats API", "✅" if status['stats'] else "❌")
    with col3:
        st.metric("Auth API", "✅" if status['auth'] else "⚠️")
    
    if not status['music']:
        st.error("⚠️ Music service unavailable")
    
    st.markdown("---")
    
    if st.button("Logout", type="secondary"):
        logout()

# USER VIEW: Song Explorer & Century View
if selected_page in ["Song Explorer", "Century View"]:
    if st.session_state.current_view == 'overall':
        st.title("Overall Top 100 Songs")
        st.markdown("Explore the most popular songs from all years")
    elif st.session_state.current_view == '1900':
        st.title("Top 100 Songs of the 1900s")
        st.markdown("Explore the most popular songs from 1958-1999")
    elif st.session_state.current_view == '2000':
        st.title("Top 100 Songs of the 2000s")
        st.markdown("Explore the most popular songs from 2000-2025")
    
    # Check service status
    if not st.session_state.service_status['music']:
        st.error("Music service is not available. Please start the music service on port 5000.")
        st.info("To start the music service, run: `python music_service/app.py`")
    else:
        # Load songs button
        button_label = f"Load Top 100 {st.session_state.current_view.upper() if st.session_state.current_view != 'overall' else ''}Songs"
        if st.button(button_label, type="primary"):
            with st.spinner(f"Loading songs for {st.session_state.current_view}..."):
                if load_songs(view=st.session_state.current_view):
                    st.success(f"Loaded {len(st.session_state.songs)} songs!")
                else:
                    st.error(f"Failed to load songs for {st.session_state.current_view}")
    
    # Display songs if loaded
    if st.session_state.songs:
        songs_df = pd.DataFrame(st.session_state.songs)
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Songs", len(songs_df))
        with col2:
            if 'year' in songs_df.columns and len(songs_df) > 0:
                if st.session_state.current_view == '1900':
                    year_range = "1958-1999"
                elif st.session_state.current_view == '2000':
                    year_range = "2000-2025"
                else:
                    min_year = songs_df['year'].min()
                    max_year = songs_df['year'].max()
                    year_range = f"{min_year}-{max_year}"
                st.metric("Year Range", year_range)
            else:
                st.metric("Year Range", "N/A")
        with col3:
            if 'artist' in songs_df.columns and len(songs_df) > 0:
                top_artist = songs_df['artist'].mode()[0] if len(songs_df['artist'].mode()) > 0 else "N/A"
                st.metric("Top Artist", top_artist[:15])
            else:
                st.metric("Top Artist", "N/A")
        with col4:
            if 'popularity' in songs_df.columns or 'century_popularity' in songs_df.columns:
                pop_col = 'century_popularity' if 'century_popularity' in songs_df.columns else 'popularity'
                avg_popularity = songs_df[pop_col].mean() if len(songs_df) > 0 else 0
                st.metric("Avg Popularity", f"{avg_popularity:.0f}")
            else:
                st.metric("Avg Popularity", "N/A")
        
        # Display songs
        st.subheader(f"Top 10 Songs")
        for idx, song in enumerate(st.session_state.songs[:10], 1):
            with st.expander(f"#{idx}: {song.get('title', 'Unknown')}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Artist:** {song.get('artist', 'Unknown')}")
                    st.write(f"**Year:** {song.get('year', 'N/A')}")
                    st.write(f"**Best Position:** #{song.get('best_position', 'N/A')}")
                with col2:
                    pop_value = song.get('century_popularity', song.get('popularity', 0))
                    st.write(f"**Popularity Score:** {pop_value:.0f}")
                    st.write(f"**Weeks on Chart:** {song.get('weeks_on_chart', 'N/A')}")
                    if st.session_state.current_view != 'overall':
                        st.write(f"**Appearances:** {song.get('appearances', 'N/A')}")
        
        # Visualizations
        if len(songs_df) > 1:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Artist Distribution")
                if 'artist' in songs_df.columns:
                    artist_counts = songs_df['artist'].value_counts().head(10)
                    fig = px.pie(
                        values=artist_counts.values,
                        names=artist_counts.index,
                        title="Top 10 Artists"
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Year Distribution")
                if 'year' in songs_df.columns:
                    year_counts = songs_df['year'].value_counts().sort_index()
                    fig = px.bar(
                        x=year_counts.index,
                        y=year_counts.values,
                        title="Songs by Year",
                        labels={'x': 'Year', 'y': 'Number of Songs'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        # Full table
        with st.expander("View All Songs"):
            display_cols = []
            for col in ['title', 'artist', 'year', 'best_position', 'weeks_on_chart', 'popularity', 'century_popularity']:
                if col in songs_df.columns:
                    display_cols.append(col)
            
            if display_cols:
                display_df = songs_df[display_cols]
                st.dataframe(display_df)
    else:
        view_name = {
            'overall': 'Overall Top 100',
            '1900': '1900s Century',
            '2000': '2000s Century'
        }.get(st.session_state.current_view, 'Songs')
        st.info(f"Click 'Load {view_name}' to explore music history")

# ADMIN VIEW: Admin Dashboard
elif selected_page == "Admin Dashboard" and st.session_state.role == 'admin':
    st.title("Admin Dashboard")
    st.markdown("Access all admin endpoints using the admin API key")
    
    # Test admin access
    if st.button("Test Admin Access", type="primary"):
        with st.spinner("Testing admin access..."):
            response = make_request(f"{MUSIC_SERVICE_URL}/test/admin", use_admin_key=True)
            
            if response and response.status_code == 200:
                data = response.json()
                st.success("Admin access successful!")
                st.json(data)
            else:
                st.error("Admin access failed. Check your admin API key.")
    
    # Admin API Key Info
    st.markdown("---")
    st.subheader("Admin API Key Configuration")
    col1, col2 = st.columns(2)
    with col1:
        st.code(f"Current Key: {st.session_state.admin_api_key}")
    with col2:
        if st.button("Copy to Clipboard"):
            st.code("Copied!")
    
    # Admin Endpoints Explorer
    st.markdown("---")
    st.subheader("Admin Endpoints Explorer")
    
    if st.button("List All Endpoints", type="secondary"):
        with st.spinner("Fetching endpoints..."):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/endpoints", use_admin_key=True)
            
            if response and response.status_code == 200:
                endpoints = response.json()
                
                # Public endpoints
                st.markdown("### Public Endpoints")
                public_df = pd.DataFrame([
                    {"Method": "GET", "Endpoint": endpoint, "Description": desc}
                    for endpoint, desc in endpoints.get('public_endpoints', {}).items()
                ])
                st.dataframe(public_df, use_container_width=True)
                
                # Admin endpoints
                st.markdown("### Admin Endpoints (Require X-Admin-Key)")
                admin_df = pd.DataFrame([
                    {"Method": endpoint.split()[0], "Endpoint": endpoint.split()[1], "Description": desc}
                    for endpoint, desc in endpoints.get('admin_endpoints', {}).items()
                ])
                st.dataframe(admin_df, use_container_width=True)
            else:
                st.error("Failed to fetch endpoints")
    
    # Admin Tools Section
    st.markdown("---")
    st.subheader("Admin Tools")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("System Stats"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/system-stats", use_admin_key=True)
            if response and response.status_code == 200:
                data = response.json()
                st.json(data)
    
    with col2:
        if st.button("Song Analytics"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/song-analytics", use_admin_key=True)
            if response and response.status_code == 200:
                data = response.json()
                st.json(data)
    
    with col3:
        if st.button("All Songs"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/all-songs", use_admin_key=True)
            if response and response.status_code == 200:
                data = response.json()
                st.info(f"Total songs: {data.get('count', 0)}")
                if data.get('songs'):
                    st.dataframe(pd.DataFrame(data['songs']).head(20))
    
    # Year Analysis Section
    st.markdown("---")
    st.subheader("Year Analysis")
    
    # Get available years
    if st.button("Load Available Years"):
        with st.spinner("Loading years..."):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/years", use_admin_key=True)
            
            if response and response.status_code == 200:
                data = response.json()
                years = data.get('available_years', [])
                
                if years:
                    selected_year = st.selectbox("Select Year for Analysis", years)
                    
                    if st.button(f"Analyze {selected_year}"):
                        with st.spinner(f"Loading songs for {selected_year}..."):
                            if load_songs(view='year', year=selected_year):
                                songs_df = pd.DataFrame(st.session_state.songs)
                                
                                st.success(f"Loaded {len(songs_df)} songs from {selected_year}")
                                
                                # Display metrics
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Total Songs", len(songs_df))
                                with col2:
                                    if len(songs_df) > 0:
                                        avg_pop = songs_df['year_popularity'].mean()
                                        st.metric("Avg Popularity", f"{avg_pop:.0f}")
                                with col3:
                                    if len(songs_df) > 0:
                                        top_song = songs_df.iloc[0]
                                        st.metric("Top Song", top_song['title'][:15])
                                
                                # Display top 5 songs
                                st.subheader(f"Top 5 Songs of {selected_year}")
                                for idx, song in enumerate(st.session_state.songs[:5], 1):
                                    st.write(f"{idx}. **{song['title']}** - {song['artist']} (Popularity: {song['year_popularity']:.0f})")
                else:
                    st.warning("No year data available")
            else:
                st.error("Failed to load year data")
    
    # Century Comparison
    st.markdown("---")
    st.subheader("Century Comparison")
    
    if st.button("Compare Centuries"):
        with st.spinner("Loading century comparison..."):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/centuries/comparison", use_admin_key=True)
            
            if response and response.status_code == 200:
                data = response.json()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("1900s Songs", data['century_1900']['song_count'])
                with col2:
                    st.metric("2000s Songs", data['century_2000']['song_count'])
                
                # Comparison chart
                fig = go.Figure(data=[
                    go.Bar(name='1900s', x=['Popularity'], y=[data['century_1900']['avg_popularity']]),
                    go.Bar(name='2000s', x=['Popularity'], y=[data['century_2000']['avg_popularity']])
                ])
                fig.update_layout(title='Average Popularity by Century', barmode='group')
                st.plotly_chart(fig, use_container_width=True)

# ADMIN VIEW: Admin Tools
elif selected_page == "Admin Tools" and st.session_state.role == 'admin':
    st.title("Admin Tools")
    st.markdown("Advanced administrative functions")
    
    # Debug Tools
    st.subheader("Debug Tools")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Debug Data"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/debug/data", use_admin_key=True)
            if response and response.status_code == 200:
                st.json(response.json())
    
    with col2:
        if st.button("MongoDB Structure"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/debug/mongodb-structure", use_admin_key=True)
            if response and response.status_code == 200:
                st.json(response.json())
    
    # System Management
    st.subheader("System Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Reload Songs", type="primary"):
            response = make_request(f"{MUSIC_SERVICE_URL}/admin/reload-songs", method='POST', use_admin_key=True)
            if response and response.status_code == 200:
                data = response.json()
                st.success(f"{data.get('message', 'Songs reloaded')}")
                st.info(f"Total songs: {data.get('total_songs', 0)}")
    
    with col2:
        if st.button("Test All Services"):
            status = check_services()
            st.success(f"Music: {'✅' if status['music'] else '❌'}")
            st.success(f"Stats: {'✅' if status['stats'] else '❌'}")
            st.success(f"Auth: {'✅' if status['auth'] else '❌'}")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Music Museum Dashboard**
    
    Features:
    - Century Views (1900s/2000s)
    - Admin Dashboard with API Key
    - Admin Tools
    
    Admin API Key: Required for admin endpoints
    """
)