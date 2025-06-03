import sys
import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect/')
from core.connectors.vector_connector_medical_agent import call_vector_db
from dotenv import load_dotenv
from core.connectors.llm_connector import chat_completion_sync
load_dotenv()

class AgentState(TypedDict):
    user_query: Optional[str]
    medicine_suggestions: Optional[str]
    error_message: Optional[str]
    final_answer: Optional[str]

def medicine_recommendation_node(state: AgentState) -> AgentState:
    print("---EXECUTING MEDICINE RECOMMENDATION NODE---")
    if state.get("error_message"):
        return {"error_message": state["error_message"]}
    
    user_query = state.get("user_query", "")
    if not user_query:
        return {"error_message": "No user query provided for medicine recommendation."}

    try:
        # Fetch medicine suggestions from the vector database
        api_key = os.getenv("DATABRICKS_TOKEN")
        if not api_key:
            return {"error_message": "Databricks token not found in environment variables."}
        
        medicine_suggestions = call_vector_db(api_key, user_query, top_n=5)
        if not medicine_suggestions:
            return {"error_message": "No relevant medicines found in the database."}
        
        return {"medicine_suggestions": medicine_suggestions, "error_message": None}
    except Exception as e:
        return {"error_message": f"Error fetching medicine recommendations: {str(e)}"}

def final_response_node(state: AgentState) -> AgentState:
    print("---EXECUTING FINAL RESPONSE NODE---")
    if state.get("error_message"):
        return {"final_answer": f"Could not complete recommendation. Error: {state['error_message']}"}
    
    suggestions = state.get("medicine_suggestions")
    if not suggestions:
        return {"final_answer": "No medicine recommendations were generated. There might have been an issue in a previous step."}
    
    # use llm for formatting the suggestions
    try:
        formatted_suggestions = chat_completion_sync(
            prompt="Please format the following medicine suggestions for a user: " + str(suggestions),
            model="databricks-llama-4-maverick",
            temperature=0.7,
            system_prompt="You are a helpful assistant that formats medical recommendations.",
        )
    except Exception as e:
        return {"error_message": f"Error formatting suggestions: {str(e)}"}

    return {"final_answer": formatted_suggestions}

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("query_processor", medicine_recommendation_node)
workflow.add_node("responder", final_response_node)

# Set entry and edges
workflow.set_entry_point("query_processor")
workflow.add_edge("query_processor", "responder")
# workflow.add_edge("responder", END)

app = workflow.compile()

def medical_recommendation_agent(user_query: str):
    inputs = {"user_query": user_query}
    print("\n---STARTING MEDICINE RECOMMENDATION WORKFLOW---")
    print(f"User Query: {user_query}")
    final_state = None
    for event in app.stream(inputs, {"recursion_limit": 10}):
        for key, value in event.items():
            print(f"---EVENT FROM NODE: {key}---")
            if value is None:
                print(f"WARNING: Node '{key}' returned None.")
                continue
            if 'error_message' in value and value['error_message']:
                print(f"ERROR: {value['error_message']}")
            if 'final_answer' in value:
                final_state = value
    
    if final_state and final_state.get("final_answer"):
        return final_state["final_answer"]
    elif final_state and final_state.get("error_message"):
        return f"Recommendation failed. Error: {final_state.get('error_message')}"
    return "No response generated, and no specific error reported in final state."

if __name__ == "__main__":
    # %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph python-dotenv
    # %pip install --upgrade --force-reinstall -q databricks-vectorsearch
    # dbutils.library.restartPython()
    print("\n--- Medicine Recommendation ---")
    user_query = "What medicine can I take for a headache?"
    medicine_suggestions = medical_recommendation_agent(user_query)
    print("\nFINAL MEDICINE SUGGESTIONS:\n", medicine_suggestions)
