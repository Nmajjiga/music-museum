# test_mongodb_updated.py
from pymongo import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://videoAppUser:uNnlvDPlnz2MbrmU@cluster0.ol102vh.mongodb.net/?appName=Cluster0"

client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

# Test the BillboardSongs database
db = client['BillboardSongs']
collection = db['Songs']

# Count documents (weekly charts)
count = collection.count_documents({})
print(f"📊 Total weekly charts in collection: {count}")

# Get one sample weekly chart
sample_week = collection.find_one()
if sample_week:
    print(f"\n📋 Sample weekly chart keys: {list(sample_week.keys())}")
    print(f"📅 Week date: {sample_week.get('date')}")
    
    # Check the data array
    data = sample_week.get('data', [])
    print(f"Number of songs in this week: {len(data)}")
    
    if data:
        # Show first 5 songs of this week
        print("\n📜 First 5 songs of this week:")
        for i, song in enumerate(data[:5]):
            title = song.get('song', 'Unknown')
            artist = song.get('artist', 'Unknown')
            peak = song.get('peak_position', 'N/A')
            weeks = song.get('weeks_on_chart', 'N/A')
            print(f"{i+1}. {title} - {artist} (Peak: #{peak}, Weeks: {weeks})")
        
        # Show some statistics
        print(f"\n📈 Sample week statistics:")
        print(f"  - Date: {sample_week.get('date')}")
        print(f"  - Total songs in chart: {len(data)}")
        print(f"  - First song: {data[0].get('song')} by {data[0].get('artist')}")
        print(f"  - Last song: {data[-1].get('song') if len(data) > 1 else 'N/A'}")
    else:
        print("No songs in this week's data array.")
else:
    print("❌ No documents found in the collection!")

# Let's also check the date range
print(f"\n📅 Checking date range of charts...")
first_chart = collection.find_one(sort=[("date", 1)])  # Earliest
last_chart = collection.find_one(sort=[("date", -1)])  # Latest

if first_chart and last_chart:
    print(f"  - Earliest chart: {first_chart.get('date')}")
    print(f"  - Latest chart: {last_chart.get('date')}")
    print(f"  - Total weeks: {count}")