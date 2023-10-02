### Running the bot

You need Python 3.6+ installed on your machine. 

To run the bot:

```bash
# 1. install the required packages from pip
pip install -r requirements.txt

# 2. create a copy of the config file and rename it to 'config.toml'
cp config.example.toml config.toml

# 3. open 'config.toml' and change the config values as described by the comments

# 4. run the script
python main.py
```

After every git pull/merge, it is highly suggested to upgrdae the database structure:

```bash
alembic upgrade head
```