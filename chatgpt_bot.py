from openai import OpenAI
import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv(), override=True)
api_key = os.getenv("OPENAI_API_KEY")

# Check if API key exists
if not api_key:
    raise ValueError("No OpenAI API key found. Make sure OPENAI_API_KEY is set in your .env file")

client = OpenAI(api_key=api_key)

def get_chatgpt_response(user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful Discord voice-chat assistant."},
                {"role": "user", "content": user_input},
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"

if __name__ == "__main__":
    test_prompt = "What's a good recipe for pancakes?"
    response = get_chatgpt_response(test_prompt)
    print("ChatGPT response:", response)