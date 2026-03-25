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
        except Exception as e:
            print(e)
    
    def insert(self, record, type): # type=1 for menu_items, type=2 for restaurant_info
        filter_query = {"restaurant": record["restaurant"]}
        if type == 1:
            items_collection = self.db['menu_items']
            filter_query = {"restaurant": record["restaurant"],
                            "category": record["category"]
                            }
        else:
            items_collection = self.db['rest_info']
        items_collection.update_one(
                filter_query,
                { "$set": record},
                upsert=True
            )