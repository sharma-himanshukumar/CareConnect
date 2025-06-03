%pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph python-dotenv pymupdf python-docx
%pip install --upgrade --force-reinstall -q databricks-vectorsearch
%pip install --upgrade -q typing_extensions
dbutils.library.restartPython()

import os
from langgraph.graph import StateGraph, END
import sys
import json
from typing import TypedDict, List, Annotated, Union, Dict, Optional, Any, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.utils.function_calling import convert_to_openai_function
sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect')
from core.agents.hospital_service_agent import hospital_agent
from core.agents.lab_report_analysis_agent import lab_report_summarizer_agent
from core.agents.medicine_agent import medical_recommendation_agent
from core.agents.pathology_agent import pathology_agent

class AgentState(TypedDict):
    query: str
    document_path: Optional[str] 
    response: Optional[str]
    next_node: Optional[str]     


try:
    DATABRICKS_TOKEN = os.getenv('DATABRICKS_TOKEN')
    if not DATABRICKS_TOKEN:
        raise ValueError("DATABRICKS_TOKEN is not set.")
except Exception as e:
    print(f"Error getting DATABRICKS_TOKEN: {e}. Please ensure it's correctly configured.")
    DATABRICKS_TOKEN = "dummy_token_if_testing_non_llm_parts"

DATABRICKS_SERVING_BASE_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT = "databricks-claude-3-7-sonnet"

try:
    llm = ChatOpenAI(
        model_name=YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT,
        openai_api_base=DATABRICKS_SERVING_BASE_URL, 
        openai_api_key=DATABRICKS_TOKEN,
        temperature=0.1, 
    )
    print(f"LangChain LLM (ChatOpenAI) configured for Databricks Model Serving endpoint: '{YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT}' at '{DATABRICKS_SERVING_BASE_URL}'")

except Exception as e:
    print(f"Error initializing ChatOpenAI for Databricks Model Serving. Ensure endpoint name and token are correct. Error: {e}")
    llm = None


def hospital_searcher_node(state: AgentState):
    print("---CALLING HOSPITAL SEARCHER---")
    result = hospital_agent(state["query"])
    return {"response": result}

def pathology_search_node(state: AgentState):
    print("---CALLING PATHOLOGY SEARCHER---")
    result = pathology_agent(state["query"])
    return {"response": result}

def medicine_explainer_node(state: AgentState):
    print("---CALLING MEDICINE EXPLAINER---")
    result = medical_recommendation_agent(state["query"])
    return {"response": result}

def lab_report_summarizer_node(state: AgentState):
    print("---CALLING LAB REPORT SUMMARIZER---")
    if not state.get("document_path"):
        return {"response": "Error: Document path not provided for lab report summarizer."}
    result = lab_report_summarizer_agent(state.get("query"), state["document_path"])
    return {"response": result}

def fallback_node(state: AgentState):
    print("---CALLING LLM FALLBACK---")
    if not llm:
        return {"response": "I am unable to process this request at the moment as my advanced reasoning capabilities are offline. Please try a more specific query related to hospitals, pathology, medicine, or lab reports."}
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant. Try to answer the user's query based on your general knowledge. If you don't know the answer, say so politely."),
            ("user", "{query}")
        ])
        chain = prompt | llm
        result = chain.invoke({"query": state["query"]})
        response_content = result.content if hasattr(result, 'content') else str(result)
        return {"response": response_content}
    except Exception as e:
        print(f"Error in LLM fallback: {e}")
        return {"response": "Sorry, I encountered an issue trying to answer your query with general knowledge."}



def format_response_node(state: AgentState):
    print("---FORMATTING RESPONSE WITH LLM---")
    if not llm:
        print("LLM not available for formatting, passing through raw response.")
        return {"response": state.get("response", "No information was found and formatter is unavailable.")}

    original_query = state["query"]
    agent_or_fallback_response = state.get("response", "No information was provided by the previous step.")

    prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert at crafting clear, concise, and user-friendly responses. "
        "The user's original query was: '{original_query}'.\n"
        "An internal system or knowledge source provided the following information/raw_output (which might be a string, a JSON string representing a list of items, or other data): '{agent_response}'.\n\n"
        "Your task is to synthesize this information into a final, polished, and helpful answer for the user. "
        "Follow these guidelines:\n"
        "1.  **Analyze Input Type**: First, determine if the `agent_response` is a simple text, an error message, or structured data (like a list of lab results).\n"
        "2.  **For Structured Data (e.g., list of labs/hospitals)**:\n"
        "    *   If it's a list, present each item clearly. You can use bullet points or a numbered list for distinct items.\n"
        "    *   For each item, extract and display the most important details: Name, Type (e.g., 'Collection center', 'Lab'), Full Address, Area, Phone, and Timings.\n"
        "    *   If a 'Location' URL is present, you can mention that a map link is available or simply rely on the full Address.\n"
        "    *   If a 'Rating' field has unusual characters (e.g., '�'), is 'N/A', or is missing, state 'Rating: Not available' or omit it.\n"
        "    *   Handle duplicate entries: If multiple entries are identical, list the distinct information once.\n"
        "    *   If there are many results (e.g., more than 5-7), you could list the first few and mention how many more are available, or provide a brief summary if appropriate.\n"
        "3.  **For Simple Text/Direct Answers**:\n"
        "    *   Present the information clearly. Add a polite opening/closing if it enhances the response.\n"
        "4.  **For Error Messages or 'Not Found'**:\n"
        "    *   If the `agent_response` indicates information couldn't be found or an error occurred, acknowledge this politely. E.g., 'I couldn't find specific details for your query about \"{original_query}\".' or 'It seems there was an issue processing your request for \"{original_query}\".'\n"
        "5.  **General Guidelines**:\n"
        "    *   Do NOT invent information not present in the `agent_response`.\n"
        "    *   Maintain a helpful, empathetic, and professional tone.\n"
        "    *   If the `agent_response` is already a good user-facing response (e.g., from an LLM fallback), refine it slightly for consistency if needed, or use it directly if it's perfect.\n"
        "    *   Start with a clear statement acknowledging the query, e.g., 'Okay, I looked for information about {original_query}. Here's what I found:' or similar.\n\n"
        "Please provide the final, well-formatted response for the user."
        ),
        ("user",
         "Original Query: '{original_query}'\n"
         "Information/Raw Output from System: '{agent_response}'\n\n"
         "Please provide the final, well-formatted and descriptive response for the user:")
    ])

    formatting_chain = prompt_template | llm

    try:
        formatted_result = formatting_chain.invoke({
            "original_query": original_query,
            "agent_response": agent_or_fallback_response
        })
        final_response_content = formatted_result.content if hasattr(formatted_result, 'content') else str(formatted_result)
        return {"response": final_response_content}
    except Exception as e:
        print(f"Error during LLM response formatting: {e}")
        return {"response": f"I found some information but had a slight issue preparing the final presentation: {agent_or_fallback_response}"}


def route_query(state: AgentState) -> str:
    print("---ROUTING QUERY---")
    query = state["query"].lower()
    document_path = state.get("document_path")

    if document_path:
        print(f"Routing to: lab_report_summarizer (document provided: {document_path})")
        return "lab_report_summarizer"
    elif "hospital" in query :
        print("Routing to: hospital_searcher")
        return "hospital_searcher"
    elif "pathology" in query or 'lab' in query:
        print("Routing to: pathology_searcher")
        return "pathology_searcher"
    elif "medicine" in query:
        print("Routing to: medicine_explainer")
        return "medicine_explainer"
    else:
        print("Routing to: fallback")
        return "fallback" 

workflow = StateGraph(AgentState)

workflow.add_node("hospital_searcher", hospital_searcher_node)
workflow.add_node("pathology_searcher", pathology_search_node)
workflow.add_node("medicine_explainer", medicine_explainer_node)
workflow.add_node("lab_report_summarizer", lab_report_summarizer_node)
workflow.add_node("fallback", fallback_node)
workflow.add_node("format_response", format_response_node)

workflow.set_conditional_entry_point(
    route_query,
    {
        "hospital_searcher": "hospital_searcher",
        "pathology_searcher": "pathology_searcher",
        "medicine_explainer": "medicine_explainer",
        "lab_report_summarizer": "lab_report_summarizer",
        "fallback": "fallback"
    }
)
workflow.add_edge("hospital_searcher", END)
workflow.add_edge("pathology_searcher", END)
workflow.add_edge("medicine_explainer", END)
workflow.add_edge("lab_report_summarizer", END)
workflow.add_edge("fallback", END)

app = workflow.compile() 

def run_query(user_query: str, doc_path: Optional[str] = None):
    inputs = {"query": user_query, "document_path": doc_path}
    print(f"\n🚀 Running query: \"{user_query}\"" + (f" (Document: {doc_path})" if doc_path else ""))
    print("--------------------")
    final_state = None
    try:
        for event in app.stream(inputs):
            for key, value in event.items():
                print(f"State update from node: {key}")
                if key == "__end__":
                    final_state = value 
        if final_state is None:
             invoked_output = app.invoke(inputs)
             final_state = invoked_output

        final_response = final_state.get('response') if final_state else "Error: Could not retrieve final state."

        print("\n✅ Final Formatted Response:")
        print(final_response)

    except Exception as e:
        print(f"\n❌ Error during graph execution: {e}")
        final_response = f"An unexpected error occurred: {e}"
    print("--------------------")
    return final_response

if __name__ == "__main__":
    # run_query("I'm feeling well, please search me hospital near Near Madhuban Chowk in delhi")
    # run_query("Hi, I'm in Delhi, feeling heavness in my heart and I want to know about the nearest hospital and contact details.")
    # run_query("I want to know me with all lab in delhi 24*7 open")
    # run_query("Embergency! find me lab or pathology near Vaishali in Ghaziabad")
    run_query("Please summerise the lab report", "/Volumes/careconnect/default/lab_reports/CBC-test-report-format-example-sample-template-Drlogy-lab-report.pdf")
