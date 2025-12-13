# Music Museum - Nihal Majjiga

This is a cloud based application that is able to show a history of top 100 songs from 1958 to 2025 based on accessibility to the billboard chart data This will utilize the techniques from class such as rest APIs, individual microservices and also docker to deploy this on my preferred cloud base digitalocean. The data is loaded in from a raw file called all.json from the github repository which is continuously being updated every single day which makes updating the application easier. The goal of my microservice is to analyze 65+ years of Billboard chart data (1958–2025) to identify the top 100 most popular songs. I chose this project because of the convenience of utilizing key microservices patterns to be able to create services for the songs, and stats of each song using a concurrently updating JSON file.

### Installation - Docker
Since this is all containerized with docker, it is much more convenient to utilize it so all the services can run. You can install docker desktop (for windows) or basic docker (using linux) provided the steps using the link here: https://docs.docker.com/engine/install/ 

STEPS:
- First clone this repository by doing 'git clone [link here]'
- Then go into the root of music museum by doing 'cd music-museum'
- With docker installed and docker desktop open, you can just type the command 'docker-compose up -d' so that it can be running in the background of the program provided

### Features
- User/Admin login when admin can view system health and additional stats on who logs into the user base
- Loads top 100 songs and displays the top 5 to save space and display
- Shows the songs as well for the 1900s and 2000s to view history of popular songs that have evolved
- Search for songs if need be to all the songs

### API
- All the endpoints are JSON outputted, so if a user were to scrape off the website, they would just need to call the API for the application and the specific endpoint through utilizing requests in python and they will have the information scraped
