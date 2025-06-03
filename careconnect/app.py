import logging
import os
import streamlit as st
from model_serving_utils import query_endpoint
from core.agents.medical_agent import run_medicine_recommendation
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure environment variable is set correctly
# assert os.getenv('SERVING_ENDPOINT'), "SERVING_ENDPOINT must be set in app.yaml."

def get_user_info():
    headers = st.context.headers
    return dict(
        user_name=headers.get("X-Forwarded-Preferred-Username"),
        user_email=headers.get("X-Forwarded-Email"),
        user_id=headers.get("X-Forwarded-User"),
    )

user_info = get_user_info()

# Streamlit app
if "visibility" not in st.session_state:
    st.session_state.visibility = "visible"
    st.session_state.disabled = False

st.title("🧱 Careconnect App")
st.markdown(
    "ℹ️ CareConnect is a one-stop solution for any and every need in healthcare."
)

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("What is up?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        # Query the Databricks serving endpoint
        # assistant_response = query_endpoint(
        #     endpoint_name=os.getenv("SERVING_ENDPOINT"),
        #     messages=st.session_state.messages,
        #     max_tokens=400,
        # )["content"]
        assistant_response = run_medicine_recommendation(
            user_query=st.session_state.messages,
        )
        st.markdown(assistant_response)


    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": assistant_response})
