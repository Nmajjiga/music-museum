import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# Configuration
MUSIC_SERVICE_URL = os.getenv('MUSIC_SERVICE_URL', 'http://localhost:5000')
STATS_SERVICE_URL = os.getenv('STATS_SERVICE_URL', 'http://localhost:5001')
API_KEY = os.getenv('API_KEY', 'your-api-key-here')

st.set_page_config(
    page_title="Music Museum Dashboard",
    page_icon="🎵",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1DB954;
        text-align: center;
        margin-bottom: 2rem;
    }
    .song-card {
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #ddd;
        margin-bottom: 1rem;
        background-color: #f9f9f9;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">🎵 Music Museum Dashboard</h1>', unsafe_allow_html=True)

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Top 100 Songs", "Statistics", "Search Songs"])

# Helper function to make API calls
def make_api_request(endpoint, params=None):
    headers = {'X-API-Key': API_KEY}
    try:
        response = requests.get(f"{MUSIC_SERVICE_URL}/{endpoint}", 
                              headers=headers, params=params)
        return response.json() if response.status_code == 200 else None
    except:
        return None

# Pages
if page == "Top 100 Songs":
    st.header("Top 100 Most Popular Songs")
    
    if st.button("Refresh Data"):
        st.cache_data.clear()
    
    @st.cache_data(ttl=300)
    def load_top_songs():
        return make_api_request("songs/top100")
    
    data = load_top_songs()
    
    if data and 'songs' in data:
        songs_df = pd.DataFrame(data['songs'])
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Songs", len(songs_df))
        with col2:
            avg_popularity = songs_df['popularity'].mean() if 'popularity' in songs_df.columns else 0
            st.metric("Average Popularity", f"{avg_popularity:.1f}")
        with col3:
            st.metric("Earliest Year", songs_df['year'].min() if 'year' in songs_df.columns else "N/A")
        
        # Display songs in a nice format
        for idx, song in enumerate(data['songs'][:20], 1):
            with st.container():
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.markdown(f"**#{idx}**")
                with col2:
                    st.markdown(f"**{song.get('title', 'Unknown')}**")
                    st.markdown(f"*{song.get('artist', 'Unknown')}* • {song.get('year', 'Unknown')}")
                    if 'popularity' in song:
                        st.progress(song['popularity'] / 100)
        # Show full list as dataframe
        with st.expander("View All 100 Songs"):
            st.dataframe(songs_df[['title', 'artist', 'year', 'popularity']])
    else:
        st.error("Unable to load song data")

elif page == "Statistics":
    st.header("Usage Statistics")
    
    # Fetch statistics from stats service
    try:
        response = requests.get(f"{STATS_SERVICE_URL}/admin/statistics",
                              headers={'X-Admin-API-Key': 'your-admin-key'})
        if response.status_code == 200:
            stats_data = response.json()
            
            # Create visualizations
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("API Request Distribution")
                endpoint_data = {
                    'Endpoint': list(stats_data['endpoint_usage'].keys()),
                    'Requests': [v['total'] for v in stats_data['endpoint_usage'].values()]
                }
                if endpoint_data['Endpoint']:
                    df = pd.DataFrame(endpoint_data)
                    fig = px.bar(df, x='Endpoint', y='Requests')
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Service Usage")
                service_data = {
                    'Service': list(stats_data['service_usage'].keys()),
                    'Requests': list(stats_data['service_usage'].values())
                }
                if service_data['Service']:
                    df = pd.DataFrame(service_data)
                    fig = px.pie(df, values='Requests', names='Service')
                    st.plotly_chart(fig, use_container_width=True)
            
            # Show raw statistics
            with st.expander("View Raw Statistics"):
                st.json(stats_data)
        else:
            st.error("Unable to fetch statistics")
    except:
        st.error("Statistics service unavailable")

elif page == "Search Songs":
    st.header("Search Songs")
    
    search_query = st.text_input("Search by title, artist, or year:")
    
    if search_query:
        # In a real implementation, you would have a search endpoint
        # For now, we'll filter from the top 100
        data = make_api_request("songs/top100")
        if data and 'songs' in data:
            filtered_songs = [
                song for song in data['songs']
                if search_query.lower() in str(song.get('title', '')).lower() or
                   search_query.lower() in str(song.get('artist', '')).lower() or
                   search_query.lower() in str(song.get('year', '')).lower()
            ]
            
            if filtered_songs:
                st.write(f"Found {len(filtered_songs)} songs:")
                for song in filtered_songs[:10]:
                    st.markdown(f"**{song.get('title', 'Unknown')}** - *{song.get('artist', 'Unknown')}* ({song.get('year', 'Unknown')})")
            else:
                st.info("No songs found matching your search.")