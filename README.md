# Music Museum - Nihal Majjiga

This is a cloud based application that is able to show a history of top 100 songs from 1958 to 2025 based on accessibility to the billboard chart data This will utilize the techniques from class such as rest APIs, individual microservices and also docker to deploy this on my preferred cloud base digitalocean. The data is loaded in from a raw file called all.json from the github repository which is continuously being updated every single day which makes updating the application easier. The goal of my microservice is to analyze 65+ years of Billboard chart data (1958–2025) to identify the top 100 most popular songs. I chose this project because of the convenience of utilizing key microservices patterns to be able to create services for the songs, and stats of each song using a concurrently updating JSON file.

### Installation - Docker
Since this is all containerized with docker, it is much more convenient to utilize it so all the services can run. You can install docker desktop (for windows) or basic docker (using linux) provided the steps using the link here: https://docs.docker.com/engine/install/ 

STEPS:
- With docker installed and docker desktop open, create the following docker-compose.yml file here:
  
docker-compose.prod.yml:
  version: '3.8'
  
  services:
    auth-service:
      image: nmajjiga/music-museum:auth
      container_name: music-museum-auth
      ports:
        - "5002:5002"
      environment:
        JWT_SECRET_KEY: "music-museum-secure-key-2025-change-in-production"
        FLASK_ENV: "production"
      restart: unless-stopped
      networks:
        - music-network
  
    music-service:
      image: nmajjiga/music-museum:music
      container_name: music-museum-music
      ports:
        - "5000:5000"
      environment:
        STATS_SERVICE_URL: http://stats-service:5001
        AUTH_SERVICE_URL: http://auth-service:5002
        JWT_SECRET_KEY: "music-museum-secure-key-2025-change-in-production"
        FLASK_ENV: "production"
      depends_on:
        - stats-service
        - auth-service
      restart: unless-stopped
      networks:
        - music-network
  
    stats-service:
      image: nmajjiga/music-museum:stats
      container_name: music-museum-stats
      ports:
        - "5001:5001"
      environment:
        AUTH_SERVICE_URL: http://auth-service:5002
        JWT_SECRET_KEY: "music-museum-secure-key-2025-change-in-production"
        FLASK_ENV: "production"
      depends_on:
        - auth-service
      restart: unless-stopped
      networks:
        - music-network
  
    dashboard:
      image: nmajjiga/music-museum:dashboard
      container_name: music-museum-dashboard
      ports:
        - "8501:8501"
      environment:
        MUSIC_SERVICE_URL: http://music-service:5000
        STATS_SERVICE_URL: http://stats-service:5001
        AUTH_SERVICE_URL: http://auth-service:5002
        JWT_SECRET_KEY: "music-museum-secure-key-2025-change-in-production"
      depends_on:
        - music-service
        - stats-service
        - auth-service
      restart: unless-stopped
      networks:
        - music-network
  
  networks:
    music-network:
      driver: bridge

- After this is created, you can just type the command 'docker-compose up -d' so that it can be running in the background of the program provided and open it using 'localhost:8501'

### Features
- User/Admin login when admin can view system health and additional stats on who logs into the user base
- Loads top 100 songs and displays the top 5 to save space and display
- Shows the songs as well for the 1900s and 2000s to view history of popular songs that have evolved
- Search for songs if need be to all the songs

### API
- All the endpoints are JSON outputted, so if a user were to scrape off the website, they would just need to call the API for the application and the specific endpoint through utilizing requests in python and they will have the information scraped
