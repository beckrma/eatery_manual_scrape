import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

class EateryDB:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.db = None
        self.collection = None
    
    def connect(self):
        load_dotenv()
        uri = os.getenv('DATABASE_URI')
        # Create a new client and connect to the server
        client = MongoClient(uri, server_api=ServerApi('1'))
        # Send a ping to confirm a successful connection
        try:
            client.admin.command('ping')
            self.db = client['scraped_restaurants']
            self.collection = self.db['menu_items']
        except Exception as e:
            print(e)
    
    def insert(self, record):
        filter_query = {"_id": record["_id"]
                            }
        self.collection.update_one(
                filter_query,
                { "$set": record},
                upsert=True
            )
        
    def get_restaurant(self, key):
        doc = self.collection.find_one(key)
        return doc