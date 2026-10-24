
import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def ask_gemini(prompt: str) -> str:
    """Send a prompt to Gemini and return its response."""
    if not API_KEY or API_KEY == "your_api_key_here":
        return (
            "API key not configured. Add a valid GEMINI_API_KEY "
            "to your local .env file."
        )

    try:
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text or "The model returned an empty response."
    except errors.APIError as exc:
        return f"Gemini API error: {exc}"
    except Exception as exc:
        return f"Unexpected error: {exc}"


def show_menu():
    print("\n===== SQLBuddy: AI SQL Assistant =====")
    print("1. Convert English to SQL")
    print("2. Explain an SQL query")
    print("3. Help with an SQL error")
    print("4. Exit")


def main():
    print("Welcome to SQLBuddy!")

    while True:
        show_menu()
        choice = input("Choose an option (1-4): ").strip()

        if choice == "1":
            question = input("Describe what you want to query: ").strip()
            schema = input(
                "Optional table/schema details (press Enter to skip): "
            ).strip()

            prompt = f"""
You are SQLBuddy, a careful SQL assistant.
Convert the user's request into a SQL query.
Use the supplied schema when available.
If important details are missing, state your assumptions.
Default to a read-only SELECT query.
Do not claim that the query has been executed.
Return the SQL and a brief explanation.

Schema:
{schema or "No schema supplied"}

User request:
{question}
"""
            print("\n" + ask_gemini(prompt))

        elif choice == "2":
            query = input("Enter your SQL query: ").strip()
            prompt = f"""
Explain this SQL query in beginner-friendly language.
Describe what it does and point out anything unclear.
Do not execute the query.

SQL query:
{query}
"""
            print("\n" + ask_gemini(prompt))

        elif choice == "3":
            query = input("Enter the SQL query (if available): ").strip()
            error_message = input("Paste the SQL error message: ").strip()

            prompt = f"""
Help a beginner understand this SQL error.
Explain likely causes and suggest a corrected query if possible.
If information is missing, say what needs checking.
Do not claim the suggested query was tested or executed.

SQL query:
{query or "Not supplied"}

Error:
{error_message}
"""
            print("\n" + ask_gemini(prompt))

        elif choice == "4":
            print("Thanks for using SQLBuddy. Goodbye!")
            break

        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()
