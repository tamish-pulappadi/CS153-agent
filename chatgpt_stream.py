from openai import OpenAI
import os
from dotenv import load_dotenv, find_dotenv

# Clear any existing cached values and force reload
os.environ.pop("OPENAI_API_KEY", None)
load_dotenv(find_dotenv(), override=True)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("No OpenAI API key found. Make sure OPENAI_API_KEY is set in your .env file")

client = OpenAI(api_key=api_key)

def chatgpt_stream_response(user_input):
    try:
        stream = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input},
            ],
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                print(chunk.choices[0].delta.content, end="")
    except Exception as e:
        print(f"\nError occurred: {str(e)}")

if __name__ == "__main__":
    test_prompt = "What's a good recipe for pancakes?"
    chatgpt_stream_response(test_prompt)
