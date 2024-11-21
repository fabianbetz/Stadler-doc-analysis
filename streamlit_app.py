import streamlit as st
from openai import OpenAI
import traceback
import time

# Zugriff auf den API-Schlüssel aus Streamlit-Secrets
api_key = st.secrets["OPENAI_API_KEY"]

# OpenAI initialisieren
client = OpenAI(api_key=api_key)

# Feste Assistant-ID und Nachricht
ASSISTANT_ID = "asst_vvaFZVcZ4wbm3yetLeB3CTgj"
DEFAULT_MESSAGE = "Analyze the PDF following your instructions. Analyze the whole document. Execute your whole task."

# Funktionen
def upload_file(file_path):
    try:
        with open(file_path, 'rb') as file:
            file_response = client.files.create(file=file, purpose='assistants')
        return file_response.id
    except Exception as e:
        st.error(f"Error uploading file: {e}")
        traceback.print_exc()
        return None

def delete_file(file_id):
    try:
        client.files.delete(file_id=file_id)
    except Exception as e:
        st.error(f"Error deleting file: {e}")
        traceback.print_exc()

def verify_file_access(file_id):
    try:
        client.files.retrieve(file_id=file_id)
        return True
    except Exception as e:
        st.error(f"File verification failed: {e}")
        return False

def send_message(thread_id, user_message, file_id=None):
    try:
        attachments = [{"file_id": str(file_id), "tools": [{"type": "file_search"}]}] if file_id else []
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
            attachments=attachments
        )
        return message
    except Exception as e:
        st.error(f"Error sending message: {e}")
        traceback.print_exc()
        return None

def run_assistant_and_get_response(assistant_id, user_message, file_id):
    try:
        thread = client.beta.threads.create()
        send_message(thread.id, user_message, file_id)
        run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant_id)

        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status == "completed":
                break
            elif run.status in ["failed", "cancelled"]:
                st.error(f"Run {run.status}. Details: {run}")
                return []
            time.sleep(5)

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        answers = [msg.content for msg in messages.data if msg.role == "assistant"]

        # Extrahiere nur den reinen Text
        plain_texts = []
        for answer in answers:
            if isinstance(answer, str):
                plain_texts.append(answer)
            elif isinstance(answer, list):
                for item in answer:
                    if isinstance(item, str):
                        plain_texts.append(item)
                    elif hasattr(item, "text") and hasattr(item.text, "value"):
                        plain_texts.append(item.text.value)

        return plain_texts
    except Exception as e:
        st.error(f"Error during assistant run: {e}")
        traceback.print_exc()
        return []

# Funktion zur Wiederholung des Tasks bei Fehlern
def process_file_with_retries(file_name, max_retries=3):
    retry_count = 0
    while retry_count < max_retries:
        st.info(f"Processing {file_name}, attempt {retry_count + 1}...")
        file_id = upload_file(file_name)
        if file_id and verify_file_access(file_id):
            answers = run_assistant_and_get_response(ASSISTANT_ID, DEFAULT_MESSAGE, file_id)
            delete_file(file_id)

            # Prüfen, ob vernünftige Ergebnisse vorliegen
            if is_valid_summary(answers):
                return answers
            else:
                st.warning(f"Analysis for {file_name} returned insufficient results. Retrying...")
        else:
            st.error(f"File upload or verification failed for {file_name}. Retrying...")
        retry_count += 1

    st.error(f"Failed to process {file_name} after {max_retries} attempts.")
    return []

# Funktion zur Validierung der Zusammenfassung
def is_valid_summary(answers):
    if not answers:
        return False
    invalid_phrases = [
        "unable to access the contents of the PDF",
        "re-upload the file",
        "did not yield any results",
        "manually analyze the document",
        "does not contain any text that can be searched",
        "any searchable text",
        "try uploading it again",
        "issue retrieving the content",
        "unable to access the content of the PDF",
        "unable to access the content",
        "issue retrieving content",
    ]
    for answer in answers:
        for phrase in invalid_phrases:
            if phrase in answer.lower():
                return False
    return any(len(answer.strip()) > 10 for answer in answers)  # Mindesttextlänge prüfen

# Streamlit App
st.title("Intelligente Vertragsanalyse")

# Beschreibung des Tools
st.markdown(
    """
    **Dieser Chatbot analysiert Vertragsdokumente und erstellt eine strukturierte Zusammenfassung basierend auf definierten Kriterien.**
    \nLaden Sie einfach Ihre Dateien hoch, und das Tool übernimmt den Rest!
    """
)

uploaded_files = st.file_uploader("Upload multiple PDF files", type="pdf", accept_multiple_files=True)

if st.button("Run Analysis"):
    if uploaded_files:
        all_answers = {}
        for uploaded_file in uploaded_files:
            progress_placeholder = st.empty()  # Platzhalter für den Fortschritt
            with progress_placeholder:
                with st.spinner(f"Processing {uploaded_file.name}..."):
                    with open(uploaded_file.name, "wb") as f:
                        f.write(uploaded_file.read())
                    answers = process_file_with_retries(uploaded_file.name)

            if answers:
                st.success(f"✔️ {uploaded_file.name} successfully processed!")
                all_answers[uploaded_file.name] = answers
            else:
                st.error(f"❌ {uploaded_file.name} could not be processed.")

        st.success("All analyses complete!")
        st.write("### Answers (Clean Text):")
        for file_name, answers in all_answers.items():
            st.write(f"#### {file_name}")
            for answer in answers:
                st.write(answer)
    else:
        st.error("Please upload at least one PDF file.")
