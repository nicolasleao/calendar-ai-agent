# AI Agent capable of interacting with Google Calendar to help you manage it

## Features
By default the agent has context about your calendar, but it can also perform actions to update the calendar, for example: searching for events, creating new ones, updating or deleting them.

## How to use
1. Create a virtual environment using `python -m venv venv`
2. Activate the virtual environment using `source venv/bin/activate`
3. Install the agent using `pip install -r requirements.txt`
4. Copy the .env.example to .env and add your openai api key
5. Download your google oauth credentials and save them as credentials.json
6. Run the agent using `python main.py`