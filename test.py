from sqlalchemy import create_engine

# Define the connection details
user = 'root'
password = 'password'
host = '127.0.0.1'
port = 5432
database = 'postgres'

# Create the engine
engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database}')

# Test the connection
try:
connection = engine.connect()
print(f"Connection to the {host} for user {user} created successfully.")
connection.close()
except Exception as ex:
print(f"Connection could not be made due to the following error: \n{ex}")